import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import sms

_env = Environment(loader=FileSystemLoader(Path(__file__).resolve().parent / "templates" / "email"),
                   autoescape=select_autoescape(["html"]))

SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "1025"))  # Mailpit
# Any SMTP relay can replace Mailpit: set these three and nothing else changes.
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_STARTTLS = os.environ.get("SMTP_STARTTLS") == "1"
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
    msg.add_alternative(_env.get_template("request.html").render(url=url, code=code), subtype="html")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=5) as smtp:
        if SMTP_STARTTLS:
            smtp.starttls()
        if SMTP_USER:
            smtp.login(SMTP_USER, SMTP_PASSWORD or "")
        smtp.send_message(msg)


def send_request(channel: str, to: str, url: str, code: str) -> None:
    if channel == "email":
        send_request_email(to, url, code)
    else:
        sms.store(to, f"Secure request, ref {code}: {url}")
