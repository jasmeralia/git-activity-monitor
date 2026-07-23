from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from git_activity_monitor.dependabot_alert_notify import build_embed, main

_WEBHOOK = "https://discord.com/api/webhooks/111/tok"


def _alert(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "number": 7,
        "html_url": "https://github.com/jasmeralia/adult-sub-monitor/security/dependabot/7",
        "dependency": {"package": {"name": "aiohttp", "ecosystem": "pip"}},
        "security_advisory": {
            "ghsa_id": "GHSA-4m7w-qmgq-4wj5",
            "cve_id": None,
            "severity": "low",
            "summary": "aiohttp: TLS Server Hostname Override Is Ignored",
        },
    }
    base.update(overrides)
    return base


def test_build_embed_created_uses_severity_color() -> None:
    embed = build_embed(
        "created",
        _alert(security_advisory={**_alert()["security_advisory"], "severity": "critical"}),
        "jasmeralia/adult-sub-monitor",
    )
    assert embed is not None
    assert embed["color"] == 0xB30000
    assert embed["title"] == "\U0001f534 New Dependabot Alert"
    assert embed["url"] == _alert()["html_url"]


def test_build_embed_fixed_is_green() -> None:
    embed = build_embed("fixed", _alert(), "jasmeralia/adult-sub-monitor")
    assert embed is not None
    assert embed["color"] == 0x2ECC71
    assert embed["title"] == "✅ Dependabot Alert Resolved"


def test_build_embed_dismissed_includes_reason() -> None:
    alert = _alert(dismissed_reason="tolerable_risk")
    embed = build_embed("dismissed", alert, "jasmeralia/adult-sub-monitor")
    assert embed is not None
    assert embed["color"] == 0x95A5A6
    reason_field = next(f for f in embed["fields"] if f["name"] == "Dismissed reason")
    assert reason_field["value"] == "tolerable_risk"


def test_build_embed_falls_back_to_cve_id() -> None:
    alert = _alert(
        security_advisory={
            **_alert()["security_advisory"],
            "ghsa_id": None,
            "cve_id": "CVE-2026-1234",
        }
    )
    embed = build_embed("created", alert, "jasmeralia/adult-sub-monitor")
    assert embed is not None
    advisory_field = next(f for f in embed["fields"] if f["name"] == "Advisory")
    assert advisory_field["value"] == "CVE-2026-1234"


def test_build_embed_skips_assignees_changed() -> None:
    assert build_embed("assignees_changed", _alert(), "jasmeralia/adult-sub-monitor") is None


@respx.mock
def test_main_posts_embed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    event = {
        "action": "created",
        "alert": _alert(),
        "repository": {"full_name": "jasmeralia/adult-sub-monitor"},
    }
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event))

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", _WEBHOOK)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    route = respx.post(_WEBHOOK).mock(return_value=httpx.Response(200, json={"id": "1"}))

    assert main() == 0
    assert route.called


@respx.mock
def test_main_skips_without_posting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    event = {
        "action": "assignees_changed",
        "alert": _alert(),
        "repository": {"full_name": "jasmeralia/adult-sub-monitor"},
    }
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event))

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", _WEBHOOK)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    route = respx.post(_WEBHOOK).mock(return_value=httpx.Response(200, json={"id": "1"}))

    assert main() == 0
    assert not route.called
