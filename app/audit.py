import sqlite3
import datetime
import json
import os

DB_PATH = os.environ.get("AUDIT_DB", "audit.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event TEXT NOT NULL,
            actor TEXT,
            details TEXT
        )
    ''')
    conn.commit()
    conn.close()

def log_audit(event: str, actor: str = "system", details: dict = None):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    details_str = json.dumps(details) if details else ""
    c.execute(
        "INSERT INTO audit_log (timestamp, event, actor, details) VALUES (?,?,?,?)",
        (datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), event, actor, details_str)
    )
    conn.commit()
    conn.close()


def read_log(limit: int = 50):
    """Newest entries first, as dicts."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT timestamp, event, actor, details FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [{"time": t, "event": e, "actor": a, "details": json.loads(d) if d else {}}
            for t, e, a, d in rows]
