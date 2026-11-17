from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from payment.config import settings
from payment.messaging.retry import backoff_seconds

PAYMENTS_EXCHANGE = "payments"
DEAD_LETTER_EXCHANGE = "payments.dlx"
RETRY_EXCHANGE = "payments.retry"
NEW_QUEUE = "payments.new"
DLQ = "payments.dlq"
NEW_ROUTING_KEY = "payments.new"
DLQ_ROUTING_KEY = "payments.failed"


def retry_delay_ms(attempt: int) -> int:
    return int(backoff_seconds(attempt) * 1000)


def retry_queue_name(delay_ms: int) -> str:
    return f"payments.retry.{delay_ms}"


def retry_delays_ms(attempts: int | None = None) -> tuple[int, ...]:
    total = settings.webhook_attempts if attempts is None else attempts
    return tuple(retry_delay_ms(attempt) for attempt in range(1, total))


payments_exchange = RabbitExchange(PAYMENTS_EXCHANGE, type=ExchangeType.DIRECT, durable=True)
dead_letter_exchange = RabbitExchange(
    DEAD_LETTER_EXCHANGE,
    type=ExchangeType.DIRECT,
    durable=True,
)
retry_exchange = RabbitExchange(RETRY_EXCHANGE, type=ExchangeType.DIRECT, durable=True)
payments_new_queue = RabbitQueue(
    NEW_QUEUE,
    durable=True,
    routing_key=NEW_ROUTING_KEY,
    arguments={
        "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
        "x-dead-letter-routing-key": DLQ_ROUTING_KEY,
    },
)
payments_dlq = RabbitQueue(DLQ, durable=True, routing_key=DLQ_ROUTING_KEY)


def make_retry_queue(delay_ms: int) -> RabbitQueue:
    name = retry_queue_name(delay_ms)
    return RabbitQueue(
        name,
        durable=True,
        routing_key=name,
        arguments={
            "x-message-ttl": delay_ms,
            "x-dead-letter-exchange": PAYMENTS_EXCHANGE,
            "x-dead-letter-routing-key": NEW_ROUTING_KEY,
        },
    )


retry_queues = {delay: make_retry_queue(delay) for delay in retry_delays_ms()}


async def declare_topology(rabbit: RabbitBroker) -> None:
    new_exchange = await rabbit.declare_exchange(payments_exchange)
    dlx = await rabbit.declare_exchange(dead_letter_exchange)
    retries = await rabbit.declare_exchange(retry_exchange)
    new_queue = await rabbit.declare_queue(payments_new_queue)
    dlq = await rabbit.declare_queue(payments_dlq)
    await new_queue.bind(new_exchange, routing_key=NEW_ROUTING_KEY)
    await dlq.bind(dlx, routing_key=DLQ_ROUTING_KEY)
    for delay, queue in retry_queues.items():
        declared = await rabbit.declare_queue(queue)
        await declared.bind(retries, routing_key=retry_queue_name(delay))
