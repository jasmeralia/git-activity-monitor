"""Email delivery via Gmail SMTP (STARTTLS).

Switched from local sendmail (direct-to-MX from gelfling's bare EC2 hostname
identity) because Gmail was flagging that delivery path as spam -- relaying
through an authenticated Gmail account with a matching From address fixes
SPF/DKIM/DMARC alignment. Credentials come from ~/.env (GMAIL_SMTP_HOST,
GMAIL_SMTP_PORT, GMAIL_SMTP_USER, GMAIL_SMTP_PASS, GMAIL_SMTP_FROM) -- see
rincity-infra's AGENTS.md ("Odoo Task Deadline Digest") for where those
values live; this digest and the Odoo deadline digest share the same
~/.env file on gelfling.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class SmtpSettings(BaseSettings):
    """Gmail SMTP relay credentials, loaded from ~/.env."""

    model_config = SettingsConfigDict(
        env_file=str(Path.home() / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gmail_smtp_host: str = "smtp.gmail.com"
    gmail_smtp_port: int = 587
    gmail_smtp_user: str
    gmail_smtp_pass: str
    gmail_smtp_from: str


def send_digest_email(subject: str, html_body: str, text_body: str, recipient: str) -> None:
    settings = SmtpSettings()

    msg = MIMEMultipart("alternative")
    msg["From"] = settings.gmail_smtp_from
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(settings.gmail_smtp_host, settings.gmail_smtp_port) as server:
        server.starttls()
        server.login(settings.gmail_smtp_user, settings.gmail_smtp_pass)
        server.sendmail(settings.gmail_smtp_from, [recipient], msg.as_string())
    logger.info("Digest email sent to %s: %s", recipient, subject)
