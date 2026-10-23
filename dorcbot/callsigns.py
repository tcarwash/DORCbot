"""Persistent per-server callsign registrations."""

import sqlite3
from pathlib import Path


class CallsignStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS callsigns (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    callsign TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, user_id)
                )"""
            )

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def set(self, guild_id, user_id, callsign):
        with self._connect() as db:
            db.execute(
                """INSERT INTO callsigns (guild_id, user_id, callsign)
                   VALUES (?, ?, ?)
                   ON CONFLICT(guild_id, user_id) DO UPDATE SET
                       callsign = excluded.callsign,
                       updated_at = CURRENT_TIMESTAMP""",
                (guild_id, user_id, callsign),
            )

    def get(self, guild_id, user_id):
        with self._connect() as db:
            row = db.execute(
                "SELECT callsign FROM callsigns WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            return row["callsign"] if row else None

    def remove(self, guild_id, user_id):
        with self._connect() as db:
            cursor = db.execute(
                "DELETE FROM callsigns WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            return cursor.rowcount == 1

    def list_for_guild(self, guild_id):
        with self._connect() as db:
            rows = db.execute(
                "SELECT user_id, callsign FROM callsigns WHERE guild_id = ?",
                (guild_id,),
            ).fetchall()
            return {row["user_id"]: row["callsign"] for row in rows}
