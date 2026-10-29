import sqlite3
import datetime
import json

DB_PATH = "audit.db"

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
        (datetime.datetime.utcnow().isoformat(), event, actor, details_str)
    )
    conn.commit()
    conn.close()
