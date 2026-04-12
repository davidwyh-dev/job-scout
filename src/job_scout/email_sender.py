from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def send_digest(html_body: str, config: dict, job_count: int = 0) -> None:
    to_addr = config["to"]
    from_addr = config["from"]
    password = config.get("smtp_password", "")
    prefix = config.get("subject_prefix", "[Job Scout]")

    if not password:
        logger.error("GMAIL_APP_PASSWORD not set — cannot send email")
        return

    date_str = datetime.now(timezone.utc).strftime("%b %d")
    subject = f"{prefix} {job_count} new PM jobs — {date_str}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr

    # Plain text fallback
    plain = f"Job Scout found {job_count} new PM jobs. View this email in HTML for the full digest."
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(from_addr, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        logger.info("Digest email sent to %s (%d jobs)", to_addr, job_count)
    except smtplib.SMTPException as e:
        logger.error("Failed to send email: %s", e)
        raise
