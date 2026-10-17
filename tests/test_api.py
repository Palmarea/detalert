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
