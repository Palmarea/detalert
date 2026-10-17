"""Herramientas de solo lectura del agente: consultan el historial con DuckDB.

La fuente es el CSV/Parquet de SAML-D (env AML_DATA_PATH). Las columnas de etiqueta
(Is_laundering, Laundering_type) NUNCA se devuelven al agente para evitar fuga de la respuesta.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import duckdb

LABEL_COLS = {"Is_laundering", "Laundering_type"}
CASH_TYPES = ("Cash Deposit", "Cash Withdrawal")
TX_COLS = ("Time, Date, Sender_account, Receiver_account, Amount, Payment_currency, "
           "Received_currency, Sender_bank_location, Receiver_bank_location, Payment_type")


@lru_cache(maxsize=1)
def _con(path: str | None = None) -> duckdb.DuckDBPyConnection:
    path = path or os.environ.get("AML_DATA_PATH", "data/SAML-D.csv")
    con = duckdb.connect(":memory:")
    reader = "read_parquet" if path.endswith(".parquet") else "read_csv_auto"
    # Vista con timestamp; sin columnas de etiqueta.
    con.execute(f"""
        CREATE VIEW tx AS
        SELECT {TX_COLS},
               CAST(Date AS DATE) + CAST(Time AS TIME) AS ts
        FROM {reader}('{path}')
    """)
    return con


def _rows(sql: str, params: list) -> list[dict[str, Any]]:
    cur = _con().execute(sql, params)
    cols = [d[0] for d in cur.description]
    out = []
    for r in cur.fetchall():
        d = {c: (v.isoformat() if hasattr(v, "isoformat") else v) for c, v in zip(cols, r)}
        out.append({k: v for k, v in d.items() if k not in LABEL_COLS})
    return out


def get_account_profile(account: int, until: str) -> dict[str, Any]:
    """Perfil de la cuenta con todo lo ocurrido ANTES de `until` (ISO datetime)."""
    sent = _rows("""
        SELECT COUNT(*) n_tx, ROUND(SUM(Amount),2) total, ROUND(MEDIAN(Amount),2) mediana,
               ROUND(MAX(Amount),2) maximo, COUNT(DISTINCT Receiver_account) contrapartes,
               ROUND(AVG(CASE WHEN Sender_bank_location<>Receiver_bank_location THEN 1 ELSE 0 END)*100,1) pct_cross_border,
               ROUND(AVG(CASE WHEN Payment_type IN ? THEN 1 ELSE 0 END)*100,1) pct_efectivo,
               MIN(ts) primera_tx, MAX(ts) ultima_tx,
               LIST(DISTINCT Receiver_bank_location) paises_destino,
               LIST(DISTINCT Payment_currency) monedas
        FROM tx WHERE Sender_account = ? AND ts < CAST(? AS TIMESTAMP)""", [list(CASH_TYPES), account, until])[0]
    recv = _rows("""
        SELECT COUNT(*) n_tx, ROUND(SUM(Amount),2) total, ROUND(MEDIAN(Amount),2) mediana,
               COUNT(DISTINCT Sender_account) contrapartes,
               LIST(DISTINCT Sender_bank_location) paises_origen
        FROM tx WHERE Receiver_account = ? AND ts < CAST(? AS TIMESTAMP)""", [account, until])[0]
    return {"account": account, "until": until, "como_emisor": sent, "como_receptor": recv,
            "cuenta_nueva": (sent["n_tx"] or 0) + (recv["n_tx"] or 0) == 0}


def get_account_history(account: int, until: str, role: str = "any", days: int = 30,
                        limit: int = 50) -> dict[str, Any]:
    """Últimas transacciones de la cuenta en los `days` días previos a `until`."""
    limit = max(1, min(int(limit), 200))
    cond = {"sender": "Sender_account = ?", "receiver": "Receiver_account = ?",
            "any": "(Sender_account = ? OR Receiver_account = ?)"}[role]
    params = [account] * (2 if role == "any" else 1) + [until, until, int(days)]
    rows = _rows(f"""
        SELECT {TX_COLS} FROM tx
        WHERE {cond} AND ts < CAST(? AS TIMESTAMP)
          AND ts >= CAST(? AS TIMESTAMP) - (? * INTERVAL 1 DAY)
        ORDER BY ts DESC LIMIT {limit}""", params)
    return {"account": account, "role": role, "days": days, "n_devueltas": len(rows), "transacciones": rows}


def get_network_signals(account: int, until: str, days: int = 7) -> dict[str, Any]:
    """Fan-in/fan-out, ratio de paso y ciclos de 2–3 saltos en la ventana."""
    p = [until, until, int(days)]
    win = "ts < CAST(? AS TIMESTAMP) AND ts >= CAST(? AS TIMESTAMP) - (? * INTERVAL 1 DAY)"
    flows = _rows(f"""
        SELECT
          (SELECT COUNT(DISTINCT Receiver_account) FROM tx WHERE Sender_account=? AND {win}) fan_out,
          (SELECT COUNT(DISTINCT Sender_account)  FROM tx WHERE Receiver_account=? AND {win}) fan_in,
          (SELECT ROUND(COALESCE(SUM(Amount),0),2) FROM tx WHERE Receiver_account=? AND {win}) entra,
          (SELECT ROUND(COALESCE(SUM(Amount),0),2) FROM tx WHERE Sender_account=? AND {win}) sale
    """, [account, *p, account, *p, account, *p, account, *p])[0]
    hi, lo = max(flows["entra"], flows["sale"]), min(flows["entra"], flows["sale"])
    flows["ratio_paso"] = round(lo / hi, 3) if hi else None
    cycles = _rows(f"""
        WITH w AS (SELECT Sender_account s, Receiver_account r FROM tx WHERE {win})
        SELECT COUNT(*) FILTER (WHERE c2) ciclos_2_saltos, COUNT(*) FILTER (WHERE c3) ciclos_3_saltos FROM (
          SELECT EXISTS(SELECT 1 FROM w b WHERE b.s=a.r AND b.r=?) c2,
                 EXISTS(SELECT 1 FROM w b JOIN w c ON c.s=b.r WHERE b.s=a.r AND c.r=? AND b.r<>?) c3
          FROM (SELECT DISTINCT r FROM w WHERE s=?) a)""", [*p, account, account, account, account])[0]
    return {"account": account, "days": days, **flows, **cycles}


# --- Definiciones para la API de Claude -------------------------------------------------
_ACC = {"type": "integer", "description": "Número de cuenta (Sender_account o Receiver_account)"}
_UNTIL = {"type": "string", "description": "Fecha-hora ISO de la transacción revisada; solo se mira el pasado"}

TOOL_SPECS = [
    {"name": "get_account_profile", "description": "Perfil histórico de una cuenta antes de la transacción.",
     "input_schema": {"type": "object", "properties": {"account": _ACC, "until": _UNTIL},
                      "required": ["account", "until"]}},
    {"name": "get_account_history", "description": "Últimas transacciones de una cuenta en una ventana de días.",
     "input_schema": {"type": "object", "properties": {
         "account": _ACC, "until": _UNTIL,
         "role": {"type": "string", "enum": ["sender", "receiver", "any"]},
         "days": {"type": "integer", "minimum": 1, "maximum": 365},
         "limit": {"type": "integer", "minimum": 1, "maximum": 200}},
         "required": ["account", "until"]}},
    {"name": "get_network_signals", "description": "Fan-in, fan-out, ratio de paso y ciclos de la cuenta.",
     "input_schema": {"type": "object", "properties": {
         "account": _ACC, "until": _UNTIL, "days": {"type": "integer", "minimum": 1, "maximum": 90}},
         "required": ["account", "until"]}},
]

REGISTRY = {"get_account_profile": get_account_profile,
            "get_account_history": get_account_history,
            "get_network_signals": get_network_signals}