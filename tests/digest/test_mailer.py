from __future__ import annotations

from email import message_from_string
from unittest.mock import MagicMock, patch

from git_activity_monitor.digest.mailer import send_digest_email


@patch("git_activity_monitor.digest.mailer.subprocess.run")
def test_send_digest_email_pipes_mime_message_to_sendmail(mock_run: MagicMock) -> None:
    send_digest_email(
        subject="[jasmeralia] Git Activity Digest - 2026-07-28",
        html_body="<p>hello</p>",
        text_body="hello",
        recipient="morgan@windsofstorm.net",
        sendmail_path="/usr/sbin/sendmail",
    )

    mock_run.assert_called_once()
    call_args, call_kwargs = mock_run.call_args
    assert call_args[0] == ["/usr/sbin/sendmail", "-t"]
    assert call_kwargs["check"] is True
    assert call_kwargs["text"] is True

    raw_message = call_kwargs["input"]
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
