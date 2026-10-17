"""Compuerta de ML para las propuestas de umbral del agente: simulación OOT con etiquetas reales.

La API no ve `is_laundering`, así que la simulación corre aquí (duckdb local) y
escribe el resultado en aml.threshold_proposals:
- blocked -> pending cuando el analista aprobó (`approved`) todos los casos de evidencia.
- pending -> passed / rejected según los límites GUARDS en OOT.
- --apply P-00X: publica una passed como nueva threshold_version en aml.meta (lo
  que sirve la API en vivo) y en models/thresholds_current.json (lo que usa el export).
  Es el ÚNICO paso que cambia producción y siempre es manual.

Toma DATABASE_URL del entorno o de .env (nunca la imprime).

Uso:
    python -m aml.review_proposals                 # revisa pendientes y bloqueadas
    python -m aml.review_proposals --apply P-002   # publica una propuesta que pasó
"""

import argparse
import copy
import json
from datetime import datetime, timezone

import duckdb
import pandas as pd
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from aml.config import DB_PATH, MODELS_DIR
from aml.export import database_url
from aml.thresholds import evaluate

# Límites de la compuerta (acordados con el equipo del agente; ver PARA_ML_AUTOMEJORA.md).
MAX_MISSED_LAUNDERING = 0.003   # lavado que se cierra solo, como % de los casos con lavado
MIN_HP_PRECISION = 0.95
MAX_QUEUE_PER_DAY = 130


def oot_cases() -> tuple[pd.DataFrame, float]:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    oot = con.execute("SELECT case_score, is_laundering, window_start, window_end FROM cases "
                      "WHERE sample = 'oot'").df()
    days = (oot.window_end.max() - oot.window_start.min()).total_seconds() / 86400
    return oot, days


def _pct(x: float | None, d: int = 2) -> str:
    return "—" if x is None else f"{x * 100:.{d}f} %".replace(".", ",")


def simulate(ask: list, th: dict, oot: pd.DataFrame, days: float) -> tuple[dict, dict, list, bool]:
    op = next(o for o in th["operating_points"] if o["mode"] == "normal")
    a, h = op["auto_close_threshold"], op["high_priority_threshold"]
    which, _, new = ask
    a2, h2 = (new, h) if which == "auto" else (a, new)
    before, after = evaluate(oot, a, h, days), evaluate(oot, a2, h2, days)
    guards = [
        ("Lavado que se cierra solo", f"límite ≤ {_pct(MAX_MISSED_LAUNDERING)} de los casos con lavado",
         f"{_pct(before['missed_laundering_pct'])} → {_pct(after['missed_laundering_pct'])}",
         after["missed_laundering_pct"] <= MAX_MISSED_LAUNDERING),
        ("Precisión de prioridad alta", f"límite ≥ {_pct(MIN_HP_PRECISION, 0)}",
         f"{_pct(before['high_priority_precision'], 1)} → {_pct(after['high_priority_precision'], 1)}",
         (after["high_priority_precision"] or 0) >= MIN_HP_PRECISION),
        ("Cola del analista", f"límite ≤ {MAX_QUEUE_PER_DAY} casos por día",
         f"{before['queue_cases_per_day']} → {after['queue_cases_per_day']}",
         after["queue_cases_per_day"] <= MAX_QUEUE_PER_DAY),
    ]
    snap = lambda ev, aa, hh: {"a": round(ev["auto_close_rate"] * 100, 1),  # noqa: E731
                               "h": None if ev["high_priority_precision"] is None
                               else round(ev["high_priority_precision"] * 100, 1), "auto": aa, "high": hh}
    return snap(before, a, h), snap(after, a2, h2) | {"_eval": after}, [list(g) for g in guards], \
        all(g[3] for g in guards)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M")


