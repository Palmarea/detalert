"""Exporta lo necesario para el scoring en vivo a Postgres.

- aml.history: transacciones desde HISTORY_START (todas, no solo alertadas), columnas mínimas.
- aml.pairs_before: pares emisor->receptor vistos antes de HISTORY_START.
- aml.accounts_before: última vez que cada cuenta envió/recibió antes de HISTORY_START.
- aml.meta['live_model']: modelos binario y de familia compactos + calibración de Platt.

Uso:
    python -m aml.export_live               # historial + modelo (~40 s; duplica el tamaño durante la carga)
    python -m aml.export_live --model-only  # solo aml.meta['live_model'] (tras reentrenar)
"""

import json
import pickle
import sys
import time
from datetime import timezone

import duckdb
import lightgbm as lgb
import psycopg
from psycopg.types.json import Jsonb

from aml.api.predictor import compact_model
from aml.config import DB_PATH, MODELS_DIR, ROOT
from aml.export import database_url

HISTORY_START = "2023-07-01"
DDL = """
CREATE SCHEMA IF NOT EXISTS aml;
DROP TABLE IF EXISTS aml.history, aml.pairs_before, aml.accounts_before;
CREATE TABLE aml.history (
    ts       TIMESTAMPTZ NOT NULL,
    sender   BIGINT NOT NULL,
    receiver BIGINT NOT NULL,
    amount   DOUBLE PRECISION NOT NULL,
    is_cash  BOOLEAN NOT NULL
);
CREATE TABLE aml.pairs_before (sender BIGINT, receiver BIGINT, PRIMARY KEY (sender, receiver));
CREATE TABLE aml.accounts_before (acct BIGINT PRIMARY KEY, last_send_ts TIMESTAMPTZ, last_recv_ts TIMESTAMPTZ);
"""
INDEXES = """
CREATE INDEX history_sender_ts ON aml.history (sender, ts);
CREATE INDEX history_receiver_ts ON aml.history (receiver, ts);
ALTER TABLE aml.history ENABLE ROW LEVEL SECURITY;
ALTER TABLE aml.pairs_before ENABLE ROW LEVEL SECURITY;
ALTER TABLE aml.accounts_before ENABLE ROW LEVEL SECURITY;
ANALYZE aml.history; ANALYZE aml.pairs_before; ANALYZE aml.accounts_before;
"""


def _utc(v):
    return v.replace(tzinfo=timezone.utc) if hasattr(v, "tzinfo") and v is not None else v


def copy_rows(pg, table: str, rows) -> int:
    n = 0
    with pg.cursor().copy(f"COPY {table} FROM STDIN") as cp:
        for r in rows:
            cp.write_row(tuple(_utc(v) for v in r))
            n += 1
    return n


def main() -> None:
    t0 = time.time()
    model_only = "--model-only" in sys.argv
    meta = json.loads((MODELS_DIR / "binary_v1_meta.json").read_text())
    fmeta = json.loads((MODELS_DIR / "family_v1_meta.json").read_text())
    with open(MODELS_DIR / "calibrator_v1.pkl", "rb") as fh:
        cal = pickle.load(fh)

    con = duckdb.connect(str(DB_PATH), read_only=True)
    hist = pairs = accts = []
    if not model_only:
        hist = con.execute(f"""
        SELECT ts, sender_account::BIGINT, receiver_account::BIGINT, amount,
               payment_type IN ('Cash Deposit', 'Cash Withdrawal')
        FROM transactions WHERE ts >= '{HISTORY_START}' ORDER BY ts""").fetchall()
        pairs = con.execute(f"""SELECT DISTINCT sender_account::BIGINT, receiver_account::BIGINT
                                FROM transactions WHERE ts < '{HISTORY_START}'""").fetchall()
        accts = con.execute(f"""
        WITH s AS (SELECT sender_account::BIGINT a, max(ts) t FROM transactions WHERE ts < '{HISTORY_START}' GROUP BY 1),
             r AS (SELECT receiver_account::BIGINT a, max(ts) t FROM transactions WHERE ts < '{HISTORY_START}' GROUP BY 1)
        SELECT coalesce(s.a, r.a), s.t, r.t
        FROM s FULL OUTER JOIN r ON s.a = r.a""").fetchall()
    (h_end,) = con.execute("SELECT max(ts) FROM transactions").fetchone()
    con.close()
    print(f"historial {len(hist):,} · pares previos {len(pairs):,} · cuentas previas {len(accts):,}")

    live_model = {
        "model_version": f"binary_{meta['version']}",
        "binary": compact_model(lgb.Booster(model_file=str(MODELS_DIR / f"binary_{meta['version']}.txt"))),
        "family": compact_model(lgb.Booster(model_file=str(MODELS_DIR / f"family_{fmeta['version']}.txt"))),
        "platt": {"coef": float(cal.lr.coef_[0][0]), "intercept": float(cal.lr.intercept_[0])},
        "family_classes": fmeta["classes"],
        "generic_below": fmeta["generic_below"],
        "history_start": f"{HISTORY_START}T00:00:00+00:00",
        "history_end": h_end.isoformat() + "+00:00",
    }

    with psycopg.connect(database_url(), prepare_threshold=None) as pg:
        if not model_only:
            pg.execute(DDL)
            copy_rows(pg, "aml.history", hist)
            copy_rows(pg, "aml.pairs_before", pairs)
            copy_rows(pg, "aml.accounts_before", accts)
            pg.execute(INDEXES)
        pg.execute("INSERT INTO aml.meta VALUES ('live_model', %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                   (Jsonb(live_model),))
    # Tamaño medido después del commit (dentro de la transacción las tablas viejas aún ocupan espacio).
    with psycopg.connect(database_url(), prepare_threshold=None) as pg:
        size = pg.execute("SELECT pg_size_pretty(pg_database_size(current_database()))").fetchone()[0]
    print(f"Listo en {time.time() - t0:.0f}s · tamaño total de la base: {size}")


if __name__ == "__main__":
    main()
