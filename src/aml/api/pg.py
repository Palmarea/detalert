"""Backend Postgres: sirve la data real exportada por el batch local (sql/schema.sql).

Pensado para serverless (Vercel): una conexión corta por request. Con Neon o
Supabase conviene usar la URL del *pooler* en DATABASE_URL.
"""

import os
import time
import uuid
from datetime import datetime

import psycopg
from psycopg.rows import dict_row

from aml.api.backend import band_for, check_agent_band, operating_point
from aml.api.live import LiveScorer
from aml.api.reasons import top_reasons
from aml.api.schemas import (
    AccountScore, AuditRecord, Band, CaseDetail, CaseList, CaseSummary, FeedbackAck, FeedbackIn,
    LiveScore, LiveTransaction, Mode, ModelMetrics, ScoreResponse, Thresholds, TxnScore,
)

_CASE_COLS = """case_id, account, window_start, window_end, n_transactions, n_flagged,
                total_amount_flagged, case_score, family, model_version, threshold_version"""
_TXN_COLS = """txn_id, ts, sender_account, receiver_account, amount, payment_type, p_laundering,
               family, family_confidence, reason_codes, model_version, threshold_version"""
_META_TTL_S = 60


class PostgresBackend:
    name = "postgres"

    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or os.environ["DATABASE_URL"]
        self._meta_cache: dict[str, tuple[float, dict]] = {}
        self._live = LiveScorer(self._conn)

    def _conn(self):
        # prepare_threshold=None: el transaction pooler (Supabase/Neon) no soporta prepared statements.
        return psycopg.connect(self.dsn, row_factory=dict_row, autocommit=True, connect_timeout=10,
                               prepare_threshold=None)

    def _meta(self, key: str) -> dict:
        hit = self._meta_cache.get(key)
        if hit and time.time() - hit[0] < _META_TTL_S:
            return hit[1]
        with self._conn() as c:
            row = c.execute("SELECT value FROM aml.meta WHERE key = %s", (key,)).fetchone()
        if row is None:
            raise RuntimeError(f"Falta aml.meta['{key}']: corre el export")
        self._meta_cache[key] = (time.time(), row["value"])
        return row["value"]

    @property
    def model_version(self) -> str:
        return self.metrics().model_version

    @property
    def threshold_version(self) -> str:
        return self.thresholds().threshold_version

    def thresholds(self) -> Thresholds:
        return Thresholds.model_validate(self._meta("thresholds"))

    def metrics(self) -> ModelMetrics:
        return ModelMetrics.model_validate(self._meta("metrics"))

    def _txn(self, r: dict) -> TxnScore:
        normal = operating_point(self.thresholds(), Mode.normal)
        return TxnScore(**r, band=band_for(r["p_laundering"], normal))

    def score(self, txn_ids: list[int]) -> ScoreResponse:
        with self._conn() as c:
            rows = c.execute(f"SELECT {_TXN_COLS} FROM aml.txn_scores WHERE txn_id = ANY(%s)", (txn_ids,)).fetchall()
        found = {r["txn_id"] for r in rows}
        return ScoreResponse(results=[self._txn(r) for r in rows], not_found=[i for i in txn_ids if i not in found])

    def _band_sql(self, mode: Mode) -> tuple[str, list]:
        op = operating_point(self.thresholds(), mode)
        return ("CASE WHEN case_score >= %s THEN 'high_priority' WHEN case_score < %s THEN 'auto_close_eligible' "
                "ELSE 'review' END", [op.high_priority_threshold, op.auto_close_threshold])

    def list_cases(self, mode: Mode, limit: int, offset: int, band: Band | None, family: str | None) -> CaseList:
        band_sql, params = self._band_sql(mode)
        sql = f"""
            WITH ranked AS (
                SELECT {_CASE_COLS}, {band_sql} AS band,
                       row_number() OVER (ORDER BY case_score DESC, case_id) AS priority_rank
                FROM aml.cases
            )
            SELECT *, count(*) OVER () AS _total FROM ranked
            WHERE (%s::text IS NULL OR band = %s) AND (%s::text IS NULL OR family = %s)
            ORDER BY priority_rank LIMIT %s OFFSET %s
        """
        b = band.value if band else None
        with self._conn() as c:
            rows = c.execute(sql, params + [b, b, family, family, limit, offset]).fetchall()
        total = rows[0].pop("_total") if rows else 0
        for r in rows[1:]:
            r.pop("_total")
        return CaseList(mode=mode, total=total, cases=[CaseSummary(**r) for r in rows])

    def get_case(self, case_id: str, mode: Mode) -> CaseDetail | None:
        band_sql, params = self._band_sql(mode)
        with self._conn() as c:
            row = c.execute(f"""
                WITH ranked AS (
                    SELECT {_CASE_COLS}, top_reason_codes, {band_sql} AS band,
                           row_number() OVER (ORDER BY case_score DESC, case_id) AS priority_rank
                    FROM aml.cases
                ) SELECT * FROM ranked WHERE case_id = %s""", params + [case_id]).fetchone()
            if row is None:
                return None
            txs = c.execute(f"SELECT {_TXN_COLS} FROM aml.txn_scores WHERE case_id = %s ORDER BY ts",
                            (case_id,)).fetchall()
        return CaseDetail(**row, transactions=[self._txn(t) for t in txs])

    def account_score(self, account: str, start: datetime, end: datetime) -> AccountScore | None:
        th = self.thresholds()
        with self._conn() as c:
            r = c.execute("""
                SELECT count(*) AS n, max(p_laundering) AS mx, avg(p_laundering) AS mean,
                       count(*) FILTER (WHERE p_laundering >= %s) AS flagged
                FROM aml.txn_scores WHERE sender_account = %s AND ts BETWEEN %s AND %s
            """, (th.alert_threshold, account, start, end)).fetchone()
        if not r["n"]:
            return None
        return AccountScore(
            account=account, window_start=start, window_end=end, n_transactions=r["n"],
            max_p_laundering=r["mx"], mean_p_laundering=r["mean"], n_flagged=r["flagged"],
            band=band_for(r["mx"], operating_point(th, Mode.normal)),
            model_version=self.model_version, threshold_version=th.threshold_version,
        )

    def audit(self, txn_id: int) -> AuditRecord | None:
        with self._conn() as c:
            r = c.execute("""
                SELECT txn_id, scored_at, features_snapshot, score_raw, p_laundering, family,
                       reason_codes, model_version, threshold_version
                FROM aml.txn_scores WHERE txn_id = %s""", (txn_id,)).fetchone()
        if r is None:
            return None
        return AuditRecord(**r, band=band_for(r["p_laundering"], operating_point(self.thresholds(), Mode.normal)))

    def feedback(self, fb: FeedbackIn) -> FeedbackAck:
        with self._conn() as c:
            row = c.execute("SELECT case_score FROM aml.cases WHERE case_id = %s", (fb.case_id,)).fetchone()
            if row is None:
                raise KeyError(fb.case_id)
            model_band = band_for(row["case_score"], operating_point(self.thresholds(), Mode.normal))
            check_agent_band(model_band, fb)
            fid = uuid.uuid4()
            r = c.execute("""
                INSERT INTO aml.feedback (feedback_id, case_id, actor, decision, model_band, agent_band, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING received_at
            """, (fid, fb.case_id, fb.actor.value, fb.decision.value, model_band.value,
                  fb.agent_band.value if fb.agent_band else None, fb.notes)).fetchone()
        return FeedbackAck(feedback_id=str(fid), received_at=r["received_at"])

    def score_live(self, txn: LiveTransaction, mode: Mode) -> LiveScore:
        out = self._live.score(txn.model_dump())
        return LiveScore(
            ts=out["ts"], p_laundering=out["p_laundering"], score_raw=out["score_raw"],
            band=band_for(out["p_laundering"], operating_point(self.thresholds(), mode)),
            family=out["family"], family_confidence=out["family_confidence"],
            reason_codes=top_reasons(out["contributions"], out["features"]),
            features=out["features"], warnings=out["warnings"],
            model_version=out["model_version"], threshold_version=self.threshold_version,
        )
