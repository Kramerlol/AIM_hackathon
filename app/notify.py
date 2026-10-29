"""Tell the doctor. The Matrix bot registers itself as the sender when it starts."""
import logging
import os
from collections.abc import Callable

log = logging.getLogger("notify")

outbox: list[tuple[str | None, str]] = []  # (room, text); shown on /dev
_sender: Callable[[str, str], None] | None = None


def set_sender(fn: Callable[[str, str], None] | None) -> None:
    global _sender
    _sender = fn


def notify_doctor(room_id: str | None, text: str) -> None:
    room = room_id or os.environ.get("MATRIX_DEFAULT_ROOM")
    outbox.append((room, text))
    if _sender and room:
        try:
            _sender(room, text)
        except Exception:  # a chat problem must never break the request flow
            log.exception("could not notify room %s", room)
