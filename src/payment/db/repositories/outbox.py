import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from payment.db.models.outbox import OutboxEvent
from payment.db.session import session_factory

logger = logging.getLogger("payment.outbox")


class OutboxRepository:
    async def publish_pending(
        self,
        limit: int,
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> int:
        """Публикует пачку и одним коммитом отмечает, что ушло в брокер."""
        async with session_factory() as session:
            try:
                rows = list(
                    (
                        await session.scalars(
                            select(OutboxEvent)
                            .where(OutboxEvent.published_at.is_(None))
                            .order_by(OutboxEvent.created_at)
                            .limit(limit)
                            .with_for_update(skip_locked=True)
                        )
                    ).all()
                )
                if not rows:
                    await session.rollback()
                    return 0

                published = 0
                for event in rows:
                    try:
                        await send(event.payload)
                    except Exception:
                        event.attempts += 1
                        logger.exception("failed to publish outbox event %s", event.id)
                        continue
                    event.published_at = datetime.now(UTC)
                    published += 1
                await session.commit()
                return published
            except Exception:
                await session.rollback()
                raise
