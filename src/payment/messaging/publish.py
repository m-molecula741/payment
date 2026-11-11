from typing import Any

from payment.messaging.broker import broker
from payment.messaging.topology import NEW_ROUTING_KEY, payments_exchange


async def publish_new(body: dict[str, Any], attempt: int = 1) -> None:
    await broker.publish(
        body,
        exchange=payments_exchange,
        routing_key=NEW_ROUTING_KEY,
        headers={"x-attempt": str(attempt)},
        persist=True,
    )
