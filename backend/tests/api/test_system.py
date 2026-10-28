from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import system
from app.db.status import DatabaseStatus
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_health_is_ok_without_database(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_security_headers_and_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"
    assert len(response.headers["X-Request-ID"]) == 36


def test_invalid_incoming_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "<script>"})
    assert response.headers["X-Request-ID"] != "<script>"


def test_status_reports_database_down_as_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        system, "read_database_status", lambda _e: DatabaseStatus(False, None, None, None)
    )
    response = client.get("/api/v1/status")
    assert response.status_code == 503
    body = response.json()
    assert body["database"] == "down"
    assert body["dataset_ready"] is False


def test_status_without_active_bundle_is_not_ready(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        system, "read_database_status", lambda _e: DatabaseStatus(True, "3.5.0", None, None)
    )
    body = client.get("/api/v1/status").json()
    assert body["database"] == "up"
    assert body["dataset_ready"] is False


def test_status_with_active_bundle_is_ready(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 10, 28, tzinfo=UTC)
    monkeypatch.setattr(
        system,
        "read_database_status",
        lambda _e: DatabaseStatus(True, "3.5.0", "b1", now),
    )
    body = client.get("/api/v1/status").json()
    assert body["dataset_ready"] is True
    assert body["active_bundle_id"] == "b1"


def test_unknown_route_returns_problem_json(client: TestClient) -> None:
    response = client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "NOT_FOUND"


def test_oversized_body_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/health", content=b"x" * (64 * 1024 + 1), headers={"Content-Type": "text/plain"}
    )
    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"
