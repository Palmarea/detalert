"""API de scoring AML.

Backend por variable de entorno:
    AML_BACKEND=mock      datos falsos deterministas (default)
    AML_BACKEND=postgres  data real; requiere DATABASE_URL
Opcional: AML_API_KEY -> exige header `X-API-Key` en todo salvo /health y /docs.

Local:
    uvicorn aml.api.main:app --reload
"""

import os
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from aml.api.backend import AgentCannotLowerBand, Backend
from aml.api.schemas import (
    AccountScore, AuditRecord, Band, CaseDetail, CaseList, FeedbackAck, FeedbackIn, Health, Mode,
    ModelMetrics, ScoreRequest, ScoreResponse, Thresholds,
)


@lru_cache
def get_backend() -> Backend:
    kind = os.getenv("AML_BACKEND", "mock")
    if kind == "postgres":
        from aml.api.pg import PostgresBackend
        return PostgresBackend()
    from aml.api.mock import MockBackend
    return MockBackend()


def require_key(x_api_key: str | None = Header(None)) -> None:
    expected = os.getenv("AML_API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(401, "X-API-Key inválida o ausente")


app = FastAPI(
    title="AML Scoring API",
    version="1.0.0",
    description=(
        "Scoring de transacciones y casos para el agente investigador y la bandeja del analista.\n\n"
        "**Regla del contrato:** el agente puede subir la banda que devuelve el modelo, nunca bajarla."
    ),
)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("AML_CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])
protected = [Depends(require_key)]


@app.get("/health", response_model=Health, tags=["sistema"])
def health(b: Backend = Depends(get_backend)):
    return Health(status="ok", backend=b.name, model_version=b.model_version, threshold_version=b.threshold_version)


@app.post("/score/transactions", response_model=ScoreResponse, dependencies=protected, tags=["scoring"])
def score_transactions(req: ScoreRequest, b: Backend = Depends(get_backend)):
    """Score calibrado, banda, familia y reason codes por transacción."""
    return b.score(req.txn_ids)


@app.get("/cases", response_model=CaseList, dependencies=protected, tags=["casos"])
def list_cases(
    mode: Mode = Mode.normal,
    band: Band | None = None,
    family: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    b: Backend = Depends(get_backend),
):
    """Casos ordenados por prioridad. La banda depende del `mode` (capacidad de analistas)."""
    return b.list_cases(mode, limit, offset, band, family)


@app.get("/cases/{case_id}", response_model=CaseDetail, dependencies=protected, tags=["casos"])
def get_case(case_id: str, mode: Mode = Mode.normal, b: Backend = Depends(get_backend)):
    c = b.get_case(case_id, mode)
    if c is None:
        raise HTTPException(404, f"Caso {case_id} no existe")
    return c


@app.get("/score/account/{account}", response_model=AccountScore, dependencies=protected, tags=["scoring"])
def account_score(account: str, start: datetime = Query(alias="from"), end: datetime = Query(alias="to"),
                  b: Backend = Depends(get_backend)):
    # Fechas sin zona horaria se interpretan como UTC (los ts de la data están en UTC).
    start, end = (d if d.tzinfo else d.replace(tzinfo=timezone.utc) for d in (start, end))
    r = b.account_score(account, start, end)
    if r is None:
        raise HTTPException(404, "Sin transacciones puntuadas para esa cuenta y ventana")
    return r


@app.get("/thresholds", response_model=Thresholds, dependencies=protected, tags=["modelo"])
def thresholds(b: Backend = Depends(get_backend)):
    """Puntos de operación (normal / capacidad reducida / sin analista) con su costo esperado."""
    return b.thresholds()


@app.get("/model/metrics", response_model=ModelMetrics, dependencies=protected, tags=["modelo"])
def metrics(b: Backend = Depends(get_backend)):
    return b.metrics()


@app.get("/audit/{txn_id}", response_model=AuditRecord, dependencies=protected, tags=["trazabilidad"])
def audit(txn_id: int, b: Backend = Depends(get_backend)):
    """Registro completo: snapshot de features, score crudo y calibrado, versiones."""
    r = b.audit(txn_id)
    if r is None:
        raise HTTPException(404, f"Transacción {txn_id} sin registro de auditoría")
    return r


@app.post("/feedback", response_model=FeedbackAck, status_code=201, dependencies=protected, tags=["feedback"])
def feedback(fb: FeedbackIn, b: Backend = Depends(get_backend)):
    """Decisión del agente o del analista. Rechaza (422) si el agente intenta bajar la banda del modelo."""
    try:
        return b.feedback(fb)
    except KeyError:
        raise HTTPException(404, f"Caso {fb.case_id} no existe")
    except AgentCannotLowerBand as e:
        raise HTTPException(422, str(e))
