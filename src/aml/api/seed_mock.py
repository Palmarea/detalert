"""Carga los datos del backend mock en Postgres (aplica sql/schema.sql primero).

Sirve para tener la API en Vercel con AML_BACKEND=postgres funcionando antes de
que exista el export real. El export real (aml.export) reemplaza estos datos.

Uso:
    DATABASE_URL=postgresql://... python -m aml.api.seed_mock
"""

import os
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from aml.api.mock import MockBackend

SCHEMA = Path(__file__).resolve().parents[3] / "sql" / "schema.sql"


def main() -> None:
    m = MockBackend()
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=False) as c:
        c.execute(SCHEMA.read_text())
        for mig in sorted((SCHEMA.parent / "migrations").glob("*.sql")):
            c.execute(mig.read_text())
        c.execute("TRUNCATE aml.feedback, aml.threshold_proposals, aml.txn_scores, aml.cases, aml.meta RESTART IDENTITY")
        c.execute("INSERT INTO aml.meta VALUES ('thresholds', %s), ('metrics', %s)",
                  (Jsonb(m.thresholds().model_dump(mode="json")), Jsonb(m.metrics().model_dump(mode="json"))))
        for cid, case in m._cases.items():
            c.execute(
                "INSERT INTO aml.cases VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (cid, case["account"], case["window_start"], case["window_end"], case["n_transactions"],
                 case["n_flagged"], case["total_amount_flagged"], case["case_score"], case["family"].value,
                 Jsonb([r.model_dump(mode="json") for r in case["top_reason_codes"]]),
                 m.model_version, m.threshold_version))
            for tid in case["txn_ids"]:
                t, a = m._txns[tid], m._audit[tid]
                c.execute(
                    "INSERT INTO aml.txn_scores VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (t.txn_id, t.ts, t.sender_account, t.receiver_account, t.amount, t.payment_type,
                     a.score_raw, t.p_laundering, t.family.value, t.family_confidence,
                     Jsonb([r.model_dump(mode="json") for r in t.reason_codes]), Jsonb(a.features_snapshot),
                     cid, a.scored_at, t.model_version, t.threshold_version))
        n_c = c.execute("SELECT count(*) FROM aml.cases").fetchone()[0]
        n_t = c.execute("SELECT count(*) FROM aml.txn_scores").fetchone()[0]
    print(f"Seed mock cargado: {n_c} casos, {n_t} transacciones")


if __name__ == "__main__":
    main()
