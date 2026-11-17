import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from payment.config import settings
from payment.db.models.outbox import OutboxEvent
from payment.db.models.payment import Payment
from payment.db.session import session_factory
from payment.domain.claim import Step, plan_processing
from payment.domain.enums import PaymentStatus
from payment.domain.errors import IdempotencyConflict, PaymentNotFoundError
from payment.messaging.topology import NEW_ROUTING_KEY
from payment.schemas.payment import PaymentAccepted, PaymentCreate, PaymentDetails


@dataclass(frozen=True)
class NextAction:
    step: Step
    url: str | None = None
    body: dict[str, str] | None = None


def same_request(payment: Payment, data: PaymentCreate) -> bool:
    return (
        payment.amount == data.amount
        and payment.currency == data.currency
        and payment.description == data.description
        and payment.meta == data.metadata
        and payment.webhook_url == str(data.webhook_url)
    )


def _accepted(payment: Payment) -> PaymentAccepted:
    return PaymentAccepted(
        payment_id=payment.id,
        status=payment.status,
        created_at=payment.created_at,
    )


def _webhook_body(payment: Payment) -> dict[str, str]:
    return {
        "payment_id": str(payment.id),
        "status": payment.status.value,
        "amount": str(payment.amount),
        "currency": payment.currency.value,
    }


class PaymentRepository:
    async def _by_key(self, session: AsyncSession, idempotency_key: str) -> Payment | None:
        return await session.scalar(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )

    async def create_with_outbox(
        self, data: PaymentCreate, idempotency_key: str
    ) -> PaymentAccepted:
        """Платёж и событие outbox сохраняются одним коммитом."""
        async with session_factory() as session:
            try:
                existing = await self._by_key(session, idempotency_key)
                if existing is not None:
                    accepted = _accepted(existing)
                    matches = same_request(existing, data)
                    await session.rollback()
                    if not matches:
                        raise IdempotencyConflict
                    return accepted

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
                await session.flush()
                session.add(
                    OutboxEvent(
                        event_type=NEW_ROUTING_KEY,
                        payload={"payment_id": str(payment.id)},
                    )
                )
                await session.commit()
                return _accepted(payment)
            except IntegrityError:
                await session.rollback()
                existing = await self._by_key(session, idempotency_key)
                if existing is None:
                    raise
                if not same_request(existing, data):
                    raise IdempotencyConflict from None
                return _accepted(existing)
            except Exception:
                await session.rollback()
                raise

    async def get_details(self, payment_id: uuid.UUID) -> PaymentDetails:
        async with session_factory() as session:
            payment = await session.get(Payment, payment_id)
            if payment is None:
                raise PaymentNotFoundError
            return PaymentDetails.model_validate(payment)

    async def begin_processing(self, payment_id: uuid.UUID) -> NextAction:
        """Блокирует строку и либо захватывает шлюз, либо забирает отправку webhook."""
        now = datetime.now(UTC)
        async with session_factory() as session:
            payment = await session.get(Payment, payment_id, with_for_update=True)
            if payment is None:
                await session.rollback()
                return NextAction(Step.MISSING)
            step = plan_processing(
                payment.status,
                payment.claimed_at,
                payment.webhook_delivered_at,
                payment.webhook_claimed_at,
                now,
                settings.claim_lease_seconds,
            )
            if step is Step.DONE:
                await session.rollback()
                return NextAction(Step.DONE)
            if step is Step.BUSY:
                await session.rollback()
                return NextAction(Step.BUSY)
            if step is Step.CHARGE:
                payment.claimed_at = now
                await session.commit()
                return NextAction(Step.CHARGE)
            payment.webhook_claimed_at = now
            action = NextAction(Step.WEBHOOK, payment.webhook_url, _webhook_body(payment))
            await session.commit()
            return action

    async def finish_gateway(self, payment_id: uuid.UUID, outcome: PaymentStatus) -> NextAction:
        """Пишет результат шлюза и забирает отправку webhook, если её ещё никто не взял."""
        now = datetime.now(UTC)
        async with session_factory() as session:
            payment = await session.get(Payment, payment_id, with_for_update=True)
            if payment is None:
                await session.rollback()
                return NextAction(Step.MISSING)
            if payment.status is PaymentStatus.PENDING:
                payment.status = outcome
                payment.processed_at = now
            step = plan_processing(
                payment.status,
                payment.claimed_at,
                payment.webhook_delivered_at,
                payment.webhook_claimed_at,
                now,
                settings.claim_lease_seconds,
            )
            if step is Step.DONE:
                await session.commit()
                return NextAction(Step.DONE)
            if step is Step.BUSY:
                await session.commit()
                return NextAction(Step.BUSY)
            payment.webhook_claimed_at = now
            action = NextAction(Step.WEBHOOK, payment.webhook_url, _webhook_body(payment))
            await session.commit()
            return action

    async def release_webhook(self, payment_id: uuid.UUID) -> None:
        async with session_factory() as session:
            payment = await session.get(Payment, payment_id, with_for_update=True)
            if payment is not None and payment.webhook_delivered_at is None:
                payment.webhook_claimed_at = None
                await session.commit()
                return
            await session.rollback()

    async def mark_webhook_delivered(self, payment_id: uuid.UUID) -> None:
        async with session_factory() as session:
            payment = await session.get(Payment, payment_id, with_for_update=True)
            if payment is None:
                await session.rollback()
                return
            payment.webhook_delivered_at = datetime.now(UTC)
            payment.webhook_claimed_at = None
            await session.commit()
