"""Loop del agente: Claude decide qué herramientas llamar y termina con `submit_verdict`."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schema import MISSING, SUBMIT_TOOL, validate_verdict
from .tools import REGISTRY, TOOL_SPECS

SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system.md").read_text(encoding="utf-8")
MODEL = os.environ.get("AML_AGENT_MODEL", "claude-sonnet-5-5")
MAX_STEPS = int(os.environ.get("AML_AGENT_MAX_STEPS", "10"))
TX_FIELDS = ["Time", "Date", "Sender_account", "Receiver_account", "Amount", "Payment_currency",
             "Received_currency", "Sender_bank_location", "Receiver_bank_location", "Payment_type"]


def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:8]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_user_message(tx: dict, model_out: dict, tx_id: str) -> str:
    clean = {k: tx.get(k, MISSING) for k in TX_FIELDS}          # etiqueta excluida a propósito
    mo = {"p_laundering": model_out.get("p_laundering", MISSING),
          "band": model_out.get("band", MISSING),
          "family": model_out.get("family", MISSING),
          "family_source": model_out.get("family_source", "mock"),
          "thresholds_version": model_out.get("thresholds_version", MISSING)}
    until = f"{clean['Date']}T{clean['Time']}"
    return (f"transaction_id: {tx_id}\nuntil (usar en las herramientas): {until}\n\n"
            f"Transacción:\n{json.dumps(clean, ensure_ascii=False, indent=2)}\n\n"
            f"Salida del modelo binary_v1:\n{json.dumps(mo, ensure_ascii=False, indent=2)}\n\n"
            "Revisa, decide si expandir al emisor/receptor y termina llamando submit_verdict.")


def review(tx: dict, model_out: dict, tx_id: str, client=None) -> dict:
    """Devuelve {'verdict': {...}, 'audit': [...], 'violations': [...], 'model': str}."""
    if client is None:
        import anthropic
        client = anthropic.Anthropic()          # usa ANTHROPIC_API_KEY del entorno

    audit = [{"at": _now(), "actor": "Sistema", "action": f"Transacción {tx_id} recibida para revisión",
              "hash": _hash(tx)}]
    messages = [{"role": "user", "content": build_user_message(tx, model_out, tx_id)}]
    tools = TOOL_SPECS + [SUBMIT_TOOL]

    for step in range(MAX_STEPS):
        force = step == MAX_STEPS - 1
        resp = client.messages.create(
            model=MODEL, max_tokens=4096, system=SYSTEM_PROMPT, tools=tools, messages=messages,
            tool_choice={"type": "tool", "name": "submit_verdict"} if force else {"type": "auto"})
        messages.append({"role": "assistant", "content": resp.content})

        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            if block.name == "submit_verdict":
                verdict = dict(block.input)
                violations = validate_verdict(verdict, model_out)
                if violations and not force:
                    results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                    "content": "Veredicto rechazado por reglas: " + "; ".join(violations)
                                               + ". Corrige y vuelve a llamar submit_verdict."})
                    audit.append({"at": _now(), "actor": "Validador", "action": "Veredicto devuelto: "
                                  + "; ".join(violations), "hash": _hash(verdict)})
                    continue
                if violations:                     # último intento: degradar a ESCALATE, nunca aprobar/rechazar mal
                    verdict["verdict"] = "ESCALATE"
                    verdict.setdefault("missing_info", []).append("Veredicto degradado: " + "; ".join(violations))
                audit.append({"at": _now(), "actor": "aml-transaction-reviewer",
                              "action": f"Veredicto {verdict['verdict']} emitido", "hash": _hash(verdict)})
                return {"verdict": verdict, "audit": audit, "violations": violations, "model": MODEL}
            fn = REGISTRY.get(block.name)
            try:
                out = fn(**block.input) if fn else {"error": f"herramienta desconocida {block.name}"}
                err = False
            except Exception as e:                  # el agente ve el error y puede reintentar
                out, err = {"error": str(e)}, True
            audit.append({"at": _now(), "actor": "aml-transaction-reviewer",
                          "action": f"{block.name}({json.dumps(block.input, ensure_ascii=False)})",
                          "hash": _hash(out)})
            results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": err,
                            "content": json.dumps(out, ensure_ascii=False, default=str)})
        if not results:
            messages.append({"role": "user", "content": "Termina llamando submit_verdict."})
        else:
            messages.append({"role": "user", "content": results})

    raise RuntimeError("El agente no emitió veredicto")