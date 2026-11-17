import asyncio
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest

from payment.db.repositories.payments import same_request
from payment.domain.claim import Step, plan_processing
from payment.domain.enums import Currency, PaymentStatus
from payment.messaging.consumer import attempt_of, give_up
from payment.messaging.retry import backoff_seconds
from payment.messaging.topology import retry_delay_ms, retry_delays_ms
from payment.schemas.payment import PaymentCreate
from payment.services.processing import decide_status
from payment.services.webhook import WebhookDeliveryError, deliver_webhook


def test_backoff_doubles() -> None:
    assert backoff_seconds(1) == 1
    assert backoff_seconds(2) == 2
    assert backoff_seconds(3) == 4
    assert retry_delay_ms(1) == 1000
    assert retry_delay_ms(2) == 2000
    assert retry_delays_ms(3) == (1000, 2000)


def test_give_up_after_third_attempt() -> None:
    assert give_up(1, 3) is False
    assert give_up(2, 3) is False
    assert give_up(3, 3) is True


def test_decide_status_uses_success_rate() -> None:
    assert decide_status(0.0) is PaymentStatus.SUCCEEDED
    assert decide_status(0.89) is PaymentStatus.SUCCEEDED
    assert decide_status(0.9) is PaymentStatus.FAILED
    assert decide_status(0.99) is PaymentStatus.FAILED


def test_attempt_header() -> None:
    class Message:
        headers = {"x-attempt": "2"}

    assert attempt_of(Message()) == 2  # type: ignore[arg-type]

    class Empty:
        headers: dict[str, str] = {}

    assert attempt_of(Empty()) == 1  # type: ignore[arg-type]


def test_plan_processing_claims_pending_once() -> None:
    now = datetime.now(UTC)
    assert (
        plan_processing(PaymentStatus.PENDING, None, None, None, now, 30) is Step.CHARGE
    )
    assert (
        plan_processing(PaymentStatus.PENDING, now, None, None, now, 30) is Step.BUSY
    )
    stale = now - timedelta(seconds=31)
    assert (
        plan_processing(PaymentStatus.PENDING, stale, None, None, now, 30) is Step.CHARGE
    )


def test_plan_processing_sends_webhook_once() -> None:
    now = datetime.now(UTC)
    assert (
        plan_processing(PaymentStatus.SUCCEEDED, now, None, None, now, 30) is Step.WEBHOOK
    )
    assert (
        plan_processing(PaymentStatus.SUCCEEDED, now, now, None, now, 30) is Step.DONE
    )
    assert (
        plan_processing(PaymentStatus.FAILED, now, None, now, now, 30) is Step.BUSY
    )


def test_same_request_compares_body() -> None:
    payment = SimpleNamespace(
        amount=Decimal("10.00"),
        currency=Currency.RUB,
        description="demo",
        meta={"order": 1},
        webhook_url="https://example.com/hook",
    )
    payload = PaymentCreate(
        amount=Decimal("10.00"),
        currency=Currency.RUB,
        description="demo",
        metadata={"order": 1},
        webhook_url="https://example.com/hook",
    )
    assert same_request(payment, payload)  # type: ignore[arg-type]
    changed = payload.model_copy(update={"amount": Decimal("11.00")})
    assert not same_request(payment, changed)  # type: ignore[arg-type]


def test_webhook_single_attempt() -> None:
    calls = {"n": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            calls["n"] += 1
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        asyncio.run(deliver_webhook(f"http://127.0.0.1:{port}/hook", {"ok": True}))
    finally:
        server.shutdown()
    assert calls["n"] == 1


def test_webhook_failure_is_not_retried_in_process() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            self.send_response(503)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        with pytest.raises(WebhookDeliveryError):
            asyncio.run(deliver_webhook(f"http://127.0.0.1:{port}/hook", {"ok": False}))
    finally:
        server.shutdown()
