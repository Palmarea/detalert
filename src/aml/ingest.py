"""Carga el CSV de SAML-D a DuckDB como tabla `transactions`.

Uso:
    python -m aml.ingest [ruta_csv]
Si no se pasa ruta, toma el único CSV dentro de data/raw/.
"""

import sys
from pathlib import Path

import duckdb

from aml.config import DB_PATH, RAW_COLUMNS, RAW_DIR


def find_csv(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    csvs = sorted(RAW_DIR.glob("*.csv"))
    if len(csvs) != 1:
        raise SystemExit(f"Esperaba exactamente 1 CSV en {RAW_DIR}, encontré {len(csvs)}: {csvs}")
    return csvs[0]


def ingest(csv_path: Path, db_path: Path = DB_PATH) -> None:
    con = duckdb.connect(str(db_path))

    header = con.execute(f"SELECT * FROM read_csv_auto('{csv_path}') LIMIT 0").df().columns
    missing = set(RAW_COLUMNS) - set(header)
    if missing:
        raise SystemExit(f"Faltan columnas en el CSV: {sorted(missing)}. Columnas encontradas: {list(header)}")

    renames = ", ".join(f'"{src}" AS {dst}' for src, dst in RAW_COLUMNS.items())

    # txn_id estable: orden determinista por todas las columnas. Filas idénticas
    # son indistinguibles de todos modos.
    con.execute(f"""
        CREATE OR REPLACE TABLE transactions AS
        WITH raw AS (
            SELECT {renames} FROM read_csv_auto('{csv_path}', header = true)
        ),
        typed AS (
            SELECT
                CAST(date AS DATE) + CAST(time AS TIME) AS ts,
                CAST(sender_account AS VARCHAR)   AS sender_account,
                CAST(receiver_account AS VARCHAR) AS receiver_account,
                CAST(amount AS DOUBLE)            AS amount,
                payment_currency,
                received_currency,
                sender_bank_location,
                receiver_bank_location,
                payment_type,
                CAST(is_laundering AS TINYINT)    AS is_laundering,
                laundering_type
            FROM raw
        )
        SELECT
            row_number() OVER (
                ORDER BY ts, sender_account, receiver_account, amount, payment_type
            ) AS txn_id,
            *
        FROM typed
        ORDER BY txn_id
    """)

    n, pos, t0, t1 = con.execute("""
        SELECT count(*), sum(is_laundering), min(ts), max(ts) FROM transactions
    """).fetchone()
    print(f"transactions: {n:,} filas | lavado: {pos:,} ({pos / n:.4%}) | {t0} -> {t1}")
    con.close()


if __name__ == "__main__":
    ingest(find_csv(sys.argv[1] if len(sys.argv) > 1 else None))
