import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from payment.config import settings
from payment.domain.enums import PaymentStatus
from payment.messaging.consumer import attempt_of
from payment.messaging.retry import backoff_seconds
from payment.services.processing import decide_status
from payment.services.webhook import WebhookDeliveryError, deliver_webhook


def test_backoff_doubles() -> None:
    assert backoff_seconds(1) == 1
    assert backoff_seconds(2) == 2
    assert backoff_seconds(3) == 4


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


def test_webhook_retries_until_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("payment.services.webhook.backoff_seconds", lambda _attempt: 0)
    codes = iter((500, 500, 200))

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            self.send_response(next(codes))
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


def test_webhook_pauses_one_two_four(monkeypatch: pytest.MonkeyPatch) -> None:
    pauses: list[float] = []

    async def record(seconds: float) -> None:
        pauses.append(seconds)

    monkeypatch.setattr("payment.services.webhook.asyncio.sleep", record)

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

    assert pauses == [1, 2, 4]


def test_webhook_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "webhook_attempts", 2)
    monkeypatch.setattr("payment.services.webhook.backoff_seconds", lambda _attempt: 0)

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
