"""Simulated SMS: messages are stored and shown on /sms. Nothing is sent."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "sms.db"


def _conn():
    DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.execute("CREATE TABLE IF NOT EXISTS sms (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                 " time TEXT NOT NULL, recipient TEXT NOT NULL, text TEXT NOT NULL)")
    return conn


def store(recipient: str, text: str) -> None:
    with _conn() as c:
        c.execute("INSERT INTO sms (time, recipient, text) VALUES (?, ?, ?)",
                  (datetime.now(timezone.utc).strftime("%H:%M:%S"), recipient, text))


def all_messages() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT time, recipient, text FROM sms ORDER BY id DESC").fetchall()
    return [{"time": t, "recipient": r, "text": x} for t, r, x in rows]
