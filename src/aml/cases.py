"""Agrupa transacciones alertadas en casos (la unidad de trabajo del agente y del analista).

- Umbral de alerta: el p que da TARGET_RECALL de recall de transacciones en test.
- Caso: alertas del mismo emisor; un caso nuevo empieza cuando una alerta cae a
  más de CASE_WINDOW_DAYS de la primera alerta del caso vigente.
- case_score = máxima p calibrada del caso. Familia = la de su transacción de mayor p.
- Etiqueta (solo evaluación): el caso es positivo si contiene alguna transacción de lavado.

Uso:
    python -m aml.cases
"""

import json

import duckdb
import numpy as np
import pandas as pd

from aml.config import DB_PATH, MODELS_DIR

TARGET_RECALL = 0.99
CASE_WINDOW_DAYS = 7


def alert_threshold(con) -> float:
    p_pos = con.execute("""SELECT s.p FROM scores s JOIN features f USING (txn_id)
                           WHERE s.sample = 'test' AND f.is_laundering = 1""").df().p.to_numpy()
    return float(np.quantile(p_pos, 1 - TARGET_RECALL))


def build_cases(alerts: pd.DataFrame) -> pd.Series:
    """Devuelve el case_id de cada alerta (alerts ordenadas por sender_account, ts)."""
    ids = np.empty(len(alerts), dtype=object)
    window = pd.Timedelta(days=CASE_WINDOW_DAYS)
    prev_acct, start = None, None
    for i, (acct, ts) in enumerate(zip(alerts.sender_account.to_numpy(), alerts.ts)):
        if acct != prev_acct or ts - start > window:
            prev_acct, start = acct, ts
        ids[i] = f"C-{acct}-{start:%Y-%m-%d}"
    return pd.Series(ids, index=alerts.index)


def main() -> None:
    con = duckdb.connect(str(DB_PATH))
    thr = alert_threshold(con)
    print(f"Umbral de alerta (recall {TARGET_RECALL:.0%} en test): p >= {thr:.6f}")

    alerts = con.execute("""
        SELECT s.txn_id, s.sample, s.p, s.score_raw, s.family_pred, s.family_conf,
               f.ts, f.sender_account, f.receiver_account, f.amount, f.payment_type,
               f.is_laundering, f.laundering_type, f.family
        FROM scores s JOIN features f USING (txn_id)
        WHERE s.p >= ? ORDER BY f.sender_account, f.ts""", [thr]).df()
    alerts["case_id"] = alerts.groupby("sample", group_keys=False).apply(build_cases, include_groups=False)

    top = alerts.sort_values("p", ascending=False).drop_duplicates("case_id").set_index("case_id")
    g = alerts.groupby("case_id")
    cases = pd.DataFrame({
        "sample": g["sample"].first(),
        "account": g.sender_account.first(),
        "window_start": g.ts.min(),
        "window_end": g.ts.max(),
        "n_flagged": g.size(),
        "total_amount_flagged": g.amount.sum().round(2),
        "case_score": g.p.max(),
        "family": top.family_pred,
        "is_laundering": g.is_laundering.max(),
        "true_family": g.family.agg(lambda s: s.dropna().mode().iloc[0] if s.notna().any() else None),
        "true_typology": g.laundering_type.agg(lambda s: s[alerts.loc[s.index, "is_laundering"] == 1].mode().iloc[0]
                                               if alerts.loc[s.index, "is_laundering"].any() else None),
    }).reset_index()

    con.register("cases_df", cases)
    con.register("alerts_df", alerts.drop(columns=["family"]))
    con.execute("CREATE OR REPLACE TABLE case_txns AS SELECT * FROM alerts_df")
    # n_transactions: toda la actividad del emisor en la ventana del caso (no solo lo alertado).
    con.execute("""
        CREATE OR REPLACE TABLE cases AS
        SELECT c.*, (SELECT count(*) FROM features f
                     WHERE f.sender_account = c.account AND f.sample = c.sample
                       AND f.ts BETWEEN c.window_start AND c.window_end) AS n_transactions
        FROM cases_df c""")
    (MODELS_DIR / "alert_threshold.json").write_text(json.dumps(
        {"alert_threshold": thr, "target_recall": TARGET_RECALL, "case_window_days": CASE_WINDOW_DAYS}, indent=2))
    print(con.execute("""
        SELECT sample, count(*) AS casos, sum(is_laundering) AS casos_lavado,
               round(avg(n_flagged), 2) AS alertas_por_caso, round(median(case_score), 4) AS score_mediano
        FROM cases GROUP BY 1 ORDER BY 1""").df().to_string(index=False))
    con.close()


if __name__ == "__main__":
    main()
