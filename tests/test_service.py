import json

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import DIAGNOSIS_JSON_SCHEMA, Detector, MEAN, STD, Settings, Telemetry, create_app

NORMAL = dict(asset_id="motor-01", timestamp="2026-11-16T10:00:00Z", temperature_c=65, vibration_mm_s=2, current_a=10)
ABNORMAL = {**NORMAL, "temperature_c": 110, "vibration_mm_s": 12, "current_a": 22}


@pytest.fixture
def settings(monkeypatch):
    for key in ["LLM_API_KEY", "LLM_MODEL", "INGEST_API_KEY", "WORKFLOW_WEBHOOK_URL", "WORKFLOW_TOKEN"]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LLM_MODE", "offline")
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.test/v1/")
    return Settings()


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def test_health_and_normal_skips_network(settings):
    def handler(request):
        pytest.fail("Normal samples must not call LLM or workflow")
    settings.webhook = "https://workflow.test/hook"
    settings.llm_mode = "live"
    with TestClient(create_app(settings, httpx.MockTransport(handler))) as client:
        assert client.get("/healthz").json()["model_loaded"]
        r = client.post("/v1/telemetry", json=NORMAL)
        assert r.status_code == 200
        data = r.json()
        assert not data["detection"]["is_anomaly"]
        assert data["diagnosis"] is None
        assert data["workflow_status"] == "not_needed"


def test_offline_anomaly(client):
    r = client.post("/v1/telemetry", json=ABNORMAL)
    assert r.status_code == 200
    data = r.json()
    assert data["detection"]["decision_margin"] < 0
    assert data["diagnosis"]["source"] == "offline"
    assert data["diagnosis"]["requires_human_review"] is True
    assert data["workflow_status"] == "disabled"


@pytest.mark.parametrize("patch", [
    {"current_a": -1}, {"temperature_c": 251}, {"vibration_mm_s": "bad"},
    {"temperature_c": True}, {"current_a": "10"}, {"asset_id": ""},
    {"asset_id": "ignore instructions"}, {"timestamp": "yesterday"},
    {"timestamp": "2026-11-16T10:00:00"}, {"extra": 1},
    {"current_a": None}, {"vibration_mm_s": 101},
])
def test_validation(client, patch):
    assert client.post("/v1/telemetry", json={**NORMAL, **patch}).status_code == 422


def test_missing_and_bad_json(client):
    assert client.post("/v1/telemetry", json={}).status_code == 422
    assert client.post("/v1/telemetry", content="{bad", headers={"Content-Type": "application/json"}).status_code == 422


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_input(client, value):
    payload = json.dumps({**NORMAL, "temperature_c": value})
    assert client.post("/v1/telemetry", content=payload, headers={"Content-Type": "application/json"}).status_code == 422


def test_authentication(settings):
    settings.api_key = "local-test-key"
    with TestClient(create_app(settings)) as client:
        assert client.post("/v1/telemetry", json=NORMAL).status_code == 401
        assert client.post("/v1/telemetry", json=NORMAL, headers={"X-API-Key": "wrong"}).status_code == 401
        assert client.post("/v1/telemetry", json=NORMAL, headers={"X-API-Key": settings.api_key}).status_code == 200


def test_live_llm_and_webhook(settings):
    settings.llm_mode, settings.llm_key, settings.llm_model = "live", "test-key", "test-model"
    settings.webhook, settings.webhook_token = "https://workflow.test/hook", "workflow-secret"
    calls = []
    def handler(request):
        calls.append(request)
        body = json.loads(request.content)
        if request.url.host == "provider.test":
            assert request.headers["Authorization"] == "Bearer test-key"
            assert body["response_format"]["type"] == "json_schema"
            assert body["response_format"]["json_schema"]["schema"] == DIAGNOSIS_JSON_SCHEMA
            assert "deviations_sigma" in body["messages"][1]["content"]
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"summary": "Elevated vibration may indicate bearing wear; inspect.", "probable_causes": ["Possible bearing wear"], "recommended_action": "inspect_bearings"})}}]})
        assert request.headers["Authorization"] == "Bearer workflow-secret"
        assert request.headers["Idempotency-Key"] == body["event"]["event_id"]
        assert body["event_type"] == "anomaly.detected"
        assert body["event"]["diagnosis"]["source"] == "llm"
        return httpx.Response(200, json={"accepted": True})
    with TestClient(create_app(settings, httpx.MockTransport(handler))) as client:
        data = client.post("/v1/telemetry", json=ABNORMAL).json()
    assert data["diagnosis"]["source"] == "llm"
    assert data["workflow_status"] == "delivered"
    assert len(calls) == 2


