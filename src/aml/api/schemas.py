"""Contrato de la API de scoring AML (compartido con el equipo del agente y la bandeja).

Reglas del contrato:
- `band` la decide el modelo con umbrales versionados. El agente puede SUBIR la
  banda (p. ej. review -> high_priority) pero nunca BAJARLA.
- `p_laundering` es una probabilidad calibrada (Platt): 0.02 significa ~2% de
  probabilidad de lavado en la población real.
- Toda respuesta trae `model_version` y `threshold_version` para trazabilidad.
"""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Band(str, Enum):
    auto_close_eligible = "auto_close_eligible"
    review = "review"
    high_priority = "high_priority"


class Family(str, Enum):
    structuring = "structuring"
    layering = "layering"
    concentration = "concentration"
    cash = "cash"
    behavioural = "behavioural"
    generic = "generic"  # confianza del clasificador de familia < 0.5 -> agente general


class Mode(str, Enum):
    normal = "normal"
    reduced_capacity = "reduced_capacity"
    no_analyst = "no_analyst"


class ReasonCode(BaseModel):
    code: str = Field(examples=["NEW_COUNTERPARTY"])
    feature: str = Field(examples=["is_new_counterparty"])
    value: float | str | None = Field(examples=[1])
    contribution: float = Field(description="Contribución SHAP al log-odds", examples=[2.31])
    text: str = Field(examples=["Primera transacción hacia esta contraparte"])


class Versions(BaseModel):
    model_version: str = Field(examples=["binary_v1"])
    threshold_version: str = Field(examples=["thresholds_v1"])


class TxnScore(Versions):
    txn_id: int
    ts: datetime
    sender_account: str
    receiver_account: str
    amount: float
    payment_type: str
    p_laundering: float = Field(ge=0, le=1)
    band: Band
    family: Family
    family_confidence: float = Field(ge=0, le=1)
    reason_codes: list[ReasonCode]


class ScoreRequest(BaseModel):
    txn_ids: list[int] = Field(min_length=1, max_length=1000, examples=[[7227174, 7259972]])


PaymentType = Literal["ACH", "Cash Deposit", "Cash Withdrawal", "Cheque", "Credit card", "Cross-border", "Debit card"]


class LiveTransaction(BaseModel):
    """Transacción nueva a puntuar en vivo. Las features se calculan con el historial
    de ambas cuentas estrictamente anterior a `ts`."""
    model_config = {"json_schema_extra": {"examples": [{
        "ts": "2023-08-10T05:15:22Z", "sender_account": "6812204903", "receiver_account": "5440521221",
        "amount": 6248.44, "payment_type": "Cross-border", "payment_currency": "UK pounds",
        "received_currency": "Euro", "sender_bank_location": "UK", "receiver_bank_location": "France"}]}}

    ts: datetime | None = Field(None, description="Momento de la transacción. Si se omite: justo después del "
                                                   "final del historial (2023-08-23), como 'ahora' en la demo.")
    sender_account: str
    receiver_account: str
    amount: float = Field(gt=0)
    payment_type: PaymentType
    payment_currency: str
    received_currency: str
    sender_bank_location: str | None = None
    receiver_bank_location: str | None = None


class LiveScore(Versions):
    ts: datetime
    p_laundering: float = Field(ge=0, le=1)
    score_raw: float
    band: Band
    family: Family
    family_confidence: float = Field(ge=0, le=1)
    reason_codes: list[ReasonCode]
    features: dict[str, float | int | str | None] = Field(
        description="Features calculadas en vivo (trazabilidad: lo que vio el modelo)")
    warnings: list[str] = []


class ScoreResponse(BaseModel):
    results: list[TxnScore]
    not_found: list[int] = []


class CaseSummary(Versions):
    case_id: str = Field(examples=["C-8724731955-2023-06-05"])
    account: str
    window_start: datetime
    window_end: datetime
    n_transactions: int
    n_flagged: int
    total_amount_flagged: float
    case_score: float = Field(ge=0, le=1, description="Probabilidad calibrada a nivel caso")
    band: Band
    family: Family
    priority_rank: int = Field(description="1 = el más urgente dentro del modo pedido")


class CaseDetail(CaseSummary):
    transactions: list[TxnScore]
    top_reason_codes: list[ReasonCode]


class CaseList(BaseModel):
    mode: Mode
    total: int
    cases: list[CaseSummary]


class AccountScore(Versions):
    account: str
    window_start: datetime
    window_end: datetime
    n_transactions: int
    max_p_laundering: float
    mean_p_laundering: float
    n_flagged: int
    band: Band


class OperatingPoint(BaseModel):
    mode: Mode
    analyst_capacity_pct: int = Field(examples=[100])
    auto_close_threshold: float = Field(description="case_score por debajo -> auto_close_eligible")
    high_priority_threshold: float
    auto_close_rate: float = Field(description="% de casos que se cierran solos")
    expected_leakage: float = Field(description="% de casos auto-cerrados que eran lavado")
    missed_laundering_pct: float | None = Field(
        None, description="% de los casos de lavado que este modo auto-cierra (lo que se escapa)")
    queue_cases_per_day: float
    preventive_hold: bool = Field(description="True: high_priority retiene la transacción mientras no haya analista")


class Thresholds(BaseModel):
    threshold_version: str
    alert_threshold: float = Field(description="p_laundering mínima para que una transacción entre a un caso")
    operating_points: list[OperatingPoint]


class FunnelStage(BaseModel):
    stage: str
    n_in: int
    n_out: int
    positives_out: int
    leakage: float


class ModelMetrics(Versions):
    sample: str = Field(examples=["oot"])
    gini: float
    ks: float
    pr_auc: float
    recall_at_1pct: float
    baseline_gini: float
    recall_by_typology: dict[str, float]
    funnel: list[FunnelStage]


class AuditRecord(Versions):
    txn_id: int
    scored_at: datetime
    features_snapshot: dict[str, float | str | None]
    score_raw: float
    p_laundering: float
    band: Band
    family: Family
    reason_codes: list[ReasonCode]


class Actor(str, Enum):
    agent = "agent"
    analyst = "analyst"


class Decision(str, Enum):
    auto_closed = "auto_closed"
    escalated = "escalated"
    high_priority = "high_priority"
    approved = "approved"      # analista confirma la decisión del agente
    rejected = "rejected"      # analista revierte la decisión del agente
    sar_filed = "sar_filed"    # reporte de operación sospechosa emitido


class FeedbackIn(BaseModel):
    case_id: str
    actor: Actor
    decision: Decision
    agent_band: Band | None = Field(None, description="Banda final del agente (solo puede ser >= la del modelo)")
    notes: str | None = None


class FeedbackAck(BaseModel):
    feedback_id: str
    received_at: datetime


class Health(Versions):
    status: str = Field(examples=["ok"])
    backend: str = Field(examples=["mock"])
