"""Convierte el veredicto del agente al contrato de detalert (/api/ingest) y lo envía.

Lo que no existe en SAML-D (nombre, email, documento, política, responsable...) se envía como "---".
El token se lee SIEMPRE de la variable de entorno INGEST_TOKEN; nunca va en el código.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone

from .schema import MISSING

OUTCOME = {"APPROVE": "good", "ESCALATE": "review", "REJECT": "bad"}       # supuesto: confirmar con el front
STATUS = {"APPROVE": "approved", "ESCALATE": "under_review", "REJECT": "rejected"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_event(tx: dict, model_out: dict, result: dict, tx_id: str) -> dict:
    v, now = result["verdict"], _now()
    p = model_out.get("p_laundering")
    score = round(p * 100) if isinstance(p, (int, float)) else MISSING
    inv, typ = v["investigation"], v["typology"]

    factors = [{"label": f"{f['signal']}: {f['evidence']}", "points": f["points"]}
               for f in v["red_flags"] + v["mitigating_factors"]]
    rules = [
        {"id": "M-01", "name": "Banda del modelo binary_v1", "fired": model_out.get("band") != "auto_close_eligible",
         "detail": f"p_laundering={p} · band={model_out.get('band', MISSING)}"},
        {"id": "A-01", "name": "Expansión al historial del emisor", "fired": inv["expanded_sender"],
         "detail": inv["expansion_reason"]},
        {"id": "A-02", "name": "Expansión al historial del receptor", "fired": inv["expanded_receiver"],
         "detail": inv["expansion_reason"]},
        {"id": "A-03", "name": "Tipología identificada", "fired": typ["primary"] != MISSING,
         "detail": f"{typ['primary']} · familia {typ['family']}"},
    ]
    data = {
        "payment_id": tx_id,
        "amount": tx.get("Amount", MISSING),
        "currency": tx.get("Payment_currency", MISSING),
        "status": STATUS[v["verdict"]],
        "method": tx.get("Payment_type", MISSING),
        "brand": MISSING, "last4": MISSING,
        "customer": {"name": MISSING, "email": MISSING, "doc": MISSING,
                     "account": tx.get("Sender_account", MISSING)},
        "merchant": f"Cuenta {tx['Receiver_account']}" if "Receiver_account" in tx else MISSING,
        "order_id": MISSING,
        "risk_score": score,
        "ip": MISSING,
        "country": tx.get("Sender_bank_location", MISSING),
        "history": [
            {"status": "created", "at": f"{tx.get('Date', MISSING)}T{tx.get('Time', MISSING)}",
             "note": "Transacción registrada"},
            {"status": STATUS[v["verdict"]], "at": now, "note": v["recommendation"]},
        ],
        "failure_code": "aml_suspected" if v["verdict"] == "REJECT" else MISSING,
        "failure_message": v["recommendation"] if v["verdict"] == "REJECT" else MISSING,
    }
    context = {
        "outcome": OUTCOME[v["verdict"]],
        "verdict": v["recommendation"],
        "decidedBy": {"kind": "agent", "name": "aml-transaction-reviewer",
                      "detail": f"{result['model']} · binary_v1 {model_out.get('band', MISSING)}"},
        "accountable": {"name": MISSING, "role": MISSING},
        "confidence": v["confidence"],
        "policy": MISSING,
        "base": score,
        "factors": factors,
        "rules": rules,
        "appeal": MISSING,
        "audit": result["audit"],
        "aml": v,          # veredicto completo; quitar si la API no acepta campos extra
    }
    return {"event": {"id": f"evt_aml_{tx_id}", "type": "transaction.reviewed",
                      "created_at": now, "data": data}, "context": context}


def send(events: list[dict], url: str | None = None, token: str | None = None) -> dict:
    url = (url or os.environ.get("DETALERT_URL", "https://detalert.vercel.app")).rstrip("/") + "/api/ingest"
    token = token or os.environ["INGEST_TOKEN"]
    req = urllib.request.Request(url, data=json.dumps({"events": events}, default=str).encode(),
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return {"status": r.status, "body": r.read().decode()}