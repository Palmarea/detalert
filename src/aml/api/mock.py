"""Backend con datos falsos pero realistas y deterministas (misma semilla -> mismos datos).

Sirve para que el agente y la bandeja integren contra el contrato antes de que
exista la data real. Usa nombres de features, tipologías y países reales de SAML-D.
"""

import random
import uuid
from datetime import datetime, timedelta, timezone

from aml.api import proposals
from aml.api.backend import band_for, check_agent_band, live_model_band, operating_point
from aml.api.schemas import (
    AccountScore, AuditRecord, Band, CaseDetail, CaseList, CaseSummary, Family, FeedbackAck,
    FeedbackIn, FeedbackList, FeedbackRecord, FunnelStage, Mode, ModelMetrics, OperatingPoint, Origin,
    Proposal, ProposalList, ReasonCode, ScoreResponse, Thresholds, TxnScore,
)

MODEL_VERSION = "binary_v1-mock"
THRESHOLD_VERSION = "thresholds_v1-mock"

REASONS = [
    ("NEW_COUNTERPARTY", "is_new_counterparty", lambda r: 1, "Primera transacción hacia esta contraparte"),
    ("SENDER_DORMANT", "s_hours_since_prev", lambda r: round(r.uniform(30, 400), 1),
     "El emisor llevaba {v} h sin operar"),
    ("RECEIVER_RAPID", "r_hours_since_prev", lambda r: round(r.uniform(0.01, 0.5), 2),
     "El receptor recibió otra transferencia hace {v} h"),
    ("CASH", "payment_type", lambda r: r.choice(["Cash Deposit", "Cash Withdrawal"]), "Operación en efectivo ({v})"),
    ("AMOUNT_UNUSUAL", "s_amt_ratio_mean_30d", lambda r: round(r.uniform(4, 40), 1),
     "Monto {v}x el promedio de 30 días de la cuenta"),
    ("RECEIVER_FORWARDS", "r_out_cnt_7d", lambda r: r.randint(3, 30),
     "El receptor reenvió dinero {v} veces en 7 días"),
    ("FAN_IN", "r_uniq_snd_7d", lambda r: r.randint(5, 20), "El receptor recibió de {v} emisores distintos en 7 días"),
    ("CURRENCY_MISMATCH", "currency_mismatch", lambda r: 1, "La moneda de pago y la de recepción no coinciden"),
]
FAMILY_TYPOLOGIES = {
    Family.structuring: ["Structuring", "Smurfing", "Deposit-Send"],
    Family.layering: ["Layered_Fan_Out", "Layered_Fan_In", "Cycle", "Scatter-Gather"],
    Family.concentration: ["Fan_In", "Fan_Out", "Bipartite"],
    Family.cash: ["Cash_Withdrawal", "Single_large"],
    Family.behavioural: ["Behavioural_Change_1", "Behavioural_Change_2"],
}
PAYMENT_TYPES = ["Cross-border", "Cash Deposit", "Cash Withdrawal", "ACH", "Credit card", "Debit card", "Cheque"]


def _reasons(rng: random.Random, k: int) -> list[ReasonCode]:
    out = []
    for i, (code, feat, gen, text) in enumerate(rng.sample(REASONS, k)):
        v = gen(rng)
        out.append(ReasonCode(code=code, feature=feat, value=v, contribution=round(3.0 / (i + 1) * rng.uniform(0.7, 1.2), 3),
                              text=text.format(v=v)))
    return out


