"""EDA mínimo sobre `transactions`; escribe reports/eda.md.

Uso:
    python -m aml.eda
"""

import duckdb

from aml.config import DB_PATH, REPORTS_DIR, TYPOLOGY_TO_FAMILY


def md_table(df) -> str:
    return df.to_markdown(index=False) if hasattr(df, "to_markdown") else df.to_string(index=False)


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    q = lambda sql: con.execute(sql).df()  # noqa: E731

    overview = q("""
        SELECT count(*) AS filas,
               sum(is_laundering) AS lavado,
               round(100.0 * avg(is_laundering), 4) AS pct_lavado,
               min(ts) AS desde, max(ts) AS hasta,
               count(DISTINCT sender_account) AS emisores,
               count(DISTINCT receiver_account) AS receptores
        FROM transactions
    """)

    by_month = q("""
        SELECT strftime(ts, '%Y-%m') AS mes, count(*) AS filas,
               sum(is_laundering) AS lavado,
               round(100.0 * avg(is_laundering), 4) AS pct_lavado
        FROM transactions GROUP BY 1 ORDER BY 1
    """)

    typologies = q("""
        SELECT laundering_type, max(is_laundering) AS sospechosa, count(*) AS filas
        FROM transactions GROUP BY 1 ORDER BY 2 DESC, 3 DESC
    """)
    typologies["familia"] = typologies["laundering_type"].map(TYPOLOGY_TO_FAMILY).fillna("")
    unmapped = typologies[(typologies.sospechosa == 1) & (typologies.familia == "")]

    def by_cat(col: str):
        return q(f"""
            SELECT {col}, count(*) AS filas, sum(is_laundering) AS lavado,
                   round(100.0 * avg(is_laundering), 4) AS pct_lavado
            FROM transactions GROUP BY 1 ORDER BY filas DESC
        """)

    cross_border = q("""
        SELECT sender_bank_location <> receiver_bank_location AS cross_border,
               payment_currency <> received_currency AS cambio_moneda,
               count(*) AS filas, round(100.0 * avg(is_laundering), 4) AS pct_lavado
        FROM transactions GROUP BY 1, 2 ORDER BY 1, 2
    """)

    amounts = q("""
        SELECT is_laundering,
               round(quantile_cont(amount, 0.5), 2)  AS p50,
               round(quantile_cont(amount, 0.9), 2)  AS p90,
               round(quantile_cont(amount, 0.99), 2) AS p99,
               round(max(amount), 2) AS max
        FROM transactions GROUP BY 1 ORDER BY 1
    """)

    sections = [
        "# EDA — SAML-D\n",
        "## Resumen\n", md_table(overview),
        "\n## Por mes (para definir el split temporal)\n", md_table(by_month),
        "\n## Tipologías\n", md_table(typologies),
        "\n**Tipologías sospechosas sin familia asignada:** "
        + (", ".join(unmapped.laundering_type) if len(unmapped) else "ninguna"),
        "\n## Tipo de pago\n", md_table(by_cat("payment_type")),
        "\n## Ubicación del banco emisor\n", md_table(by_cat("sender_bank_location")),
        "\n## Ubicación del banco receptor\n", md_table(by_cat("receiver_bank_location")),
        "\n## Cross-border y cambio de moneda\n", md_table(cross_border),
        "\n## Montos por clase\n", md_table(amounts),
    ]
    REPORTS_DIR.mkdir(exist_ok=True)
    out = REPORTS_DIR / "eda.md"
    out.write_text("\n".join(sections) + "\n")
    print(f"Escrito {out}")
    if len(unmapped):
        print("ATENCIÓN: tipologías sin familia:", list(unmapped.laundering_type))


if __name__ == "__main__":
    main()
