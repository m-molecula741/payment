import logging
from typing import Any

import httpx

from payment.config import settings

logger = logging.getLogger("payment.webhook")


class WebhookDeliveryError(Exception):
    pass


async def deliver_webhook(url: str, payload: dict[str, Any]) -> None:
    """Одна попытка POST. Повтор делает брокер через TTL-очередь."""
    async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds) as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("webhook %s failed: %s", url, exc)
            raise WebhookDeliveryError(str(exc)) from exc
