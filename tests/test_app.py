from fastapi.testclient import TestClient

from payment.db.base import Base
from payment.main import app
from payment.messaging.topology import DLQ, NEW_QUEUE


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_payments_require_api_key() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/payments", json={})

    assert response.status_code == 401


def test_openapi_lists_payment_routes() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/payments" in paths
    assert "/api/v1/payments/{payment_id}" in paths


def test_tables_and_queues_match_the_spec() -> None:
    import payment.db.models  # noqa: F401

    assert "payments" in Base.metadata.tables
    assert "outbox" in Base.metadata.tables
    assert NEW_QUEUE == "payments.new"
    assert DLQ == "payments.dlq"
