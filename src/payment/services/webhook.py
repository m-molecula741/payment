import asyncio
import logging
from typing import Any

import httpx

from payment.config import settings
from payment.messaging.retry import backoff_seconds

logger = logging.getLogger("payment.webhook")


class WebhookDeliveryError(Exception):
    pass


async def deliver_webhook(url: str, payload: dict[str, Any]) -> None:
    """Шлёт результат платежа. Три попытки, после каждой неудачи пауза 1с, 2с, 4с."""
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds) as client:
        for attempt in range(1, settings.webhook_attempts + 1):
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("webhook %s attempt %s failed: %s", url, attempt, exc)
                await asyncio.sleep(backoff_seconds(attempt))
    raise WebhookDeliveryError(str(last_error)) from last_error
