"""Matrix bot for Dr. Hofer: `!request ...` sends a request, and the bot posts the outcome.

Runs inside the FastAPI process (see lifespan in main.py), because the stub backend is in memory.
Rooms must be unencrypted: the brief does not ask for end-to-end encryption.
"""
import asyncio
import logging
import os
import shlex
import time

from . import notify, service

log = logging.getLogger("matrix_bot")

USAGE = (
    "Usage: !request <lab|rehab> patient=<id> to=<email or phone> person=\"<full name>\" "
    "[org=\"<organisation>\"]\n"
    "Example: !request lab patient=maria-beispiel to=eva.brandl@labor-kanal.example "
    "person=\"Dr. Eva Brandl\" org=\"Labor Kanalstrasse\""
)


class CommandError(ValueError):
    pass


def allowed_users() -> set[str]:
    raw = os.environ.get("MATRIX_ALLOWED_USERS", "@lena.hofer:klinikum.example")
    return {u.strip() for u in raw.split(",") if u.strip()}


def parse_command(text: str) -> dict:
    """Parse `!request lab patient=... to=... person="..." org="..."` into fields."""
    try:
        words = shlex.split(text.strip())
    except ValueError:
        raise CommandError("I could not read the quotes in your command.\n" + USAGE)
    if len(words) < 2 or words[0] != "!request":
        raise CommandError(USAGE)
    fields = {}
    for word in words[2:]:
        key, sep, value = word.partition("=")
        if not sep or key not in {"patient", "to", "person", "org"}:
            raise CommandError(f"I did not understand '{word}'.\n" + USAGE)
        fields[key] = value
    missing = [k for k in ("patient", "to", "person") if not fields.get(k)]
    if missing:
        raise CommandError(f"Missing: {', '.join(missing)}.\n" + USAGE)
    return {"kind": words[1].lower(), "patient_id": fields["patient"], "to": fields["to"],
            "person": fields["person"], "org": fields.get("org", "")}


def handle_message(sender: str, room_id: str, text: str) -> str | None:
    """Return the reply for a chat message, or None to stay silent. Blocking: run in a thread."""
    text = text.strip()
    if not text.startswith("!"):
        return None
    if sender not in allowed_users():
        return "You are not allowed to send requests from this room."
    if text.split()[0] == "!help":
        return USAGE
    if text.split()[0] != "!request":
        return None
    try:
        cmd = parse_command(text)
        result = service.create_and_send(room_id=room_id, matrix_user=sender, **cmd)
    except (CommandError, service.RequestError) as exc:
        return str(exc)
    except OSError as exc:
        log.exception("send failed")
        return f"The request could not be sent ({exc.__class__.__name__}). Nothing was sent."
    return (f"Request {result['code']} sent to {cmd['person']} by {result['channel']}. "
            "I will post here when they answer.")


async def run_bot(stop: asyncio.Event) -> None:
    from nio import AsyncClient, InviteMemberEvent, RoomMessageText

    client = AsyncClient(os.environ["MATRIX_HOMESERVER"], os.environ["MATRIX_BOT_USER"])
    login = await client.login(os.environ["MATRIX_BOT_PASSWORD"])
    if not getattr(login, "access_token", None):
        raise RuntimeError(f"Matrix login failed: {login}")
    loop = asyncio.get_running_loop()

    async def say(room_id: str, text: str) -> None:
        await client.room_send(room_id, "m.room.message", {"msgtype": "m.text", "body": text})

    # FastAPI runs sync routes in threads, so hand notifications over to this loop.
    notify.set_sender(lambda room, text: asyncio.run_coroutine_threadsafe(say(room, text), loop))

    # First sync: take in the current state but never act on old messages after a restart.
    await client.sync(timeout=5000, full_state=True)
    started_ms = int(time.time() * 1000)
    for room_id in list(client.invited_rooms):
        await client.join(room_id)

    async def on_invite(room, event):
        if event.state_key == client.user_id:
            await client.join(room.room_id)

    async def on_message(room, event):
        if event.sender == client.user_id or event.server_timestamp < started_ms:
            return
        reply = await asyncio.to_thread(handle_message, event.sender, room.room_id, event.body)
        if reply:
            await say(room.room_id, reply)

    client.add_event_callback(on_invite, InviteMemberEvent)
    client.add_event_callback(on_message, RoomMessageText)
    log.info("Matrix bot running as %s", client.user_id)

    sync_task = asyncio.create_task(client.sync_forever(timeout=30000))
    await stop.wait()
    notify.set_sender(None)
    sync_task.cancel()
    await client.close()
