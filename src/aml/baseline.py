"""Baseline = "modelo vigente": reglas típicas de monitoreo transaccional.

Umbrales fijados por criterio de negocio, NO ajustados con los datos, para que
la comparación sea honesta. Score = número de reglas disparadas.

Uso:
    python -m aml.baseline
"""

import json

import pandas as pd

from aml.config import REPORTS_DIR
from aml.data import load
from aml.metrics import summary

# Lista gris del GAFI (FATF) vigente en 2022-2023 para las jurisdicciones del dataset.
HIGH_RISK = {"Albania", "Morocco", "Nigeria", "Pakistan", "Turkey", "UAE"}

RULES = {
    "R1_efectivo": lambda d: d.payment_type.isin(["Cash Deposit", "Cash Withdrawal"]),
    "R2_jurisdiccion_riesgo": lambda d: d.receiver_bank_location.isin(HIGH_RISK) | d.sender_bank_location.isin(HIGH_RISK),
    "R3_monto_alto": lambda d: d.amount >= 50_000,
    "R4_estructuracion": lambda d: (d.is_near_10k == 1) | (d.s_cash_cnt_30d >= 5),
    "R5_monto_inusual": lambda d: d.s_amt_ratio_mean_30d >= 5,
    "R6_contraparte_nueva_monto": lambda d: (d.is_new_counterparty == 1) & (d.amount >= 10_000),
}
COLS = ["payment_type", "receiver_bank_location", "sender_bank_location", "amount", "is_near_10k",
        "s_cash_cnt_30d", "s_amt_ratio_mean_30d", "is_new_counterparty"]


def score(d: pd.DataFrame) -> pd.Series:
    return sum(rule(d).fillna(False).astype(int) for rule in RULES.values())


def main() -> None:
    out = {}
    for sample in ["test", "oot"]:
        d = load([sample], cols=COLS)
        s = score(d)
        m = summary(d.is_laundering, s)
        m["alert_rate_1+_reglas"] = round(float((s >= 1).mean()), 4)
        m["recall_1+_reglas"] = round(float(d.is_laundering[s >= 1].sum() / d.is_laundering.sum()), 4)
        m["alert_rate_2+_reglas"] = round(float((s >= 2).mean()), 4)
        m["recall_2+_reglas"] = round(float(d.is_laundering[s >= 2].sum() / d.is_laundering.sum()), 4)
        m["recall_por_regla"] = {k: round(float(d.is_laundering[r(d).fillna(False)].sum() / d.is_laundering.sum()), 4)
                                 for k, r in RULES.items()}
        out[sample] = m
        print(sample, json.dumps(m, indent=2))
    (REPORTS_DIR / "metrics_baseline.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
