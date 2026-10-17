"""Contrato del veredicto. Se usa como input_schema de la herramienta `submit_verdict`,
lo que obliga a Claude a devolver exactamente esta estructura."""

MISSING = "---"

_SIGNAL = {"type": "object", "properties": {
    "signal": {"type": "string"}, "evidence": {"type": "string"},
    "points": {"type": "integer", "minimum": -30, "maximum": 40}},
    "required": ["signal", "evidence", "points"]}

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "transaction_id": {"type": "string"},
        "verdict": {"type": "string", "enum": ["APPROVE", "ESCALATE", "REJECT"]},
        "is_laundering_suspected": {"type": "boolean"},
        "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        "model": {"type": "object", "properties": {
            "p_laundering": {"type": "number"}, "band": {"type": "string"},
            "family": {"type": "string"}, "family_source": {"type": "string"},
            "agrees_with_evidence": {"type": "boolean"}},
            "required": ["p_laundering", "band", "agrees_with_evidence"]},
        "investigation": {"type": "object", "properties": {
            "expanded_sender": {"type": "boolean"}, "expanded_receiver": {"type": "boolean"},
            "expansion_reason": {"type": "string"},
            "tools_used": {"type": "array", "items": {"type": "string"}}},
            "required": ["expanded_sender", "expanded_receiver", "expansion_reason"]},
        "typology": {"type": "object", "properties": {
            "primary": {"type": "string", "description": "Tipología SAML-D más probable o '---'"},
            "family": {"type": "string",
                       "enum": ["structuring", "layering", "concentration", "cash", "behavioural", "generic", MISSING]},
            "candidates": {"type": "array", "items": {"type": "string"}}},
            "required": ["primary", "family"]},
        "red_flags": {"type": "array", "items": _SIGNAL},
        "mitigating_factors": {"type": "array", "items": _SIGNAL},
        "reasoning": {"type": "array", "items": {"type": "string"}, "minItems": 2},
        "recommendation": {"type": "string"},
        "narrative": {"type": "string"},
        "missing_info": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["transaction_id", "verdict", "is_laundering_suspected", "risk_level", "confidence",
                 "model", "investigation", "typology", "red_flags", "mitigating_factors",
                 "reasoning", "recommendation", "narrative", "missing_info"],
}

SUBMIT_TOOL = {"name": "submit_verdict",
               "description": "Entrega el veredicto final de la revisión AML. Llamar una sola vez, al final.",
               "input_schema": VERDICT_SCHEMA}


def validate_verdict(v: dict, model_input: dict) -> list[str]:
    """Reglas duras que no dependen del LLM. Devuelve la lista de violaciones."""
    errors = [f"falta '{k}'" for k in VERDICT_SCHEMA["required"] if k not in v]
    if errors:
        return errors
    band = model_input.get("band")
    if v["verdict"] == "APPROVE" and band == "high_priority":
        errors.append("APPROVE no permitido con band=high_priority")
    if v["verdict"] == "REJECT":
        strong = [f for f in v["red_flags"] if f.get("points", 0) > 0 and f.get("evidence", MISSING) != MISSING]
        if len(strong) < 2:
            errors.append("REJECT requiere al menos 2 red flags con evidencia")
        if not (v["investigation"]["expanded_sender"] or v["investigation"]["expanded_receiver"]):
            errors.append("REJECT requiere haber investigado el historial")
    return errors