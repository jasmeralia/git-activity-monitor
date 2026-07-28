"""Email delivery via the local MTA (`sendmail -t`).

Deliberately not SMTP/smtplib: gelfling (where this digest runs) already has
a working local postfix MTA with direct-to-MX delivery confirmed live, so
piping a `sendmail -t` message needs zero SMTP credentials to configure or
rotate.
"""

from __future__ import annotations

import logging
import subprocess  # fixed argv to the local MTA, no shell, no user input
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SENDMAIL_PATH = "/usr/sbin/sendmail"


def send_digest_email(
    subject: str,
    html_body: str,
    text_body: str,
    recipient: str,
    sendmail_path: str = SENDMAIL_PATH,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    subprocess.run(
        [sendmail_path, "-t"],
        input=msg.as_string(),
        text=True,
        check=True,
    )
    logger.info("Digest email sent to %s: %s", recipient, subject)