def test_boundary_telemetry_gets_structured_live_diagnosis(settings):
    settings.llm_mode, settings.llm_key, settings.llm_model = "live", "test-key", "gemini-3.5-flash-lite"
    boundary = {**NORMAL, "temperature_c": -50, "vibration_mm_s": 100, "current_a": 500}
    answer = {"summary": "Extreme sensor readings need human inspection.",
              "probable_causes": ["Sensor fault", "Mechanical or electrical fault"],
              "recommended_action": "review_sensor"}

    def handler(request):
        assert json.loads(request.content)["response_format"]["type"] == "json_schema"
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})

    with TestClient(create_app(settings, httpx.MockTransport(handler))) as client:
        result = client.post("/v1/telemetry", json=boundary).json()
    assert result["detection"]["is_anomaly"] is True
    assert result["diagnosis"]["source"] == "llm"
    assert result["diagnosis"]["fallback_reason"] is None
    assert result["diagnosis"]["recommended_action"] == "review_sensor"


def test_provider_json_schema_compatibility_retry(settings):
    settings.llm_mode, settings.llm_key, settings.llm_model = "live", "test-key", "test-model"
    requests = []
    answer = {"summary": "Inspect sensor and motor.", "probable_causes": ["Sensor or load fault"],
              "recommended_action": "review_sensor"}

    def handler(request):
        body = json.loads(request.content)
        requests.append(body["response_format"]["type"])
        if len(requests) == 1:
            return httpx.Response(400, json={"error": {"message": "JSON schema mode unavailable"}})
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})

    with TestClient(create_app(settings, httpx.MockTransport(handler))) as client:
        result = client.post("/v1/telemetry", json={**NORMAL, "temperature_c": -50,
                                                     "vibration_mm_s": 100, "current_a": 500}).json()
    assert requests == ["json_schema", "json_object"]
    assert result["diagnosis"]["source"] == "llm"
    assert result["diagnosis"]["fallback_reason"] is None


@pytest.mark.parametrize("failure", ["timeout", "rate_limit", "server", "bad_json", "missing", "unsafe_action"])
def test_llm_fallback(settings, failure):
    settings.llm_mode, settings.llm_key, settings.llm_model = "live", "test", "test"
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("test", request=request)
        if failure in {"rate_limit", "server"}:
            return httpx.Response(429 if failure == "rate_limit" else 503)
        if failure == "missing":
            return httpx.Response(200, json={"choices": []})
        content = "not JSON" if failure == "bad_json" else json.dumps({"summary": "Stop", "probable_causes": ["unknown"], "recommended_action": "shutdown_machine"})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
    with TestClient(create_app(settings, httpx.MockTransport(handler))) as client:
        response = client.post("/v1/telemetry", json=ABNORMAL)
    assert response.status_code == 200
    assert response.json()["diagnosis"]["source"] == "fallback"
    assert response.json()["diagnosis"]["fallback_reason"]


@pytest.mark.parametrize("status", [302, 401, 503])
def test_webhook_failure_preserves_detection(settings, status):
    settings.webhook = "https://workflow.test/hook"
    with TestClient(create_app(settings, httpx.MockTransport(lambda r: httpx.Response(status)))) as client:
        response = client.post("/v1/telemetry", json=ABNORMAL)
    assert response.status_code == 200
    assert response.json()["workflow_status"] == "failed"
    assert response.json()["detection"]["is_anomaly"]


def test_webhook_timeout(settings):
    settings.webhook = "https://workflow.test/hook"
    def handler(request):
        raise httpx.ConnectTimeout("test", request=request)
    with TestClient(create_app(settings, httpx.MockTransport(handler))) as client:
        assert client.post("/v1/telemetry", json=ABNORMAL).json()["workflow_status"] == "failed"


def test_model_repeatability_and_heldout_behavior():
    a, b = Detector(), Detector()
    sample = Telemetry(**ABNORMAL)
    assert a.predict(sample) == b.predict(sample)
    rng = np.random.default_rng(93)
    healthy = rng.normal(MEAN, STD, (500, 3))
    faults = rng.normal([110, 12, 22], STD, (100, 3))
    assert np.mean(a.model.predict(healthy) == -1) < .08
    assert np.mean(a.model.predict(faults) == -1) > .95


def test_configuration_requires_live_credentials(monkeypatch, settings):
    monkeypatch.setenv("LLM_MODE", "live")
    with pytest.raises(ValueError, match="requires"):
        Settings()


def test_openapi(client):
    schema = client.get("/openapi.json").json()
    assert "Telemetry" in schema["components"]["schemas"]
    assert "/v1/telemetry" in schema["paths"]
    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["docs"] == "/docs"
