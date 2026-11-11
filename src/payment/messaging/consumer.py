import asyncio
import logging
import uuid
from typing import Any

from faststream import FastStream
from faststream.exceptions import RejectMessage
from faststream.rabbit.annotations import RabbitMessage

from payment.messaging.broker import broker
from payment.messaging.publish import publish_new
from payment.messaging.retry import backoff_seconds
from payment.messaging.topology import (
    DLQ,
    MAX_DELIVERY_ATTEMPTS,
    NEW_QUEUE,
    declare_topology,
    payments_exchange,
    payments_new_queue,
)
from payment.services.processing import process_payment
from payment.services.webhook import WebhookDeliveryError

logger = logging.getLogger("payment.consumer")

app = FastStream(broker)


def attempt_of(message: RabbitMessage) -> int:
    raw = message.headers.get("x-attempt", "1")
    try:
        return max(int(raw), 1)
    except (TypeError, ValueError):
        return 1


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
    except WebhookDeliveryError:
        logger.error("webhook for %s failed after retries, sent to dlq", payment_id)
        raise RejectMessage() from None
    except Exception:
        logger.exception("payment %s failed on attempt %s", payment_id, attempt)
        if attempt >= MAX_DELIVERY_ATTEMPTS:
            raise RejectMessage() from None
        await asyncio.sleep(backoff_seconds(attempt))
        await publish_new(body, attempt=attempt + 1)


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
