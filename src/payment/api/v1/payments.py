import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from payment.api.deps import SessionDep, get_idempotency_key
from payment.schemas.payment import PaymentAccepted, PaymentCreate, PaymentDetails
from payment.services import payments as payments_service
from payment.services.payments import PaymentNotFoundError

router = APIRouter(tags=["payments"])


@router.post("/payments", status_code=status.HTTP_202_ACCEPTED, response_model=PaymentAccepted)
async def create_payment(
    payload: PaymentCreate,
    session: SessionDep,
    idempotency_key: Annotated[str, Depends(get_idempotency_key)],
) -> PaymentAccepted:
    return await payments_service.create_payment(session, payload, idempotency_key)


@router.get("/payments/{payment_id}", response_model=PaymentDetails)
async def get_payment(payment_id: uuid.UUID, session: SessionDep) -> PaymentDetails:
    try:
        return await payments_service.get_payment(session, payment_id)
    except PaymentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        ) from None
