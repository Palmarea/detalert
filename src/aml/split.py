"""Asigna la muestra de cada transacción en `features.sample`.

- warmup: primeros 30 días; las ventanas de 30d aún no tienen historial completo
          (criterio de exclusión). No se usa para entrenar ni evaluar.
- train / test: ventana de desarrollo (warmup_end <= ts < OOT_START), 70/30
          estratificado por is_laundering, determinista por txn_id.
- oot: ts >= OOT_START (jun-ago 2023).

Uso:
    python -m aml.split
"""

import duckdb

from aml.config import DB_PATH, OOT_START, SPLIT_SEED, TEST_FRACTION

WARMUP_DAYS = 30


def assign_split(con: duckdb.DuckDBPyConnection, table: str = "features") -> None:
    (t0,) = con.execute(f"SELECT min(ts) FROM {table}").fetchone()
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _split AS
        WITH dev AS (
            SELECT txn_id,
                percent_rank() OVER (
                    PARTITION BY is_laundering ORDER BY hash(txn_id + {SPLIT_SEED}), txn_id
                ) AS pr
            FROM {table}
            WHERE ts >= TIMESTAMP '{t0}' + INTERVAL {WARMUP_DAYS} DAY AND ts < TIMESTAMP '{OOT_START}'
        )
        SELECT f.txn_id,
            CASE
                WHEN f.ts <  TIMESTAMP '{t0}' + INTERVAL {WARMUP_DAYS} DAY THEN 'warmup'
                WHEN f.ts >= TIMESTAMP '{OOT_START}' THEN 'oot'
                WHEN dev.pr < {TEST_FRACTION} THEN 'test'
                ELSE 'train'
            END AS sample
        FROM {table} f LEFT JOIN dev USING (txn_id)
    """)
    con.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS sample")
    con.execute(f"ALTER TABLE {table} ADD COLUMN sample VARCHAR")
    con.execute(f"UPDATE {table} SET sample = s.sample FROM _split s WHERE {table}.txn_id = s.txn_id")


def main() -> None:
    con = duckdb.connect(str(DB_PATH))
    assign_split(con)
    print(con.execute("""
        SELECT sample, count(*) AS filas, sum(is_laundering) AS lavado,
               round(100 * avg(is_laundering), 4) AS pct, min(ts)::DATE AS desde, max(ts)::DATE AS hasta
        FROM features GROUP BY 1 ORDER BY desde, sample
    """).df().to_string(index=False))
    con.close()


if __name__ == "__main__":
    main()
