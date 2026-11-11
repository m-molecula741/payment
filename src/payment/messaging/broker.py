from faststream.rabbit import RabbitBroker

from payment.config import settings

broker = RabbitBroker(
    settings.rabbitmq_url,
    fail_fast=False,
    reconnect_interval=2.0,
)
