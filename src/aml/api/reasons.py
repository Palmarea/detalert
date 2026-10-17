"""Reason codes legibles a partir de contribuciones por feature (sin dependencias pesadas).

Lo usan el batch (aml/explain.py, contribuciones SHAP de LightGBM) y el scoring en
vivo de la API (contribuciones de Saabas del predictor en Python puro).
"""

import math

TOP_K = 3

# feature -> (código, plantilla). {v} es el valor de la feature en la transacción.
TEMPLATES = {
    "is_new_counterparty": ("NEW_COUNTERPARTY", "Primera transacción hacia esta contraparte"),
    "s_hours_since_prev": ("SENDER_TIME_SINCE_PREV", "El emisor llevaba {v:.1f} h sin operar"),
    "r_hours_since_prev": ("RECEIVER_TIME_SINCE_PREV", "El receptor recibió otra transferencia hace {v:.2f} h"),
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
_NO_HISTORY = {
    "s_hours_since_prev": "El emisor no tiene transacciones previas",
    "r_hours_since_prev": "El receptor no tiene transacciones previas",
    "s_amt_ratio_mean_30d": "El emisor no tiene historial en 30 días para comparar el monto",
    "s_amt_z_30d": "El emisor no tiene historial suficiente para comparar el monto",
    "s_out_in_ratio_7d": "El emisor no recibió dinero en 7 días",
}


def is_missing(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def code(feature: str) -> str:
    return TEMPLATES.get(feature, (feature.upper(), ""))[0]


def text(feature: str, value) -> str:
    if is_missing(value):
        return _NO_HISTORY.get(feature, f"{feature}: sin dato")
    tpl = TEMPLATES.get(feature)
    if tpl is None:
        return f"{feature} = {value}"
    try:
        return tpl[1].format(v=value)
    except (ValueError, TypeError):
        return f"{feature} = {value}"


def top_reasons(contrib: dict[str, float], values: dict, top_k: int = TOP_K) -> list[dict]:
    """Las top_k contribuciones positivas (empujan hacia "lavado") como reason codes."""
    ranked = sorted(((f, c) for f, c in contrib.items() if c > 0), key=lambda fc: -fc[1])[:top_k]
    return [{"code": code(f), "feature": f,
             "value": None if is_missing(values.get(f)) else values.get(f),
             "contribution": round(c, 4), "text": text(f, values.get(f))} for f, c in ranked]
