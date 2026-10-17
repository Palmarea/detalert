"""Modo offline: reemplaza a Claude por reglas fijas, sin API key.

Implementa la misma interfaz que el cliente (messages.create) y sigue la política de prompts/system.md:
decide qué herramientas llamar, junta evidencia y emite `submit_verdict`. No es IA: es un motor de reglas
que sirve como respaldo y para demos sin conexión a la API.
"""
from __future__ import annotations

import json

from .schema import MISSING

PAISES_ALTO_RIESGO = {"Mexico", "Turkey", "Morocco", "UAE", "Nigeria", "Pakistan"}
CASH = {"Cash Deposit", "Cash Withdrawal"}
UMBRAL = 10_000
FAMILIA = {"Cycle": "layering", "Fan_Out": "layering", "Fan_In": "concentration",
           "Structuring": "structuring", "Deposit-Send": "cash", "Single_large": "behavioural",
           "Behavioural_Change_1": "behavioural", MISSING: MISSING}


class _Obj(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


def _tool(i, name, inp):
    return _Obj(type="tool_use", id=f"off_{i}", name=name, input=inp)


class OfflineClient:
    def __init__(self, tx: dict, model_out: dict, tx_id: str):
        self.tx, self.mo, self.tx_id = tx, model_out, tx_id
        self.until = f"{tx['Date']}T{tx['Time']}"
        self.calls: dict[str, dict] = {}
        self.step = 0
        self.messages = self

    # ---------------------------------------------------------------- interfaz
    def create(self, **kw):
        self.step += 1
        if self.step == 1:
            return _Obj(content=self._plan())
        self._read_results(kw["messages"])
        return _Obj(content=[_tool(99, "submit_verdict", self._verdict())])

    # ---------------------------------------------------------------- paso 1: qué investigar
    def _hard_flags(self):
        t = self.tx
        return {
            "cross_border": t["Sender_bank_location"] != t["Receiver_bank_location"],
            "cambio_moneda": t["Payment_currency"] != t["Received_currency"],
            "efectivo": t["Payment_type"] in CASH,
            "pais_riesgo": bool({t["Sender_bank_location"], t["Receiver_bank_location"]} & PAISES_ALTO_RIESGO),
            "bajo_umbral": UMBRAL * 0.9 <= float(t["Amount"]) < UMBRAL,
        }

    def _plan(self):
        band, hard = self.mo.get("band"), self._hard_flags()
        s, r = self.tx["Sender_account"], self.tx["Receiver_account"]
        self.exp_sender = band != "auto_close_eligible" or any(hard.values())
        self.exp_receiver = band == "high_priority" or (band == "review" and hard["cross_border"])
        motivos = [f"band={band}"] + [k for k, v in hard.items() if v]
        self.reason = ("Se expande: " if self.exp_sender else "No se expande: ") + ", ".join(motivos)
        plan = []
        if self.exp_sender:
            plan += [("get_account_profile", {"account": s, "until": self.until}),
                     ("get_network_signals", {"account": s, "until": self.until, "days": 30})]
        if self.exp_receiver:
            plan += [("get_account_profile", {"account": r, "until": self.until}),
                     ("get_network_signals", {"account": r, "until": self.until, "days": 30})]
        self._order = [(n, i["account"]) for n, i in plan]
        return [_Obj(type="text", text=self.reason)] + [_tool(i, n, inp) for i, (n, inp) in enumerate(plan)]

    def _read_results(self, messages):
        results = messages[-1]["content"] if isinstance(messages[-1]["content"], list) else []
        for (name, acc), res in zip(self._order, results):
            try:
                self.calls[f"{name}:{acc}"] = json.loads(res["content"])
            except (ValueError, KeyError, TypeError):
                self.calls[f"{name}:{acc}"] = {}

    # ---------------------------------------------------------------- paso 2: evidencia y veredicto
    def _verdict(self):
        t, mo, hard = self.tx, self.mo, self._hard_flags()
        s, r, amt = t["Sender_account"], t["Receiver_account"], float(t["Amount"])
        flags, mitig, steps, typ = [], [], [], []

        def add(lst, sig, ev, pts, ty=None):
            lst.append({"signal": sig, "evidence": ev, "points": pts})
            if ty:
                typ.append(ty)

        p = mo.get("p_laundering", MISSING)
        steps.append(f"Modelo binary_v1: p_laundering={p}, banda {mo.get('band')}; familia "
                     f"{mo.get('family', MISSING)} ({mo.get('family_source', 'mock')}, solo pista).")
        steps.append(self.reason + ".")

        if hard["cross_border"]:
            add(flags, "Transferencia cross-border", f"{t['Sender_bank_location']} → {t['Receiver_bank_location']}", 8)
        if hard["cambio_moneda"]:
            add(flags, "Cambio de moneda", f"{t['Payment_currency']} → {t['Received_currency']}", 6)
        if hard["efectivo"]:
            add(flags, "Operación en efectivo", t["Payment_type"], 8, "Deposit-Send")
        if hard["pais_riesgo"]:
            add(flags, "País de alto riesgo", f"{t['Sender_bank_location']} / {t['Receiver_bank_location']}", 10)
        if hard["bajo_umbral"]:
            add(flags, "Monto justo bajo el umbral de reporte", f"{amt:,.2f} vs umbral {UMBRAL:,}", 15, "Structuring")

        hist_flags = 0
        for acc, rol in ((s, "emisor"), (r, "receptor")):
            prof = self.calls.get(f"get_account_profile:{acc}")
            net = self.calls.get(f"get_network_signals:{acc}")
            if prof:
                e = prof.get("como_emisor", {})
                med = e.get("mediana")
                if prof.get("cuenta_nueva"):
                    add(flags, f"Cuenta {rol} sin historial previo", f"cuenta {acc}: 0 transacciones antes", 5)
                elif rol == "emisor" and med and amt > 5 * med:
                    add(flags, "Monto muy superior al perfil", f"{amt:,.2f} = {amt / med:.1f}x la mediana ({med:,.2f})",
                        15, "Single_large"); hist_flags += 1
                elif rol == "emisor" and med and (e.get("n_tx") or 0) >= 20 and amt <= 2 * med:
                    add(mitig, "Monto coherente con el perfil", f"{e['n_tx']} tx previas, mediana {med:,.2f}", -10)
                steps.append(f"Perfil {rol} {acc}: {e.get('n_tx', 0)} envíos previos, mediana {med}, "
                             f"{prof.get('como_receptor', {}).get('n_tx', 0)} recepciones.")
            if net:
                c = (net.get("ciclos_2_saltos") or 0) + (net.get("ciclos_3_saltos") or 0)
                if c:
                    add(flags, "Flujo circular", f"cuenta {acc}: {c} ciclo(s) de 2–3 saltos en 30 días", 25, "Cycle")
                    hist_flags += 1
                if (net.get("fan_out") or 0) >= 5:
                    add(flags, "Fan-out", f"cuenta {acc} envió a {net['fan_out']} cuentas distintas en 30 días", 12,
                        "Fan_Out"); hist_flags += 1
                if (net.get("fan_in") or 0) >= 5:
                    add(flags, "Fan-in", f"cuenta {acc} recibió de {net['fan_in']} cuentas distintas en 30 días", 12,
                        "Fan_In"); hist_flags += 1
                rp = net.get("ratio_paso")
                if rp and rp > 0.9 and (net.get("entra") or 0) > UMBRAL:
                    add(flags, "Cuenta puente (pass-through)",
                        f"cuenta {acc}: entra {net['entra']:,.2f} y sale {net['sale']:,.2f} (ratio {rp})", 18)
                    hist_flags += 1
                steps.append(f"Red {rol} {acc} (30 d): fan-out {net.get('fan_out')}, fan-in {net.get('fan_in')}, "
                             f"ratio de paso {rp}, ciclos {c}.")

        score = sum(f["points"] for f in flags) + sum(m["points"] for m in mitig)
        band = mo.get("band")
        high = band == "high_priority" or (isinstance(p, (int, float)) and p >= 0.8)
        if high and len(flags) >= 2 and hist_flags >= 1 and score >= 40:
            verdict, rec = "REJECT", "Rechazar la transacción y reportar: patrón de lavado con evidencia en el historial."
        elif band != "high_priority" and score < (15 if band == "auto_close_eligible" else 10):
            verdict, rec = "APPROVE", "Aprobar: sin evidencia de lavado en la transacción ni en el historial."
        else:
            verdict, rec = "ESCALATE", "Escalar a analista: hay señales de riesgo que requieren revisión humana."
        risk = "critical" if score >= 60 else "high" if score >= 35 else "medium" if score >= 15 else "low"
        prioridad = ["Cycle", "Fan_Out", "Fan_In", "Structuring", "Deposit-Send", "Single_large"]
        typ = sorted(dict.fromkeys(typ), key=lambda x: prioridad.index(x) if x in prioridad else 99)
        primary = typ[0] if typ else MISSING
        agrees = (verdict != "APPROVE") == high or band == "review"
        steps.append(f"Puntaje de evidencia {score} con {len(flags)} red flags ({hist_flags} del historial) → {verdict}.")
        if not agrees:
            steps.append("El modelo y la evidencia no coinciden; prevalece la evidencia.")

        narrative = (f"Transacción {self.tx_id} de {amt:,.2f} {t['Payment_currency']} desde la cuenta {s} "
                     f"({t['Sender_bank_location']}) hacia {r} ({t['Receiver_bank_location']}) vía {t['Payment_type']}. "
                     f"El modelo la ubicó en la banda {band} (p={p}). "
                     + (f"Se identificaron {len(flags)} señales: " + "; ".join(f["signal"].lower() for f in flags) + ". "
                        if flags else "No se identificaron señales de riesgo. ")
                     + (f"Tipología más probable: {primary}. " if primary != MISSING else "")
                     + f"Recomendación: {rec}")
        return {
            "transaction_id": self.tx_id, "verdict": verdict, "is_laundering_suspected": verdict != "APPROVE",
            "risk_level": risk, "confidence": 85 if verdict in ("REJECT", "APPROVE") else 60,
            "model": {"p_laundering": p, "band": band, "family": mo.get("family", MISSING),
                      "family_source": mo.get("family_source", "mock"), "agrees_with_evidence": agrees},
            "investigation": {"expanded_sender": self.exp_sender, "expanded_receiver": self.exp_receiver,
                              "expansion_reason": self.reason, "tools_used": sorted({k.split(':')[0] for k in self.calls})},
            "typology": {"primary": primary, "family": FAMILIA.get(primary, "generic"),
                         "candidates": typ},
            "red_flags": flags, "mitigating_factors": mitig, "reasoning": steps,
            "recommendation": rec, "narrative": narrative,
            "missing_info": ["Datos del cliente (nombre, documento): no existen en SAML-D",
                             "Modo offline: veredicto por reglas, sin modelo de lenguaje"],
        }