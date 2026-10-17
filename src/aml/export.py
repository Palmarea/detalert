"""Exporta los resultados del batch (período OOT = "producción") a Postgres para la API.

Escribe aml.cases, aml.txn_scores (con reason codes y snapshot de features) y
aml.meta (umbrales y métricas). NO exporta etiquetas reales (is_laundering,
laundering_type): el agente no debe ver la respuesta.

Toma DATABASE_URL del entorno o del archivo .env (nunca la imprime).

Uso:
    python -m aml.export
"""

import json
import os
import time
from datetime import datetime, timezone

import duckdb
import lightgbm as lgb
import pandas as pd
import psycopg
from psycopg.types.json import Jsonb

from aml.config import DB_PATH, MODELS_DIR, ROOT
from aml.data import load
from aml.explain import reason_codes, snapshot

SAMPLE = "oot"
SCHEMA = ROOT / "sql" / "schema.sql"


def database_url() -> str:
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == "DATABASE_URL" and v.split("#")[0].strip():
                return v.split("#")[0].strip().strip("'\"")
    raise SystemExit("Falta DATABASE_URL (variable de entorno o archivo .env)")


def top_case_reasons(rcs: list[list[dict]], k: int = 4) -> list[dict]:
    """Agrega reason codes de las transacciones del caso: suma contribuciones por código."""
    agg: dict[str, dict] = {}
    for rc in rcs:
        for r in rc:
            a = agg.setdefault(r["code"], {**r, "contribution": 0.0})
            a["contribution"] += r["contribution"]
    return sorted(({**v, "contribution": round(v["contribution"], 4)} for v in agg.values()),
                  key=lambda r: -r["contribution"])[:k]


def main() -> None:
    t0 = time.time()
    meta = json.loads((MODELS_DIR / "binary_v1_meta.json").read_text())
    thresholds = json.loads((MODELS_DIR / "thresholds_v1.json").read_text())
    metrics = json.loads((MODELS_DIR / "api_metrics_v1.json").read_text())
    model_version, threshold_version = f"binary_{meta['version']}", thresholds["threshold_version"]
    feats = meta["features"]
    model = lgb.Booster(model_file=str(MODELS_DIR / f"binary_{meta['version']}.txt"))

    con = duckdb.connect(str(DB_PATH), read_only=True)
    txns = con.execute("""SELECT txn_id, case_id, ts, sender_account, receiver_account, amount, payment_type,
                                 score_raw, p, family_pred, family_conf
                          FROM case_txns WHERE sample = ? ORDER BY case_id, ts""", [SAMPLE]).df()
    cases = con.execute("""SELECT case_id, account, window_start, window_end, n_transactions, n_flagged,
                                  total_amount_flagged, case_score, family
                           FROM cases WHERE sample = ?""", [SAMPLE]).df()
    X = load([SAMPLE], cols=feats, where=f"txn_id IN (SELECT txn_id FROM case_txns WHERE sample = '{SAMPLE}')", con=con)
    con.close()
    X = X.set_index("txn_id").loc[txns.txn_id, feats]
    print(f"{len(cases):,} casos, {len(txns):,} transacciones. Calculando reason codes...")
    txns["reason_codes"] = reason_codes(model, X)
    txns["snapshot"] = snapshot(X)
    case_rc = txns.groupby("case_id").reason_codes.apply(lambda s: top_case_reasons(list(s)))
    scored_at = datetime.now(timezone.utc)

    with psycopg.connect(database_url()) as pg:
        pg.execute(SCHEMA.read_text())
        pg.execute("TRUNCATE aml.feedback, aml.txn_scores, aml.cases, aml.meta")
        pg.execute("INSERT INTO aml.meta VALUES ('thresholds', %s), ('metrics', %s)",
                   (Jsonb(thresholds), Jsonb(metrics)))
        with pg.cursor().copy("COPY aml.cases FROM STDIN") as cp:
            for r in cases.itertuples(index=False):
                cp.write_row((r.case_id, r.account, r.window_start.tz_localize("UTC"), r.window_end.tz_localize("UTC"),
                              int(r.n_transactions), int(r.n_flagged), float(r.total_amount_flagged),
                              float(r.case_score), r.family, json.dumps(case_rc[r.case_id]),
                              model_version, threshold_version))
        with pg.cursor().copy("COPY aml.txn_scores FROM STDIN") as cp:
            for r in txns.itertuples(index=False):
                cp.write_row((int(r.txn_id), r.ts.tz_localize("UTC"), r.sender_account, r.receiver_account,
                              float(r.amount), r.payment_type, float(r.score_raw), float(r.p), r.family_pred,
                              float(r.family_conf), json.dumps(r.reason_codes), json.dumps(r.snapshot),
                              r.case_id, scored_at, model_version, threshold_version))
        pg.execute("ANALYZE aml.cases; ANALYZE aml.txn_scores")
        n_c = pg.execute("SELECT count(*) FROM aml.cases").fetchone()[0]
        n_t = pg.execute("SELECT count(*) FROM aml.txn_scores").fetchone()[0]
        size = pg.execute("SELECT pg_size_pretty(sum(pg_total_relation_size(c.oid))) FROM pg_class c "
                          "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'aml'").fetchone()[0]
    print(f"Exportado: {n_c:,} casos, {n_t:,} transacciones ({size}) en {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
