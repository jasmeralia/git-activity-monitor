from __future__ import annotations

from email import message_from_string
from unittest.mock import MagicMock, patch

from git_activity_monitor.digest.mailer import send_digest_email


def _fake_settings() -> MagicMock:
    settings = MagicMock()
    settings.gmail_smtp_host = "smtp.gmail.com"
    settings.gmail_smtp_port = 587
    settings.gmail_smtp_user = "morgan@windsofstorm.net"
    settings.gmail_smtp_pass = "app-password"
    settings.gmail_smtp_from = "morgan@windsofstorm.net"
    return settings


@patch("git_activity_monitor.digest.mailer.smtplib.SMTP")
@patch("git_activity_monitor.digest.mailer.SmtpSettings")
def test_send_digest_email_relays_via_gmail_smtp(
    mock_settings_cls: MagicMock, mock_smtp_cls: MagicMock
) -> None:
    mock_settings_cls.return_value = _fake_settings()
    mock_server = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = mock_server

    send_digest_email(
        subject="[jasmeralia] Git Activity Digest - 2026-07-28",
        html_body="<p>hello</p>",
        text_body="hello",
        recipient="morgan@windsofstorm.net",
    )

    mock_smtp_cls.assert_called_once_with("smtp.gmail.com", 587)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("morgan@windsofstorm.net", "app-password")

    from_addr, to_addrs, raw_message = mock_server.sendmail.call_args.args
    assert from_addr == "morgan@windsofstorm.net"
    assert to_addrs == ["morgan@windsofstorm.net"]
    assert "From: morgan@windsofstorm.net" in raw_message
    assert "To: morgan@windsofstorm.net" in raw_message
    assert "Subject: [jasmeralia] Git Activity Digest - 2026-07-28" in raw_message
    assert "Content-Type: multipart/alternative" in raw_message

    parsed = message_from_string(raw_message)
    payloads = [
        part.get_payload(decode=True).decode("utf-8")
        for part in parsed.walk()
        if part.get_content_type() in ("text/plain", "text/html")
    ]
    assert "hello" in payloads[0]
    assert "<p>hello</p>" in payloads[1]
