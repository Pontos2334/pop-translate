import hashlib
import os
import sqlite3
import threading
import time
from typing import Optional

from .config import CONFIG_DIR

DB_PATH = os.path.join(CONFIG_DIR, "history.db")
CLEANUP_THRESHOLD = 86400

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_key TEXT,
    source TEXT NOT NULL,
    translation TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    prompt_version TEXT NOT NULL DEFAULT 'legacy',
    created_at REAL NOT NULL,
    last_used REAL NOT NULL
);
"""

_INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_cache_key ON history(cache_key);
CREATE INDEX IF NOT EXISTS idx_source ON history(source);
CREATE INDEX IF NOT EXISTS idx_last_used ON history(last_used);
"""


class HistoryDB:
    def __init__(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)
        self._ensure_columns()
        self.conn.executescript(_INDEXES)
        self.conn.commit()

    def lookup(self, source_text: str, model: str = "", prompt_version: str = "legacy") -> Optional[str]:
        cache_key = self._cache_key(source_text, model, prompt_version)
        with self.lock:
            self._cleanup()
            cur = self.conn.execute(
                "SELECT id, translation FROM history WHERE cache_key = ? LIMIT 1",
                (cache_key,),
            )
            row = cur.fetchone()
            if not row:
                return None
            self.conn.execute(
                "UPDATE history SET last_used = ? WHERE id = ?",
                (time.time(), row[0]),
            )
            self.conn.commit()
            return row[1]

    def save(
        self,
        source_text: str,
        translation: str,
        model: str = "",
        prompt_version: str = "legacy",
    ) -> None:
        cache_key = self._cache_key(source_text, model, prompt_version)
        with self.lock:
            cur = self.conn.execute(
                "SELECT id FROM history WHERE cache_key = ? LIMIT 1",
                (cache_key,),
            )
            now = time.time()
            row = cur.fetchone()
            if row:
                self.conn.execute(
                    "UPDATE history SET source = ?, translation = ?, model = ?, prompt_version = ?, last_used = ? WHERE id = ?",
                    (source_text, translation, model or "", prompt_version, now, row[0]),
                )
            else:
                self.conn.execute(
                    """
                    INSERT INTO history
                        (cache_key, source, translation, model, prompt_version, created_at, last_used)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (cache_key, source_text, translation, model or "", prompt_version, now, now),
                )
            self.conn.commit()
            self._cleanup()

    def _cleanup(self) -> None:
        cutoff = time.time() - CLEANUP_THRESHOLD
        self.conn.execute("DELETE FROM history WHERE last_used < ?", (cutoff,))
        self.conn.commit()

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    def _ensure_columns(self) -> None:
        columns = {
            row[1] for row in self.conn.execute("PRAGMA table_info(history)").fetchall()
        }
        migrations = {
            "cache_key": "ALTER TABLE history ADD COLUMN cache_key TEXT",
            "model": "ALTER TABLE history ADD COLUMN model TEXT NOT NULL DEFAULT ''",
            "prompt_version": "ALTER TABLE history ADD COLUMN prompt_version TEXT NOT NULL DEFAULT 'legacy'",
        }
        for column, sql in migrations.items():
            if column not in columns:
                self.conn.execute(sql)

    def _cache_key(self, source_text: str, model: str, prompt_version: str) -> str:
        raw = "\0".join((prompt_version or "legacy", model or "", source_text or ""))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
