from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


def _is_retryable_discord(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        # 429 is handled inline (variable sleep); retry 5xx only
        return exc.response.status_code in {500, 502, 503, 504}
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError))


class DiscordClient:
    def __init__(self, webhook_url: str, timeout: float = 30.0) -> None:
        self._webhook_url = webhook_url
        self._client = httpx.Client(timeout=timeout)
        # Parse webhook ID and token from URL for message edit/delete operations
        parts = urlparse(webhook_url).path.rstrip("/").split("/")
        # URL format: /api/webhooks/{id}/{token}
        self._webhook_id = parts[-2]
        self._webhook_token = parts[-1]

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> DiscordClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def send_message(self, content: str) -> dict[str, Any]:
        """Send a message via webhook; returns the created message dict (includes 'id')."""
        resp = self._request(
            "POST", self._webhook_url, params={"wait": "true"}, json={"content": content}
        )
        result: dict[str, Any] = resp.json()
        return result

    def edit_message(self, message_id: str, content: str) -> dict[str, Any]:
        """Edit a previously sent webhook message."""
        url = (
            f"https://discord.com/api/webhooks"
            f"/{self._webhook_id}/{self._webhook_token}/messages/{message_id}"
        )
        resp = self._request("PATCH", url, json={"content": content})
        result: dict[str, Any] = resp.json()
        return result

    @retry(
        retry=retry_if_exception(_is_retryable_discord),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        resp = self._client.request(method, url, **kwargs)
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("X-RateLimit-Reset-After", "1.0"))
            logger.warning("Discord rate limited; sleeping %.1fs", retry_after)
            time.sleep(retry_after)
            resp.raise_for_status()
        resp.raise_for_status()
        return resp
