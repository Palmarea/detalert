"""Tests del contrato de la API.

Por defecto con el backend mock. Contra Postgres (cargado con aml.api.seed_mock):
    AML_TEST_BACKEND=postgres DATABASE_URL=postgresql:///aml_dev pytest tests/test_api.py
"""

import os

import pytest
from fastapi.testclient import TestClient

from aml.api.main import app, get_backend


@pytest.fixture(autouse=True)
def mock_backend(monkeypatch):
    monkeypatch.setenv("AML_BACKEND", os.getenv("AML_TEST_BACKEND", "mock"))
    monkeypatch.delenv("AML_API_KEY", raising=False)
    get_backend.cache_clear()
    yield
    get_backend.cache_clear()


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/health").json()
    assert r["status"] == "ok" and r["backend"] == os.getenv("AML_TEST_BACKEND", "mock")


def test_cases_sorted_by_priority(client):
    r = client.get("/cases", params={"limit": 20}).json()
    scores = [c["case_score"] for c in r["cases"]]
    assert scores == sorted(scores, reverse=True)
    assert [c["priority_rank"] for c in r["cases"]] == list(range(1, 21))
    assert r["total"] >= 20


def test_band_depends_on_mode(client):
    def n_high(mode):
        return client.get("/cases", params={"mode": mode, "band": "high_priority", "limit": 1}).json()["total"]
    total = client.get("/cases", params={"limit": 1}).json()["total"]
    assert total == client.get("/cases", params={"limit": 1, "mode": "no_analyst"}).json()["total"]
    # Sin analista el umbral de alta prioridad baja -> más casos high_priority.
    assert n_high("no_analyst") > n_high("normal")


def test_case_detail_and_score_roundtrip(client):
    case_id = client.get("/cases", params={"limit": 1}).json()["cases"][0]["case_id"]
    case = client.get(f"/cases/{case_id}").json()
    assert case["transactions"] and case["top_reason_codes"]
    ids = [t["txn_id"] for t in case["transactions"]]
    r = client.post("/score/transactions", json={"txn_ids": ids + [1]}).json()
    assert {t["txn_id"] for t in r["results"]} == set(ids)
    assert r["not_found"] == [1]
    assert all(0 <= t["p_laundering"] <= 1 and t["reason_codes"] for t in r["results"])
    a = client.get(f"/audit/{ids[0]}").json()
    assert a["features_snapshot"] and a["model_version"]



def test_account_score_accepts_naive_and_aware_dates(client):
    case = client.get("/cases", params={"limit": 1}).json()["cases"][0]
    for start, end in [("2022-10-01T00:00:00", "2023-12-31T00:00:00"), ("2022-10-01T00:00:00Z", "2023-12-31T00:00:00Z")]:
        r = client.get(f"/score/account/{case['account']}", params={"from": start, "to": end})
        assert r.status_code == 200 and r.json()["n_transactions"] >= 1


def test_filters(client):
    r = client.get("/cases", params={"band": "auto_close_eligible", "family": "cash", "limit": 500}).json()
    assert all(c["band"] == "auto_close_eligible" and c["family"] == "cash" for c in r["cases"])


def test_agent_cannot_lower_band(client):
    hp = client.get("/cases", params={"band": "high_priority", "limit": 1}).json()["cases"][0]["case_id"]
    bad = client.post("/feedback", json={"case_id": hp, "actor": "agent", "decision": "auto_closed",
                                         "agent_band": "auto_close_eligible"})
    assert bad.status_code == 422
    ok = client.post("/feedback", json={"case_id": hp, "actor": "agent", "decision": "high_priority",
                                        "agent_band": "high_priority"})
    assert ok.status_code == 201 and ok.json()["feedback_id"]


def test_raise_band_allowed(client):
    rv = client.get("/cases", params={"band": "review", "limit": 1}).json()["cases"][0]["case_id"]
    r = client.post("/feedback", json={"case_id": rv, "actor": "agent", "decision": "high_priority",
                                       "agent_band": "high_priority"})
    assert r.status_code == 201


def test_not_found(client):
    assert client.get("/cases/nope").status_code == 404
    assert client.get("/audit/1").status_code == 404
    assert client.post("/feedback", json={"case_id": "nope", "actor": "analyst",
                                          "decision": "approved"}).status_code == 404


def test_api_key(client, monkeypatch):
    monkeypatch.setenv("AML_API_KEY", "secreto-de-prueba")
    assert client.get("/cases").status_code == 401
    assert client.get("/cases", headers={"X-API-Key": "secreto-de-prueba"}).status_code == 200
    assert client.get("/health").status_code == 200


def test_thresholds_and_metrics(client):
    th = client.get("/thresholds").json()
    assert {op["mode"] for op in th["operating_points"]} == {"normal", "reduced_capacity", "no_analyst"}
    m = client.get("/model/metrics").json()
    assert m["gini"] > m["baseline_gini"] and m["funnel"]