def review(pg, th: dict) -> None:
    oot, days = oot_cases()
    props = pg.execute("SELECT * FROM aml.threshold_proposals WHERE status IN ('blocked', 'pending') "
                       "ORDER BY seq").fetchall()
    for p in props:
        log, status, reason = p["log"], p["status"], p["reason"]
        if p["base_threshold_version"] != th["threshold_version"]:
            status, reason = "rejected", (f"Desactualizada: se propuso sobre {p['base_threshold_version']} y la "
                                          f"vigente es {th['threshold_version']}.")
            log.append(["Compuerta", reason, _now()])
        if status == "blocked":
            ids = list({e[0] for e in p["evidence"]})
            n = pg.execute("SELECT count(DISTINCT case_id) AS n FROM aml.feedback WHERE actor = 'analyst' "
                           "AND decision = 'approved' AND case_id = ANY(%s)", (ids,)).fetchone()["n"]
            if n < len(ids):
                print(f"{p['proposal_id']}: sigue bloqueada ({n} de {len(ids)} aprobaciones del analista)")
                continue
            log.append(["Analista", f"Aprobó los {n} casos de evidencia", _now()])
            status = "pending"
        to = guards = None
        if status == "pending":
            frm, to, guards, ok = simulate(p["ask"], th, oot, days)
            to.pop("_eval")
            status = "passed" if ok else "rejected"
            failed = [g[0] for g in guards if not g[3]]
            reason = ("Pasa los tres límites en OOT. Falta que ML la aplique." if ok
                      else f"No cumple en OOT: {', '.join(failed)}.")
            log.append(["Simulación OOT", reason, _now()])
            pg.execute("UPDATE aml.threshold_proposals SET from_snapshot = %s WHERE seq = %s",
                       (Jsonb(frm), p["seq"]))
        pg.execute("UPDATE aml.threshold_proposals SET status = %s, reason = %s, to_snapshot = %s, guards = %s, "
                   "log = %s WHERE seq = %s",
                   (status, reason, Jsonb(to) if to else None, Jsonb(guards) if guards else None, Jsonb(log),
                    p["seq"]))
        print(f"{p['proposal_id']}: {status} — {reason}")
    if not props:
        print("No hay propuestas pendientes ni bloqueadas.")


def apply(pg, th: dict, proposal_id: str) -> None:
    p = pg.execute("SELECT * FROM aml.threshold_proposals WHERE proposal_id = %s", (proposal_id,)).fetchone()
    if p is None or p["status"] != "passed":
        raise SystemExit(f"{proposal_id}: solo se aplica una propuesta en estado 'passed' "
                         f"(está en {p and p['status']})")
    if p["base_threshold_version"] != th["threshold_version"]:
        raise SystemExit(f"{proposal_id}: desactualizada; vuelve a correr la revisión")
    oot, days = oot_cases()
    _, to, _, ok = simulate(p["ask"], th, oot, days)
    if not ok:
        raise SystemExit(f"{proposal_id}: ya no pasa los límites; vuelve a correr la revisión")
    ev = to.pop("_eval")
    n = pg.execute("SELECT count(*) AS n FROM aml.threshold_proposals WHERE status = 'applied'").fetchone()["n"]
    base = th["threshold_version"].split(".")[0]
    version = f"{base}.{n + 1}-agente"

    new = copy.deepcopy(th)
    new["threshold_version"] = version
    for op in new["operating_points"]:
        if op["mode"] == "normal":
            op.update(auto_close_threshold=to["auto"], high_priority_threshold=to["high"],
                      auto_close_rate=ev["auto_close_rate"], expected_leakage=ev["expected_leakage"],
                      missed_laundering_pct=ev["missed_laundering_pct"],
                      queue_cases_per_day=ev["queue_cases_per_day"])
        elif op["mode"] == "no_analyst" and p["ask"][0] == "auto":
            # Por diseño, sin analista usa el mismo auto-cierre seguro que normal y todo lo demás es prioridad alta.
            op.update(auto_close_threshold=to["auto"], high_priority_threshold=to["auto"],
                      auto_close_rate=ev["auto_close_rate"], expected_leakage=ev["expected_leakage"],
                      missed_laundering_pct=ev["missed_laundering_pct"])

    (MODELS_DIR / f"{version}.json").write_text(json.dumps(new, indent=2))
    (MODELS_DIR / "thresholds_current.json").write_text(json.dumps(new, indent=2))
    pg.execute("UPDATE aml.meta SET value = %s WHERE key = 'thresholds'", (Jsonb(new),))
    log = p["log"] + [["ML", f"Aplicada como {version}", _now()]]
    pg.execute("UPDATE aml.threshold_proposals SET status = 'applied', applied_version = %s, to_snapshot = %s, "
               "reason = %s, log = %s WHERE seq = %s",
               (version, Jsonb(to), f"Pasa los tres límites. Nueva versión {version}.", Jsonb(log), p["seq"]))
    print(f"{proposal_id}: aplicada como {version} (la API la sirve en ≤ 60 s)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", metavar="PROPOSAL_ID", help="publica una propuesta 'passed' (cambia producción)")
    args = ap.parse_args()
    with psycopg.connect(database_url(), row_factory=dict_row, prepare_threshold=None) as pg:
        th = pg.execute("SELECT value FROM aml.meta WHERE key = 'thresholds'").fetchone()["value"]
        apply(pg, th, args.apply) if args.apply else review(pg, th)


if __name__ == "__main__":
    main()
