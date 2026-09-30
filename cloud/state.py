import sqlite3
import threading
import time

from common.config import STORAGE_DIR

DB_PATH = STORAGE_DIR / "cloud" / "cloud.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS versions (
    doc_id     TEXT PRIMARY KEY,
    version    INTEGER NOT NULL,
    updated_by TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS received (
    note_id     TEXT PRIMARY KEY,
    device      TEXT NOT NULL,
    outcome     TEXT NOT NULL,
    received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conflicts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id         TEXT NOT NULL,
    note_id        TEXT NOT NULL,
    device         TEXT NOT NULL,
    base_version   INTEGER,
    server_version INTEGER,
    proposed_text  TEXT NOT NULL,
    status         TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
"""


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


class CloudState:
    def __init__(self, path=DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.lock = threading.Lock()

    def reset(self, records):
        with self.conn:
            for table in ("versions", "received", "conflicts"):
                self.conn.execute(f"DELETE FROM {table}")
            self.conn.executemany(
                "INSERT INTO versions VALUES (?, ?, ?, ?)",
                [(r["doc_id"], r["version"], "seed", _now()) for r in records],
            )

    def version(self, doc_id):
        row = self.conn.execute("SELECT version FROM versions WHERE doc_id = ?", (doc_id,)).fetchone()
        return row["version"] if row else None

    def set_version(self, doc_id, version, device):
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO versions VALUES (?, ?, ?, ?)", (doc_id, version, device, _now())
            )

    def was_received(self, note_id):
        return self.conn.execute("SELECT 1 FROM received WHERE note_id = ?", (note_id,)).fetchone() is not None

    def mark_received(self, note_id, device, outcome):
        with self.conn:
            self.conn.execute("INSERT INTO received VALUES (?, ?, ?, ?)", (note_id, device, outcome, _now()))

    def add_conflict(self, doc_id, note_id, device, base_version, server_version, text):
        with self.conn:
            self.conn.execute(
                "INSERT INTO conflicts (doc_id, note_id, device, base_version, server_version, "
                "proposed_text, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'open', ?)",
                (doc_id, note_id, device, base_version, server_version, text, _now()),
            )

    def conflicts(self, status="open"):
        rows = self.conn.execute("SELECT * FROM conflicts WHERE status = ? ORDER BY id", (status,)).fetchall()
        return [dict(r) for r in rows]
    def get_conflict(self, conflict_id):
        row = self.conn.execute("SELECT * FROM conflicts WHERE id = ?", (conflict_id,)).fetchone()
        return dict(row) if row else None

    def set_conflict_status(self, conflict_id, status):
        with self.conn:
            self.conn.execute("UPDATE conflicts SET status = ? WHERE id = ?", (status, conflict_id))