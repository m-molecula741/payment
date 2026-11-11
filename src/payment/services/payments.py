import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from payment.db.models.outbox import OutboxEvent
from payment.db.models.payment import Payment
from payment.domain.enums import PaymentStatus
from payment.messaging.topology import NEW_ROUTING_KEY
from payment.schemas.payment import PaymentAccepted, PaymentCreate, PaymentDetails


class PaymentNotFoundError(Exception):
    pass


def _accepted(payment: Payment) -> PaymentAccepted:
    return PaymentAccepted(
        payment_id=payment.id,
        status=payment.status,
        created_at=payment.created_at,
    )


async def _by_idempotency_key(session: AsyncSession, idempotency_key: str) -> Payment | None:
    return await session.scalar(select(Payment).where(Payment.idempotency_key == idempotency_key))


async def create_payment(
    session: AsyncSession,
    data: PaymentCreate,
    idempotency_key: str,
) -> PaymentAccepted:
    """Сохраняет платёж и событие outbox в одной транзакции."""
    existing = await _by_idempotency_key(session, idempotency_key)
    if existing is not None:
        return _accepted(existing)

    payment = Payment(
        amount=data.amount,
        currency=data.currency,
        description=data.description,
        meta=data.metadata,
        status=PaymentStatus.PENDING,
        idempotency_key=idempotency_key,
        webhook_url=str(data.webhook_url),
    )
    session.add(payment)
    try:
        await session.flush()
        session.add(
            OutboxEvent(
                event_type=NEW_ROUTING_KEY,
                payload={"payment_id": str(payment.id)},
            )
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await _by_idempotency_key(session, idempotency_key)
        if existing is None:
            raise
        return _accepted(existing)

    await session.refresh(payment)
    return _accepted(payment)


async def get_payment(session: AsyncSession, payment_id: uuid.UUID) -> PaymentDetails:
    """Возвращает платёж по идентификатору."""
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise PaymentNotFoundError
    return PaymentDetails.model_validate(payment)
