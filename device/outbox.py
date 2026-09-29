import json
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
    note_id      TEXT PRIMARY KEY,
    payload      TEXT NOT NULL,
    action       TEXT NOT NULL,
    reason       TEXT NOT NULL,
    priority     INTEGER NOT NULL,
    size_bytes   INTEGER NOT NULL,
    base_version INTEGER,
    status       TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activity (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     TEXT NOT NULL,
    event  TEXT NOT NULL,
    detail TEXT NOT NULL
);
"""

INITIAL_STATUS = {"sync": "pending", "keep_local": "kept_local", "review": "needs_review"}


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


class Outbox:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def add(self, record, decision, base_version=None):
        payload = json.dumps(record)
        now = _now()
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO outbox VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (record["note_id"], payload, decision.action, decision.reason, decision.priority,
                 len(payload.encode("utf-8")), base_version,
                 INITIAL_STATUS[decision.action], now, now),
            )
        self.log("decision", f"{record['note_id']} -> {decision.action}: {decision.reason}")

    def items(self, status=None):
        sql, params = "SELECT * FROM outbox", ()
        if status:
            sql, params = sql + " WHERE status = ?", (status,)
        rows = self.conn.execute(sql + " ORDER BY priority DESC, created_at", params).fetchall()
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    def set_status(self, note_id, status):
        with self.conn:
            self.conn.execute(
                "UPDATE outbox SET status = ?, updated_at = ? WHERE note_id = ?",
                (status, _now(), note_id),
            )

    def log(self, event, detail):
        with self.conn:
            self.conn.execute(
                "INSERT INTO activity (ts, event, detail) VALUES (?, ?, ?)", (_now(), event, detail)
            )

    def activity(self, limit=50):
        rows = self.conn.execute(
            "SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()