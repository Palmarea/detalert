-- Ciclo de feedback del agente: solo agrega (idempotente); el código en vivo sigue funcionando igual.
-- - aml.feedback deja de depender de aml.cases: acepta casos de /score/live y sobrevive a re-exports.
-- - Columnas nuevas opcionales para reentrenar y trazar versiones.
-- - aml.threshold_proposals: propuestas de umbral del agente (las revisa python -m aml.review_proposals).

ALTER TABLE aml.feedback DROP CONSTRAINT IF EXISTS feedback_case_id_fkey;
ALTER TABLE aml.feedback ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'cases'
    CHECK (origin IN ('cases', 'score_live'));
ALTER TABLE aml.feedback ADD COLUMN IF NOT EXISTS case_score DOUBLE PRECISION;
ALTER TABLE aml.feedback ADD COLUMN IF NOT EXISTS model_version TEXT;
ALTER TABLE aml.feedback ADD COLUMN IF NOT EXISTS threshold_version TEXT;
ALTER TABLE aml.feedback ADD COLUMN IF NOT EXISTS agent_payload JSONB;
CREATE INDEX IF NOT EXISTS feedback_received ON aml.feedback (received_at);

CREATE TABLE IF NOT EXISTS aml.threshold_proposals (
    seq                    SERIAL UNIQUE,
    proposal_id            TEXT GENERATED ALWAYS AS ('P-' || lpad(seq::text, 3, '0')) STORED PRIMARY KEY,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    status                 TEXT NOT NULL CHECK (status IN ('pending', 'blocked', 'passed', 'rejected', 'applied')),
    title                  TEXT NOT NULL,
    sub                    TEXT NOT NULL DEFAULT '',
    ask                    JSONB NOT NULL,   -- ["auto"|"high", valor vigente, valor pedido]
    reason                 TEXT NOT NULL,
    from_snapshot          JSONB NOT NULL,   -- {a, h, auto, high}
    to_snapshot            JSONB,
    guards                 JSONB,            -- [[límite, regla, antes → después, cumple]]
    evidence               JSONB NOT NULL,   -- [[case_id, case_score, banda modelo, banda agente, por qué]]
    log                    JSONB NOT NULL,   -- [[quién, qué, hora]]
    base_threshold_version TEXT NOT NULL,
    applied_version        TEXT
);
ALTER TABLE aml.threshold_proposals ENABLE ROW LEVEL SECURITY;
