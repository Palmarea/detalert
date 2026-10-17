-- Esquema Postgres que sirve la API de scoring AML.
-- Lo llena el batch local (python -m aml.export); la API solo lee, salvo feedback.

CREATE SCHEMA IF NOT EXISTS aml;

-- Transacciones puntuadas que la API expone (alertadas y las de cada caso).
CREATE TABLE IF NOT EXISTS aml.txn_scores (
    txn_id            BIGINT PRIMARY KEY,
    ts                TIMESTAMPTZ NOT NULL,
    sender_account    TEXT NOT NULL,
    receiver_account  TEXT NOT NULL,
    amount            DOUBLE PRECISION NOT NULL,
    payment_type      TEXT NOT NULL,
    score_raw         DOUBLE PRECISION NOT NULL,
    p_laundering      DOUBLE PRECISION NOT NULL,
    family            TEXT NOT NULL,
    family_confidence DOUBLE PRECISION NOT NULL,
    reason_codes      JSONB NOT NULL,
    features_snapshot JSONB NOT NULL,
    case_id           TEXT,
    scored_at         TIMESTAMPTZ NOT NULL,
    model_version     TEXT NOT NULL,
    threshold_version TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS txn_scores_sender_ts ON aml.txn_scores (sender_account, ts);
CREATE INDEX IF NOT EXISTS txn_scores_case ON aml.txn_scores (case_id);

CREATE TABLE IF NOT EXISTS aml.cases (
    case_id              TEXT PRIMARY KEY,
    account              TEXT NOT NULL,
    window_start         TIMESTAMPTZ NOT NULL,
    window_end           TIMESTAMPTZ NOT NULL,
    n_transactions       INT NOT NULL,
    n_flagged            INT NOT NULL,
    total_amount_flagged DOUBLE PRECISION NOT NULL,
    case_score           DOUBLE PRECISION NOT NULL,
    family               TEXT NOT NULL,
    top_reason_codes     JSONB NOT NULL,
    model_version        TEXT NOT NULL,
    threshold_version    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS cases_score ON aml.cases (case_score DESC);

-- Documentos JSON: 'thresholds' (schemas.Thresholds) y 'metrics' (schemas.ModelMetrics).
CREATE TABLE IF NOT EXISTS aml.meta (
    key   TEXT PRIMARY KEY,
    value JSONB NOT NULL
);

-- Decisiones del agente y del analista: alimenta reentrenamiento y evaluación del agente.
CREATE TABLE IF NOT EXISTS aml.feedback (
    feedback_id UUID PRIMARY KEY,
    case_id     TEXT NOT NULL REFERENCES aml.cases (case_id),
    actor       TEXT NOT NULL CHECK (actor IN ('agent', 'analyst')),
    decision    TEXT NOT NULL,
    model_band  TEXT NOT NULL,
    agent_band  TEXT,
    notes       TEXT,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS feedback_case ON aml.feedback (case_id);

-- Defensa en profundidad (Supabase): el esquema aml no se expone por la API REST,
-- pero igual se activa RLS sin políticas; solo el rol dueño (el que usa FastAPI) accede.
ALTER TABLE aml.txn_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE aml.cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE aml.meta ENABLE ROW LEVEL SECURITY;
ALTER TABLE aml.feedback ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON SCHEMA aml FROM anon, authenticated;
    END IF;
END $$;
