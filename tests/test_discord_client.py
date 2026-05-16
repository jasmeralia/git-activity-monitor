from __future__ import annotations

import httpx
import pytest
import respx

from github_activity_monitor.discord_client import DiscordClient

_WEBHOOK = "https://discord.com/api/webhooks/111/tok"


@pytest.fixture
def dc() -> DiscordClient:
    return DiscordClient(webhook_url=_WEBHOOK)


@respx.mock
def test_send_message_returns_id(dc: DiscordClient) -> None:
    respx.post(_WEBHOOK).mock(
        return_value=httpx.Response(200, json={"id": "9999", "content": "hello"})
    )
    msg = dc.send_message("hello")
    assert msg["id"] == "9999"


@respx.mock
def test_send_message_uses_wait_true(dc: DiscordClient) -> None:
    route = respx.post(_WEBHOOK).mock(return_value=httpx.Response(200, json={"id": "1"}))
    dc.send_message("test")
    assert route.called
    assert "wait" in str(route.calls.last.request.url)


@respx.mock
def test_edit_message_sends_patch(dc: DiscordClient) -> None:
    edit_url = "https://discord.com/api/webhooks/111/tok/messages/42"
    respx.patch(edit_url).mock(
        return_value=httpx.Response(200, json={"id": "42", "content": "updated"})
    )
    result = dc.edit_message("42", "updated")
    assert result["id"] == "42"


@respx.mock
def test_retries_on_503(dc: DiscordClient) -> None:
    route = respx.post(_WEBHOOK)
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(200, json={"id": "5"}),
    ]
    msg = dc.send_message("retry test")
    assert msg["id"] == "5"


def test_webhook_url_parsing() -> None:
    dc = DiscordClient("https://discord.com/api/webhooks/99999/my-secret-token")
    assert dc._webhook_id == "99999"
    assert dc._webhook_token == "my-secret-token"


@respx.mock
def test_send_sets_allowed_mentions(dc: DiscordClient) -> None:
    route = respx.post(_WEBHOOK).mock(return_value=httpx.Response(200, json={"id": "1"}))
    dc.send_message("hello @everyone")
    body = route.calls.last.request.read()
    import json as _json
    payload = _json.loads(body)
    assert payload.get("allowed_mentions") == {"parse": []}


@respx.mock
def test_429_inline_retry(dc: DiscordClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("github_activity_monitor.discord_client.time.sleep", lambda _: None)
    respx.post(_WEBHOOK).mock(
        side_effect=[
            httpx.Response(429, headers={"X-RateLimit-Reset-After": "0.5"}),
            httpx.Response(429, headers={"X-RateLimit-Reset-After": "0.5"}),
            httpx.Response(200, json={"id": "7"}),
        ]
    )
    msg = dc.send_message("rate limited")
    assert msg["id"] == "7"
