import uuid

from payment.db.repositories.payments import PaymentRepository
from payment.domain.errors import IdempotencyConflict, PaymentNotFoundError
from payment.schemas.payment import PaymentAccepted, PaymentCreate, PaymentDetails

__all__ = [
    "IdempotencyConflict",
    "PaymentNotFoundError",
    "create_payment",
    "get_payment",
]


async def create_payment(data: PaymentCreate, idempotency_key: str) -> PaymentAccepted:
    return await PaymentRepository().create_with_outbox(data, idempotency_key)


async def get_payment(payment_id: uuid.UUID) -> PaymentDetails:
    return await PaymentRepository().get_details(payment_id)
