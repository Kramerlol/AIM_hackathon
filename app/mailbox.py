"""Read the emails Mailpit has caught, so the app can show them in its own light inbox (/mail)."""
import os

import httpx

MAILPIT_API = os.environ.get("MAILPIT_API", "http://localhost:8025")


class MailboxUnavailable(Exception):
    pass


def _get(path: str) -> dict:
    try:
        r = httpx.get(f"{MAILPIT_API}/api/v1/{path}", timeout=3)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        raise MailboxUnavailable(str(exc)) from exc


def list_messages(limit: int = 50) -> list[dict]:
    data = _get(f"messages?limit={limit}")
    return [{"id": m["ID"], "to": m["To"][0]["Address"] if m["To"] else "", "subject": m["Subject"],
             "created": m["Created"][11:19], "snippet": m.get("Snippet", "")}
            for m in data["messages"]]


def get_message(message_id: str) -> dict:
    m = _get(f"message/{message_id}")
    return {"id": m["ID"], "to": m["To"][0]["Address"] if m["To"] else "", "subject": m["Subject"],
            "created": m["Date"][11:19], "html": m.get("HTML") or "", "text": m.get("Text") or ""}
