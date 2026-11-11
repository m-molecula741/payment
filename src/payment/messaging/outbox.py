import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from payment.config import settings
from payment.db.models.outbox import OutboxEvent
from payment.db.session import session_factory
from payment.messaging.broker import broker
from payment.messaging.publish import publish_new
from payment.messaging.topology import declare_topology

logger = logging.getLogger("payment.outbox")


async def publish_pending() -> int:
    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.created_at)
                .limit(settings.outbox_batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()
        if not rows:
            return 0

        published = 0
        for event in rows:
            try:
                await publish_new(event.payload, attempt=1)
            except Exception:
                event.attempts += 1
                logger.exception("failed to publish outbox event %s", event.id)
                continue
            event.published_at = datetime.now(UTC)
            published += 1
        await session.commit()
        return published


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    await broker.start()
    await declare_topology(broker)
    logger.info("outbox relay started")
    try:
        while True:
            try:
                published = await publish_pending()
                if published:
                    logger.info("published %s outbox events", published)
            except Exception:
                logger.exception("outbox poll failed")
            await asyncio.sleep(settings.outbox_poll_interval_seconds)
    finally:
        await broker.stop()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
