import os
import smtplib
from email.message import EmailMessage

from . import sms

SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "1025"))  # Mailpit
SENDER = "noreply@pgk-bridge.example"


def request_text(url: str, code: str) -> str:
    """The only text any channel may carry: a link and a reference code."""
    return f"You have a secure request. Open this link to answer: {url}\nReference: {code}"


def send_request_email(to: str, url: str, code: str) -> None:
    msg = EmailMessage()
    msg["From"] = SENDER
    msg["To"] = to
    msg["Subject"] = f"Secure request, ref {code}"
    msg.set_content(request_text(url, code) + "\n\nIf you did not expect this, ignore this message.")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=5) as smtp:
        smtp.send_message(msg)


def send_request(channel: str, to: str, url: str, code: str) -> None:
    if channel == "email":
        send_request_email(to, url, code)
    else:
        sms.store(to, f"Secure request, ref {code}: {url}")
