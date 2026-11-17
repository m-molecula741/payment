from datetime import UTC, datetime
from enum import StrEnum

from payment.domain.enums import PaymentStatus


class Step(StrEnum):
    CHARGE = "charge"
    WEBHOOK = "webhook"
    DONE = "done"
    BUSY = "busy"
    MISSING = "missing"


def claim_is_fresh(claimed_at: datetime | None, now: datetime, lease_seconds: float) -> bool:
    if claimed_at is None:
        return False
    if claimed_at.tzinfo is None:
        claimed_at = claimed_at.replace(tzinfo=UTC)
    return (now - claimed_at).total_seconds() < lease_seconds


def plan_processing(
    status: PaymentStatus,
    claimed_at: datetime | None,
    webhook_delivered_at: datetime | None,
    webhook_claimed_at: datetime | None,
    now: datetime,
    lease_seconds: float,
) -> Step:
    """Шлюз запускает только тот, кто первым захватил pending-платёж."""
    if status is PaymentStatus.PENDING:
        if claim_is_fresh(claimed_at, now, lease_seconds):
            return Step.BUSY
        return Step.CHARGE
    if webhook_delivered_at is not None:
        return Step.DONE
    if claim_is_fresh(webhook_claimed_at, now, lease_seconds):
        return Step.BUSY
    return Step.WEBHOOK
