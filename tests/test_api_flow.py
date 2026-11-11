import time
import uuid

import httpx
import pytest

API = "http://localhost:8000"
API_KEY = "dev-api-key"


def _api_up() -> bool:
    try:
        response = httpx.get(f"{API}/health", timeout=2)
    except httpx.HTTPError:
        return False
    return response.status_code == 200


pytestmark = pytest.mark.skipif(not _api_up(), reason="api is not running")


def test_create_is_idempotent_and_readable() -> None:
    key = str(uuid.uuid4())
    payload = {
        "amount": "15.50",
        "currency": "RUB",
        "description": "pytest",
        "metadata": {"source": "test"},
        "webhook_url": "http://127.0.0.1:9/hook",
    }
    headers = {"X-API-Key": API_KEY, "Idempotency-Key": key}

    with httpx.Client(timeout=10) as client:
        created = client.post(f"{API}/api/v1/payments", json=payload, headers=headers)
        again = client.post(f"{API}/api/v1/payments", json=payload, headers=headers)

        assert created.status_code == 202, created.text
        assert again.status_code == 202, again.text
        body = created.json()
        assert again.json()["payment_id"] == body["payment_id"]
        assert body["status"] == "pending"

        missing = client.get(
            f"{API}/api/v1/payments/{uuid.uuid4()}",
            headers={"X-API-Key": API_KEY},
        )
        assert missing.status_code == 404

        payment_id = body["payment_id"]
        deadline = time.monotonic() + 20
        status = "pending"
        while time.monotonic() < deadline:
            fetched = client.get(
                f"{API}/api/v1/payments/{payment_id}",
                headers={"X-API-Key": API_KEY},
            )
            assert fetched.status_code == 200, fetched.text
            status = fetched.json()["status"]
            if status != "pending":
                assert fetched.json()["metadata"] == {"source": "test"}
                assert fetched.json()["amount"] == "15.50"
                break
            time.sleep(1)

    assert status in {"succeeded", "failed"}
