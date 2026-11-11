import asyncio
import logging
import random
import uuid
from datetime import UTC, datetime

from payment.config import settings
from payment.db.models.payment import Payment
from payment.db.session import session_factory
from payment.domain.enums import PaymentStatus
from payment.services.webhook import deliver_webhook

logger = logging.getLogger("payment.processing")


def decide_status(roll: float, success_rate: float = 0.9) -> PaymentStatus:
    if roll < success_rate:
        return PaymentStatus.SUCCEEDED
    return PaymentStatus.FAILED


def webhook_body(payment: Payment) -> dict[str, str]:
    return {
        "payment_id": str(payment.id),
        "status": payment.status.value,
        "amount": str(payment.amount),
        "currency": payment.currency.value,
    }


async def process_payment(payment_id: uuid.UUID) -> None:
    """Эмулирует шлюз, пишет статус и вызывает webhook."""
    async with session_factory() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None:
            logger.warning("payment %s not found", payment_id)
            return
        pending = payment.status == PaymentStatus.PENDING

    if pending:
        await asyncio.sleep(
            random.uniform(settings.processing_min_seconds, settings.processing_max_seconds)
        )
        outcome = decide_status(random.random(), settings.processing_success_rate)
        async with session_factory() as session:
            payment = await session.get(Payment, payment_id, with_for_update=True)
            if payment is None:
                logger.warning("payment %s not found", payment_id)
                return
            if payment.status == PaymentStatus.PENDING:
                payment.status = outcome
                payment.processed_at = datetime.now(UTC)
                await session.commit()
            body = webhook_body(payment)
            url = payment.webhook_url
        logger.info("payment %s finished with %s", payment_id, body["status"])
    else:
        async with session_factory() as session:
            payment = await session.get(Payment, payment_id)
            if payment is None:
                return
            body = webhook_body(payment)
            url = payment.webhook_url
        logger.info("payment %s already %s, retrying webhook", payment_id, body["status"])

    await deliver_webhook(url, body)
