import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from payment.api.deps import get_idempotency_key
from payment.domain.errors import IdempotencyConflict, PaymentNotFoundError
from payment.schemas.payment import PaymentAccepted, PaymentCreate, PaymentDetails
from payment.services import payments as payments_service

router = APIRouter(tags=["payments"])


@router.post("/payments", status_code=status.HTTP_202_ACCEPTED, response_model=PaymentAccepted)
async def create_payment(
    payload: PaymentCreate,
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
) -> PaymentAccepted:
    try:
        return await payments_service.create_payment(payload, idempotency_key)
    except IdempotencyConflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key already used with a different request",
        ) from None


@router.get("/payments/{payment_id}", response_model=PaymentDetails)
async def get_payment(payment_id: uuid.UUID) -> PaymentDetails:
    try:
        return await payments_service.get_payment(payment_id)
    except PaymentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        ) from None