LIVE_TXN = {"ts": "2023-08-10T05:15:22Z", "sender_account": "6812204903", "receiver_account": "5440521221",
            "amount": 6248.44, "payment_type": "Cross-border", "payment_currency": "UK pounds",
            "received_currency": "Euro", "sender_bank_location": "UK", "receiver_bank_location": "France"}


def test_live_score(client):
    r = client.post("/score/live", json=LIVE_TXN)
    if os.getenv("AML_TEST_BACKEND", "mock") == "mock":
        assert r.status_code == 501
        return
    assert r.status_code == 200
    d = r.json()
    # txn 9116407 (lavado real, Stacked Bipartite): el batch le dio p = 0.997308
    assert abs(d["p_laundering"] - 0.997308) < 1e-5
    assert d["band"] == "high_priority" and d["reason_codes"] and not d["warnings"]
    assert d["features"]["is_new_counterparty"] in (0, 1)


def test_live_score_validation(client):
    bad = dict(LIVE_TXN, payment_type="Bitcoin")
    assert client.post("/score/live", json=bad).status_code == 422
    assert client.post("/score/live", json=dict(LIVE_TXN, amount=-5)).status_code == 422


def test_live_score_unknown_accounts(client):
    if os.getenv("AML_TEST_BACKEND", "mock") == "mock":
        return
    new = dict(LIVE_TXN, sender_account="cuenta-nueva-1", receiver_account="cuenta-nueva-2")
    d = client.post("/score/live", json=new).json()
    assert d["features"]["is_new_counterparty"] == 1 and d["features"]["s_hours_since_prev"] is None


def test_feedback_live_and_list(client):
    base = client.get("/feedback").json()["total"]
    # Caso de /score/live: no existe en /cases; la banda se valida con case_score.
    no_score = client.post("/feedback", json={"case_id": "jurado_1", "actor": "agent", "decision": "escalated",
                                              "origin": "score_live"})
    assert no_score.status_code == 422
    lower = client.post("/feedback", json={"case_id": "jurado_1", "actor": "agent", "decision": "auto_closed",
                                           "origin": "score_live", "case_score": 0.99,
                                           "agent_band": "auto_close_eligible"})
    assert lower.status_code == 422
    ok = client.post("/feedback", json={"case_id": "jurado_1", "actor": "agent", "decision": "escalated",
                                        "origin": "score_live", "case_score": 0.5, "agent_band": "review",
                                        "model_version": "binary_v1",
                                        "agent_payload": {"familia_inferida": "structuring", "confianza": 66}})
    assert ok.status_code == 201
    r = client.get("/feedback", params={"origin": "score_live"}).json()
    rec = r["items"][-1]
    assert rec["case_id"] == "jurado_1" and rec["agent_payload"]["confianza"] == 66 and rec["case_score"] == 0.5
    assert client.get("/feedback").json()["total"] == base + 1
    assert client.get("/feedback", params={"actor": "analyst", "origin": "score_live"}).json()["total"] == 0


def _evidence(client, n, band="review"):
    cases = client.get("/cases", params={"band": band, "limit": n}).json()["cases"]
    return [[c["case_id"], c["case_score"], c["band"], "review", "prueba"] for c in cases]


def test_threshold_proposals(client):
    auto = next(op for op in client.get("/thresholds").json()["operating_points"]
                if op["mode"] == "normal")["auto_close_threshold"]
    ev = _evidence(client, 5)
    tighten = client.post("/thresholds/proposals", json={
        "title": "Bajar cierre", "ask": ["auto", auto, round(auto * 0.9, 6)], "evidence": ev})
    assert tighten.status_code == 201, tighten.text
    p = tighten.json()
    assert p["status"] == "pending" and p["from"]["auto"] == auto and p["id"].startswith("P-")
    relax = client.post("/thresholds/proposals", json={
        "title": "Subir cierre", "ask": ["auto", auto, round(auto * 1.1, 6)], "evidence": ev}).json()
    assert relax["status"] == "blocked"
    listed = client.get("/thresholds/proposals").json()
    assert {x["id"] for x in listed["proposals"]} >= {p["id"], relax["id"]}
    assert all(x["status"] == "blocked" for x in client.get("/thresholds/proposals",
                                                              params={"status": "blocked"}).json()["proposals"])


def test_threshold_proposal_rules(client):
    auto = next(op for op in client.get("/thresholds").json()["operating_points"]
                if op["mode"] == "normal")["auto_close_threshold"]
    ev = _evidence(client, 5)
    bad = [
        {"ask": ["auto", auto * 2, auto], "evidence": ev},                       # no es el valor vigente
        {"ask": ["auto", auto, auto * 0.5], "evidence": ev},                     # cambio > 25 %
        {"ask": ["auto", auto, auto * 0.9], "evidence": ev[:4]},                 # < 5 casos
        {"ask": ["auto", auto, auto * 0.9], "evidence": ev[:4] + [["C-no-existe", 0.1, "review", "review", ""]]},
    ]
    for body in bad:
        assert client.post("/thresholds/proposals", json={"title": "x", **body}).status_code == 422
