"""Scoring en vivo: transacción nueva -> features point-in-time desde Postgres -> modelo en Python puro.

Replica exactamente las definiciones de aml/features.py para las 18 features del
modelo: ventanas [T - N días, T) sobre aml.history, y las features "desde siempre"
(contraparte nueva, horas desde la última transacción) completadas con
aml.pairs_before / aml.accounts_before para lo anterior al inicio del historial.
"""

import math
import time
from datetime import datetime, timedelta, timezone

from aml.api.predictor import TreeModel, platt

_MODEL_TTL_S = 3600

FEATURE_SQL = """
WITH s30 AS (
    SELECT ts, receiver, amount, is_cash FROM aml.history
    WHERE sender = %(s)s AND ts >= %(t)s - interval '30 days' AND ts < %(t)s
), r30 AS (
    SELECT ts, sender FROM aml.history
    WHERE receiver = %(r)s AND ts >= %(t)s - interval '30 days' AND ts < %(t)s
)
SELECT
    (SELECT count(*) FROM s30 WHERE ts >= %(t)s - interval '7 days')                        AS s_cnt_7d,
    (SELECT count(*) FROM s30)                                                               AS s_cnt_30d,
    (SELECT coalesce(sum(amount), 0) FROM s30 WHERE ts >= %(t)s - interval '7 days')         AS s_amt_7d,
    (SELECT avg(amount) FROM s30)                                                            AS s_mean_30d,
    (SELECT stddev_samp(amount) FROM s30)                                                    AS s_std_30d,
    (SELECT count(*) FILTER (WHERE is_cash) FROM s30)                                        AS s_cash_cnt_30d,
    (SELECT count(*) FROM s30 WHERE receiver = %(r)s AND ts >= %(t)s - interval '7 days')    AS pair_cnt_7d,
    (SELECT count(DISTINCT sender) FROM r30 WHERE ts >= %(t)s - interval '7 days')           AS r_uniq_snd_7d,
    (SELECT count(DISTINCT sender) FROM r30)                                                 AS r_uniq_snd_30d,
    (SELECT count(*) FROM aml.history WHERE receiver = %(s)s
        AND ts >= %(t)s - interval '7 days' AND ts < %(t)s)                                  AS s_in_cnt_7d,
    (SELECT coalesce(sum(amount), 0) FROM aml.history WHERE receiver = %(s)s
        AND ts >= %(t)s - interval '7 days' AND ts < %(t)s)                                  AS s_in_amt_7d,
    (SELECT count(*) FROM aml.history WHERE sender = %(r)s
        AND ts >= %(t)s - interval '7 days' AND ts < %(t)s)                                  AS r_out_cnt_7d,
    coalesce((SELECT max(ts) FROM aml.history WHERE sender = %(s)s AND ts < %(t)s),
             (SELECT last_send_ts FROM aml.accounts_before WHERE acct = %(s)s))              AS s_prev_ts,
    coalesce((SELECT max(ts) FROM aml.history WHERE receiver = %(r)s AND ts < %(t)s),
             (SELECT last_recv_ts FROM aml.accounts_before WHERE acct = %(r)s))              AS r_prev_ts,
    (EXISTS (SELECT 1 FROM aml.history WHERE sender = %(s)s AND receiver = %(r)s AND ts < %(t)s)
     OR EXISTS (SELECT 1 FROM aml.pairs_before WHERE sender = %(s)s AND receiver = %(r)s))  AS pair_seen
"""


def _acct(a: str) -> int:
    try:
        return int(a)
    except (TypeError, ValueError):
        return -1  # cuenta no numérica: no existe en el historial -> cuenta nueva


def build_features(row: dict, txn: dict, t: datetime) -> dict:
    amount = float(txn["amount"])
    mean, std = row["s_mean_30d"], row["s_std_30d"]
    hours = lambda prev: (t - prev).total_seconds() / 3600 if prev else None  # noqa: E731
    return {
        "amount": amount,
        "payment_type": txn["payment_type"],
        "currency_mismatch": int(txn["payment_currency"] != txn["received_currency"]),
        "is_new_counterparty": int(not row["pair_seen"]),
        "s_cnt_7d": row["s_cnt_7d"],
        "s_cnt_30d": row["s_cnt_30d"],
        "s_amt_7d": float(row["s_amt_7d"]),
        "s_amt_ratio_mean_30d": amount / mean if mean else None,
        "s_amt_z_30d": (amount - mean) / std if std else None,
        "s_cash_cnt_30d": row["s_cash_cnt_30d"],
        "pair_cnt_7d": row["pair_cnt_7d"],
        "r_uniq_snd_7d": row["r_uniq_snd_7d"],
        "r_uniq_snd_30d": row["r_uniq_snd_30d"],
        "s_in_cnt_7d": row["s_in_cnt_7d"],
        "s_out_in_ratio_7d": float(row["s_amt_7d"]) / float(row["s_in_amt_7d"]) if row["s_in_amt_7d"] else None,
        "r_out_cnt_7d": row["r_out_cnt_7d"],
        "s_hours_since_prev": hours(row["s_prev_ts"]),
        "r_hours_since_prev": hours(row["r_prev_ts"]),
    }


class LiveScorer:
    """Carga modelos y calibración desde aml.meta (clave 'live_model') y puntúa transacciones."""

    def __init__(self, conn_factory):
        self._conn = conn_factory
        self._loaded_at = 0.0

    def _load(self):
        if time.time() - self._loaded_at < _MODEL_TTL_S:
            return
        with self._conn() as c:
            m = c.execute("SELECT value FROM aml.meta WHERE key = 'live_model'").fetchone()
        if m is None:
            raise RuntimeError("Falta aml.meta['live_model']: corre python -m aml.export_live")
        m = m["value"]
        self.binary, self.family = TreeModel(m["binary"]), TreeModel(m["family"])
        self.coef, self.intercept = m["platt"]["coef"], m["platt"]["intercept"]
        self.classes, self.generic_below = m["family_classes"], m["generic_below"]
        self.history_start = datetime.fromisoformat(m["history_start"])
        self.history_end = datetime.fromisoformat(m["history_end"])
        self.model_version = m["model_version"]
        self._loaded_at = time.time()

    def score(self, txn: dict) -> dict:
        self._load()
        warnings = []
        t = txn.get("ts") or (self.history_end + timedelta(minutes=1))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        if t < self.history_start + timedelta(days=30):
            warnings.append(f"ts anterior a {self.history_start + timedelta(days=30):%Y-%m-%d}: "
                            "las ventanas de 30 días quedan incompletas")
        if t > self.history_end + timedelta(days=1):
            warnings.append(f"ts posterior al historial (termina {self.history_end:%Y-%m-%d}): "
                            "no hay actividad reciente para estas cuentas")
        with self._conn() as c:
            row = c.execute(FEATURE_SQL, {"s": _acct(txn["sender_account"]), "r": _acct(txn["receiver_account"]),
                                          "t": t}).fetchone()
        x = build_features(row, txn, t)
        prob, margin, contrib = self.binary.predict_binary(x, with_contrib=True)
        fam = self.family.predict_multiclass(x)
        k = max(range(len(fam)), key=fam.__getitem__)
        return {
            "ts": t,
            "features": {k_: (None if isinstance(v, float) and math.isnan(v) else v) for k_, v in x.items()},
            "score_raw": prob,
            "p_laundering": platt(margin, self.coef, self.intercept),
            "family": self.classes[k] if fam[k] >= self.generic_below else "generic",
            "family_confidence": fam[k],
            "contributions": contrib,
            "warnings": warnings,
            "model_version": self.model_version,
        }
