"""Reason codes: las features que más empujaron el score hacia "lavado" (SHAP de LightGBM).

Se toman las TOP_K contribuciones positivas al log-odds (pred_contrib) y se
traducen a texto legible para el agente y el analista.
"""

import numpy as np
import pandas as pd

TOP_K = 3

# feature -> (código, plantilla). {v} es el valor de la feature en la transacción.
TEMPLATES = {
    "is_new_counterparty": ("NEW_COUNTERPARTY", "Primera transacción hacia esta contraparte"),
    "s_hours_since_prev": ("SENDER_DORMANT", "El emisor llevaba {v:.1f} h sin operar"),
    "r_hours_since_prev": ("RECEIVER_RAPID", "El receptor recibió otra transferencia hace {v:.2f} h"),
    "payment_type": ("PAYMENT_TYPE", "Tipo de pago: {v}"),
    "amount": ("AMOUNT", "Monto de {v:,.2f}"),
    "pair_cnt_7d": ("PAIR_REPEAT_7D", "{v:.0f} transferencias previas a la misma contraparte en 7 días"),
    "s_amt_7d": ("SENDER_VOLUME_7D", "El emisor movió {v:,.0f} en los últimos 7 días"),
    "s_cnt_7d": ("SENDER_VELOCITY_7D", "El emisor hizo {v:.0f} transacciones en 7 días"),
    "s_cnt_30d": ("SENDER_VELOCITY_30D", "El emisor hizo {v:.0f} transacciones en 30 días"),
    "r_out_cnt_7d": ("RECEIVER_FORWARDS", "El receptor reenvió dinero {v:.0f} veces en 7 días"),
    "r_uniq_snd_7d": ("FAN_IN_7D", "El receptor recibió de {v:.0f} emisores distintos en 7 días"),
    "r_uniq_snd_30d": ("FAN_IN_30D", "El receptor recibió de {v:.0f} emisores distintos en 30 días"),
    "s_cash_cnt_30d": ("CASH_30D", "{v:.0f} operaciones en efectivo del emisor en 30 días"),
    "s_amt_z_30d": ("AMOUNT_ZSCORE", "Monto a {v:.1f} desviaciones del historial de 30 días"),
    "s_amt_ratio_mean_30d": ("AMOUNT_UNUSUAL", "Monto {v:.1f}x el promedio de 30 días de la cuenta"),
    "s_out_in_ratio_7d": ("PASS_THROUGH", "Salidas/entradas del emisor en 7 días: {v:.2f}"),
    "s_in_cnt_7d": ("SENDER_INFLOWS_7D", "El emisor recibió {v:.0f} transferencias en 7 días"),
    "currency_mismatch": ("CURRENCY_MISMATCH", "La moneda de pago y la de recepción no coinciden"),
}


def _fmt(feature: str, value) -> str:
    code_tpl = TEMPLATES.get(feature)
    if code_tpl is None:
        return f"{feature} = {value}"
    try:
        return code_tpl[1].format(v=value)
    except (ValueError, TypeError):
        return code_tpl[1].replace("{v:.0f}", "s/d").replace("{v:.1f}", "s/d").replace("{v:.2f}", "s/d") \
            .replace("{v:,.0f}", "s/d").replace("{v:,.2f}", "s/d").replace("{v}", "s/d")


def _json_value(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (np.integer, int)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return round(float(v), 6)
    return str(v)


def reason_codes(model, X: pd.DataFrame, top_k: int = TOP_K) -> list[list[dict]]:
    contrib = model.predict(X, pred_contrib=True)[:, :-1]  # última columna = bias
    feats = list(X.columns)
    out = []
    for i in range(len(X)):
        row = contrib[i]
        idx = [j for j in np.argsort(-row)[:top_k] if row[j] > 0]
        out.append([{
            "code": TEMPLATES.get(feats[j], (feats[j].upper(), ""))[0],
            "feature": feats[j],
            "value": _json_value(X.iat[i, j]),
            "contribution": round(float(row[j]), 4),
            "text": _fmt(feats[j], X.iat[i, j]),
        } for j in idx])
    return out


def snapshot(X: pd.DataFrame) -> list[dict]:
    return [{c: _json_value(v) for c, v in zip(X.columns, row)} for row in X.itertuples(index=False)]
