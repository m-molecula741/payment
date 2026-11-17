from typing import Any

from payment.messaging.broker import broker
from payment.messaging.topology import (
    NEW_ROUTING_KEY,
    payments_exchange,
    retry_exchange,
    retry_queue_name,
    retry_queues,
)


async def publish_new(body: dict[str, Any], attempt: int = 1) -> None:
    await broker.publish(
        body,
        exchange=payments_exchange,
        routing_key=NEW_ROUTING_KEY,
        headers={"x-attempt": str(attempt)},
        persist=True,
    )


async def publish_later(body: dict[str, Any], delay_ms: int, attempt: int) -> None:
    """Кладёт сообщение в TTL-очередь. По истечении срока брокер вернёт его в payments.new."""
    if delay_ms not in retry_queues:
        raise KeyError(f"no retry queue for {delay_ms} ms")
    await broker.publish(
        body,
        exchange=retry_exchange,
        routing_key=retry_queue_name(delay_ms),
        headers={"x-attempt": str(attempt)},
        persist=True,
    )