class MockBackend:
    name = "mock"
    model_version = MODEL_VERSION
    threshold_version = THRESHOLD_VERSION

    def __init__(self, n_cases: int = 120, seed: int = 42):
        rng = random.Random(seed)
        self._th = Thresholds(
            threshold_version=THRESHOLD_VERSION,
            alert_threshold=0.01,
            operating_points=[
                OperatingPoint(mode=Mode.normal, analyst_capacity_pct=100, auto_close_threshold=0.05,
                               high_priority_threshold=0.9, auto_close_rate=0.35, expected_leakage=0.002,
                               queue_cases_per_day=40, preventive_hold=False),
                OperatingPoint(mode=Mode.reduced_capacity, analyst_capacity_pct=50, auto_close_threshold=0.12,
                               high_priority_threshold=0.8, auto_close_rate=0.5, expected_leakage=0.005,
                               queue_cases_per_day=20, preventive_hold=False),
                OperatingPoint(mode=Mode.no_analyst, analyst_capacity_pct=0, auto_close_threshold=0.05,
                               high_priority_threshold=0.5, auto_close_rate=0.35, expected_leakage=0.002,
                               queue_cases_per_day=0, preventive_hold=True),
            ],
        )
        self._txns: dict[int, TxnScore] = {}
        self._audit: dict[int, AuditRecord] = {}
        self._cases: dict[str, dict] = {}
        self._feedback: list[FeedbackRecord] = []
        self._proposals: list[Proposal] = []
        t0 = datetime(2023, 6, 1, tzinfo=timezone.utc)
        txn_id = 9_000_000
        normal = operating_point(self._th, Mode.normal)
        for _ in range(n_cases):
            account = str(rng.randint(10**9, 10**10 - 1))
            fam = rng.choice(list(FAMILY_TYPOLOGIES))
            # Mezcla: ~35% casos claros de bajo riesgo, resto revisión / alta prioridad.
            case_score = round(rng.choice([rng.uniform(0.01, 0.05), rng.uniform(0.05, 0.9), rng.uniform(0.9, 0.999)]), 4)
            start = t0 + timedelta(days=rng.randint(0, 80), hours=rng.randint(0, 23))
            txs = []
            for j in range(rng.randint(1, 8)):
                txn_id += rng.randint(1, 500)
                p = round(min(0.999, max(0.011, case_score * rng.uniform(0.6, 1.1))), 4)
                ts = start + timedelta(hours=j * rng.uniform(0.2, 20))
                reasons = _reasons(rng, 3)
                tx = TxnScore(
                    txn_id=txn_id, ts=ts, sender_account=account,
                    receiver_account=str(rng.randint(10**9, 10**10 - 1)),
                    amount=round(rng.lognormvariate(8.8, 1.1), 2), payment_type=rng.choice(PAYMENT_TYPES),
                    p_laundering=p, band=band_for(p, normal), family=fam,
                    family_confidence=round(rng.uniform(0.55, 0.98), 3), reason_codes=reasons,
                    model_version=MODEL_VERSION, threshold_version=THRESHOLD_VERSION,
                )
                self._txns[txn_id] = tx
                self._audit[txn_id] = AuditRecord(
                    txn_id=txn_id, scored_at=ts + timedelta(seconds=2),
                    features_snapshot={r.feature: r.value for r in reasons} | {"amount": tx.amount},
                    score_raw=round(min(0.999, p * 1.3), 5), p_laundering=p, band=tx.band, family=fam,
                    reason_codes=reasons, model_version=MODEL_VERSION, threshold_version=THRESHOLD_VERSION,
                )
                txs.append(tx)
            case_id = f"C-{account}-{start:%Y-%m-%d}"
            self._cases[case_id] = {
                "case_id": case_id, "account": account, "window_start": txs[0].ts, "window_end": txs[-1].ts,
                "n_transactions": len(txs) + rng.randint(0, 20), "n_flagged": len(txs),
                "total_amount_flagged": round(sum(t.amount for t in txs), 2), "case_score": case_score,
                "family": fam, "txn_ids": [t.txn_id for t in txs], "top_reason_codes": _reasons(rng, 4),
            }

    # --- Backend API ---
    def thresholds(self) -> Thresholds:
        return self._th

    def score(self, txn_ids: list[int]) -> ScoreResponse:
        found = [self._txns[i] for i in txn_ids if i in self._txns]
        return ScoreResponse(results=found, not_found=[i for i in txn_ids if i not in self._txns])

    def _summary(self, c: dict, mode: Mode, rank: int) -> CaseSummary:
        return CaseSummary(
            **{k: c[k] for k in ("case_id", "account", "window_start", "window_end", "n_transactions",
                                 "n_flagged", "total_amount_flagged", "case_score", "family")},
            band=band_for(c["case_score"], operating_point(self._th, mode)), priority_rank=rank,
            model_version=MODEL_VERSION, threshold_version=THRESHOLD_VERSION,
        )

    def _ranked(self, mode: Mode) -> list[CaseSummary]:
        ordered = sorted(self._cases.values(), key=lambda c: -c["case_score"])
        return [self._summary(c, mode, i + 1) for i, c in enumerate(ordered)]

    def list_cases(self, mode, limit, offset, band, family) -> CaseList:
        cases = [c for c in self._ranked(mode)
                 if (band is None or c.band == band) and (family is None or c.family.value == family)]
        return CaseList(mode=mode, total=len(cases), cases=cases[offset:offset + limit])

    def get_case(self, case_id, mode) -> CaseDetail | None:
        if case_id not in self._cases:
            return None
        s = next(c for c in self._ranked(mode) if c.case_id == case_id)
        c = self._cases[case_id]
        return CaseDetail(**s.model_dump(), transactions=[self._txns[i] for i in c["txn_ids"]],
                          top_reason_codes=c["top_reason_codes"])

    def account_score(self, account, start, end) -> AccountScore | None:
        txs = [t for t in self._txns.values() if t.sender_account == account and start <= t.ts <= end]
        if not txs:
            return None
        mx = max(t.p_laundering for t in txs)
        return AccountScore(
            account=account, window_start=start, window_end=end, n_transactions=len(txs), max_p_laundering=mx,
            mean_p_laundering=round(sum(t.p_laundering for t in txs) / len(txs), 4),
            n_flagged=sum(t.p_laundering >= self._th.alert_threshold for t in txs),
            band=band_for(mx, operating_point(self._th, Mode.normal)),
            model_version=MODEL_VERSION, threshold_version=THRESHOLD_VERSION,
        )

    def metrics(self) -> ModelMetrics:
        return ModelMetrics(
            sample="oot", gini=99.94, ks=98.21, pr_auc=0.9756, recall_at_1pct=0.9898, baseline_gini=44.7,
            recall_by_typology={"Smurfing": 0.947, "Cash_Withdrawal": 0.975, "Structuring": 1.0},
            funnel=[
                FunnelStage(stage="transacciones", n_in=2_456_064, n_out=2_456_064, positives_out=2837, leakage=0),
                FunnelStage(stage="alertas", n_in=2_456_064, n_out=24_561, positives_out=2808, leakage=0.0102),
                FunnelStage(stage="casos", n_in=24_561, n_out=3_900, positives_out=2808, leakage=0),
                FunnelStage(stage="escalados", n_in=3_900, n_out=2_500, positives_out=2802, leakage=0.002),
            ],
            model_version=MODEL_VERSION, threshold_version=THRESHOLD_VERSION,
        )

    def audit(self, txn_id) -> AuditRecord | None:
        return self._audit.get(txn_id)

    def feedback(self, fb: FeedbackIn) -> FeedbackAck:
        if fb.origin == Origin.score_live:
            model_band = live_model_band(fb, self._th)
        elif fb.case_id in self._cases:
            model_band = band_for(self._cases[fb.case_id]["case_score"], operating_point(self._th, Mode.normal))
        else:
            raise KeyError(fb.case_id)
        check_agent_band(model_band, fb)
        ack = FeedbackAck(feedback_id=str(uuid.uuid4()), received_at=datetime.now(timezone.utc))
        self._feedback.append(FeedbackRecord(**fb.model_dump(), **ack.model_dump(), model_band=model_band))
        return ack

    def list_feedback(self, actor, origin, since, limit, offset) -> FeedbackList:
        items = [f for f in self._feedback if (actor is None or f.actor == actor)
                 and (origin is None or f.origin == origin) and (since is None or f.received_at >= since)]
        return FeedbackList(total=len(items), items=items[offset:offset + limit])

    def _known_case_ids(self) -> set[str]:
        return set(self._cases) | {f.case_id for f in self._feedback if f.origin == Origin.score_live}

    def create_proposal(self, p) -> Proposal:
        proposals.validate(p, self._th, self._known_case_ids())
        status, reason, log = proposals.initial(p)
        prop = Proposal(id=f"P-{len(self._proposals) + 1:03d}", at=datetime.now(timezone.utc), status=status,
                        title=p.title, sub=p.sub, ask=p.ask, reason=reason, from_=proposals.snapshot(self._th),
                        evidence=p.evidence, log=log, base_threshold_version=self._th.threshold_version)
        self._proposals.append(prop)
        return prop

    def list_proposals(self, status) -> ProposalList:
        return ProposalList(threshold_version=self._th.threshold_version,
                            proposals=[p for p in self._proposals if status is None or p.status == status])

    def score_live(self, txn, mode):
        raise NotImplementedError("El scoring en vivo necesita el historial real: usa AML_BACKEND=postgres")
