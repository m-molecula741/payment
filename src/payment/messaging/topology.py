from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

PAYMENTS_EXCHANGE = "payments"
DEAD_LETTER_EXCHANGE = "payments.dlx"
NEW_QUEUE = "payments.new"
DLQ = "payments.dlq"
NEW_ROUTING_KEY = "payments.new"
DLQ_ROUTING_KEY = "payments.failed"
MAX_DELIVERY_ATTEMPTS = 3

payments_exchange = RabbitExchange(PAYMENTS_EXCHANGE, type=ExchangeType.DIRECT, durable=True)
dead_letter_exchange = RabbitExchange(
    DEAD_LETTER_EXCHANGE,
    type=ExchangeType.DIRECT,
    durable=True,
)
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


async def declare_topology(rabbit: RabbitBroker) -> None:
    new_exchange = await rabbit.declare_exchange(payments_exchange)
    dlx = await rabbit.declare_exchange(dead_letter_exchange)
    new_queue = await rabbit.declare_queue(payments_new_queue)
    dlq = await rabbit.declare_queue(payments_dlq)
    await new_queue.bind(new_exchange, routing_key=NEW_ROUTING_KEY)
    await dlq.bind(dlx, routing_key=DLQ_ROUTING_KEY)
