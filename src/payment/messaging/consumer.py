import asyncio
import logging
import uuid
from typing import Any

from faststream import FastStream
from faststream.exceptions import RejectMessage
from faststream.rabbit.annotations import RabbitMessage

from payment.config import settings
from payment.messaging.broker import broker
from payment.messaging.publish import publish_later
from payment.messaging.topology import (
    DLQ,
    NEW_QUEUE,
    declare_topology,
    payments_exchange,
    payments_new_queue,
    retry_delay_ms,
)
from payment.services.processing import PaymentBusy, process_payment
from payment.services.webhook import WebhookDeliveryError

logger = logging.getLogger("payment.consumer")

app = FastStream(broker)


def attempt_of(message: RabbitMessage) -> int:
    raw = message.headers.get("x-attempt", "1")
    try:
        return max(int(raw), 1)
    except (TypeError, ValueError):
        return 1


def give_up(attempt: int, max_attempts: int | None = None) -> bool:
    limit = settings.webhook_attempts if max_attempts is None else max_attempts
    return attempt >= limit


@broker.subscriber(payments_new_queue, payments_exchange)
async def handle_new_payment(body: dict[str, Any], message: RabbitMessage) -> None:
    attempt = attempt_of(message)
    try:
        payment_id = uuid.UUID(str(body["payment_id"]))
    except (KeyError, TypeError, ValueError):
        logger.error("drop message without payment_id, attempt %s", attempt)
        raise RejectMessage() from None

    try:
        await process_payment(payment_id)
    except PaymentBusy:
        logger.info("payment %s is claimed, retry in 1s", payment_id)
        await publish_later(body, retry_delay_ms(1), attempt)
    except WebhookDeliveryError:
        await _retry_or_drop(body, attempt, payment_id)
    except Exception:
        logger.exception("payment %s failed on attempt %s", payment_id, attempt)
        await _retry_or_drop(body, attempt, payment_id)


async def _retry_or_drop(body: dict[str, Any], attempt: int, payment_id: uuid.UUID) -> None:
    if give_up(attempt):
        logger.error("payment %s dropped after attempt %s", payment_id, attempt)
        raise RejectMessage()
    delay_ms = retry_delay_ms(attempt)
    logger.info("payment %s scheduled in %sms, next attempt %s", payment_id, delay_ms, attempt + 1)
    await publish_later(body, delay_ms, attempt + 1)


@app.after_startup
async def prepare() -> None:
    await declare_topology(broker)
    logger.info("consumer ready, queues: %s, %s", NEW_QUEUE, DLQ)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
