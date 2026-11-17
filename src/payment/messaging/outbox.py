import asyncio
import logging

from payment.config import settings
from payment.db.repositories.outbox import OutboxRepository
from payment.messaging.broker import broker
from payment.messaging.publish import publish_new
from payment.messaging.topology import declare_topology

logger = logging.getLogger("payment.outbox")


async def publish_pending() -> int:
    return await OutboxRepository().publish_pending(settings.outbox_batch_size, publish_new)


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
