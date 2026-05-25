import os
import sqlite3
import time

from .config import CONFIG_DIR

DB_PATH = os.path.join(CONFIG_DIR, "history.db")
CLEANUP_THRESHOLD = 86400

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    translation TEXT NOT NULL,
    created_at REAL NOT NULL,
    last_used REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_source ON history(source);
CREATE INDEX IF NOT EXISTS idx_last_used ON history(last_used);
"""


class HistoryDB:
    def __init__(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def lookup(self, source_text):
        self._cleanup()
        cur = self.conn.execute(
            "SELECT id, translation FROM history WHERE source = ? LIMIT 1",
            (source_text,),
        )
        row = cur.fetchone()
        if row:
            self.conn.execute(
                "UPDATE history SET last_used = ? WHERE id = ?",
                (time.time(), row[0]),
            )
            self.conn.commit()
            return row[1]
        return None

    def save(self, source_text, translation):
        cur = self.conn.execute(
            "SELECT id FROM history WHERE source = ? LIMIT 1",
            (source_text,),
        )
        now = time.time()
        row = cur.fetchone()
        if row:
            self.conn.execute(
                "UPDATE history SET translation = ?, last_used = ? WHERE id = ?",
                (translation, now, row[0]),
            )
        else:
            self.conn.execute(
                "INSERT INTO history (source, translation, created_at, last_used) VALUES (?, ?, ?, ?)",
                (source_text, translation, now, now),
            )
        self.conn.commit()
        self._cleanup()

    def _cleanup(self):
        cutoff = time.time() - CLEANUP_THRESHOLD
        self.conn.execute("DELETE FROM history WHERE last_used < ?", (cutoff,))
        self.conn.commit()

    def close(self):
        self.conn.close()
