"""Interfaz de backend y reglas de negocio compartidas (bandas, modos, validación del agente).

La banda NO se guarda: se deriva del score con los umbrales del modo pedido, así
el mismo caso puede ser `review` en modo normal y `auto_close_eligible` o
`high_priority` en otro modo, sin reprocesar nada.
"""

from datetime import datetime
from typing import Protocol

from aml.api.schemas import (
    AccountScore, AuditRecord, Band, CaseDetail, CaseList, FeedbackAck, FeedbackIn,
    Mode, ModelMetrics, OperatingPoint, ScoreResponse, Thresholds,
)

BAND_ORDER = {Band.auto_close_eligible: 0, Band.review: 1, Band.high_priority: 2}


def band_for(score: float, op: OperatingPoint) -> Band:
    if score >= op.high_priority_threshold:
        return Band.high_priority
    if score < op.auto_close_threshold:
        return Band.auto_close_eligible
    return Band.review


def operating_point(th: Thresholds, mode: Mode) -> OperatingPoint:
    return next(op for op in th.operating_points if op.mode == mode)


class AgentCannotLowerBand(ValueError):
    pass


def check_agent_band(model_band: Band, fb: FeedbackIn) -> None:
    if fb.agent_band is not None and BAND_ORDER[fb.agent_band] < BAND_ORDER[model_band]:
        raise AgentCannotLowerBand(
            f"El agente no puede bajar la banda: modelo={model_band.value}, agente={fb.agent_band.value}"
        )


class Backend(Protocol):
    name: str
    model_version: str
    threshold_version: str

    def thresholds(self) -> Thresholds: ...
    def score(self, txn_ids: list[int]) -> ScoreResponse: ...
    def list_cases(self, mode: Mode, limit: int, offset: int, band: Band | None, family: str | None) -> CaseList: ...
    def get_case(self, case_id: str, mode: Mode) -> CaseDetail | None: ...
    def account_score(self, account: str, start: datetime, end: datetime) -> AccountScore | None: ...
    def metrics(self) -> ModelMetrics: ...
    def audit(self, txn_id: int) -> AuditRecord | None: ...
    def feedback(self, fb: FeedbackIn) -> FeedbackAck: ...
