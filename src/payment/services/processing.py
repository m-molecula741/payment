import asyncio
import logging
import random
import uuid

from payment.config import settings
from payment.db.repositories.payments import PaymentRepository
from payment.domain.claim import Step
from payment.domain.enums import PaymentStatus
from payment.services.webhook import WebhookDeliveryError, deliver_webhook

logger = logging.getLogger("payment.processing")


class PaymentBusy(Exception):
    pass


def decide_status(roll: float, success_rate: float = 0.9) -> PaymentStatus:
    if roll < success_rate:
        return PaymentStatus.SUCCEEDED
    return PaymentStatus.FAILED


async def process_payment(payment_id: uuid.UUID) -> None:
    """Захватывает платёж, вне транзакции зовёт шлюз и один раз шлёт webhook."""
    repo = PaymentRepository()
    action = await repo.begin_processing(payment_id)
    if action.step is Step.MISSING:
        logger.warning("payment %s not found", payment_id)
        return
    if action.step is Step.DONE:
        return
    if action.step is Step.BUSY:
        raise PaymentBusy
    if action.step is Step.CHARGE:
        await asyncio.sleep(
            random.uniform(settings.processing_min_seconds, settings.processing_max_seconds)
        )
        outcome = decide_status(random.random(), settings.processing_success_rate)
        action = await repo.finish_gateway(payment_id, outcome)
        if action.step is Step.MISSING:
            logger.warning("payment %s not found", payment_id)
            return
        if action.step is Step.DONE:
            return
        if action.step is Step.BUSY:
            raise PaymentBusy
        logger.info("payment %s finished with %s", payment_id, outcome.value)

    if action.url is None or action.body is None:
        return
    try:
        await deliver_webhook(action.url, action.body)
    except WebhookDeliveryError:
        await repo.release_webhook(payment_id)
        raise
    await repo.mark_webhook_delivered(payment_id)
