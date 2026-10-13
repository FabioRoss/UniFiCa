"""Standard Web Push (RFC 8030 + VAPID) through pywebpush. Works with the
browsers' own push services (Google FCM endpoint, Mozilla, Apple), no
account or API key needed: the VAPID keypair identifies us."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pywebpush import WebPushException, webpush

from ..config import settings

log = logging.getLogger("openunifi.webpush")

OK, GONE, ERROR = "ok", "gone", "error"


def _send(endpoint: str, keys: dict[str, str], payload: dict[str, Any], vapid_private: str,
          urgency: str) -> str:
    try:
        webpush(
            subscription_info={"endpoint": endpoint, "keys": keys},
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=vapid_private,
            vapid_claims={"sub": settings.vapid_contact},
            ttl=24 * 3600,
            headers={"Urgency": urgency},
            timeout=20,
        )
        return OK
    except WebPushException as e:
        status = e.response.status_code if e.response is not None else 0
        if status in (404, 410):
            return GONE  # unsubscribed or expired: drop it
        log.info("push to %s failed: %s", endpoint[:60], e)
        return ERROR
    except Exception as e:
        log.info("push to %s failed: %s", endpoint[:60], e)
        return ERROR


async def send(endpoint: str, keys: dict[str, str], payload: dict[str, Any], vapid_private: str,
               urgency: str = "normal") -> str:
    return await asyncio.to_thread(_send, endpoint, keys, payload, vapid_private, urgency)
