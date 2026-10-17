"""Reglas de las propuestas de umbral del agente (compartidas por los backends y la revisión OOT).

El agente propone; ML decide. Aquí solo se valida la forma y las reglas para no
aprender mal. La simulación con etiquetas reales vive fuera de la API
(python -m aml.review_proposals), porque la API no ve `is_laundering`.
"""

from datetime import datetime, timezone

from aml.api.schemas import Mode, OpSnapshot, ProposalIn, ProposalStatus, Thresholds

MAX_CHANGE = 0.25   # ningún cambio mayor a 25 % del valor vigente
MIN_CASES = 5       # nada se propone con menos de 5 casos
MODE = Mode.normal  # el agente solo propone sobre el modo normal


class InvalidProposal(ValueError):
    pass


def current(th: Thresholds, which: str) -> float:
    op = next(o for o in th.operating_points if o.mode == MODE)
    return op.auto_close_threshold if which == "auto" else op.high_priority_threshold


def snapshot(th: Thresholds) -> OpSnapshot:
    op = next(o for o in th.operating_points if o.mode == MODE)
    return OpSnapshot(a=round(op.auto_close_rate * 100, 1), h=None,
                      auto=op.auto_close_threshold, high=op.high_priority_threshold)


def is_relax(which: str, old: float, new: float) -> bool:
    """Relajar = menos casos para el analista: subir el cierre automático o subir prioridad alta."""
    return new > old


def validate(p: ProposalIn, th: Thresholds, known_case_ids: set[str]) -> None:
    which, old, new = p.ask
    now = current(th, which)
    if abs(old - now) > 1e-9:
        raise InvalidProposal(f"El umbral '{which}' vigente es {now}, no {old} ({th.threshold_version})")
    if new <= 0 or new >= 1 or new == old:
        raise InvalidProposal("El valor pedido debe estar en (0, 1) y ser distinto del vigente")
    if abs(new - old) / old > MAX_CHANGE:
        raise InvalidProposal(f"Cambio de {abs(new - old) / old:.0%}: el máximo es {MAX_CHANGE:.0%}")
    ids = [e[0] for e in p.evidence]
    if len(set(ids)) < MIN_CASES:
        raise InvalidProposal(f"Se necesitan al menos {MIN_CASES} casos distintos de evidencia ({len(set(ids))})")
    unknown = sorted(set(ids) - known_case_ids)
    if unknown:
        raise InvalidProposal(f"Casos de evidencia que no existen: {', '.join(unknown[:5])}")


def initial(p: ProposalIn) -> tuple[ProposalStatus, str, list[tuple[str, str, str]]]:
    which, old, new = p.ask
    t = datetime.now(timezone.utc).strftime("%H:%M")
    log = [("Agente", f"Propuso mover '{which}' de {old} a {new}" + (f": {p.reason}" if p.reason else ""), t)]
    if is_relax(which, old, new):
        reason = (f"El agente no puede relajar umbrales. Se activa con {len(p.evidence)} aprobaciones "
                  "del analista sobre los casos de evidencia.")
        log.append(("Compuerta", "Bloqueada: relajar requiere al analista", t))
        return ProposalStatus.blocked, reason, log
    log.append(("Compuerta", "En espera de la simulación OOT del equipo de ML", t))
    return ProposalStatus.pending, "Pendiente de la simulación OOT.", log
