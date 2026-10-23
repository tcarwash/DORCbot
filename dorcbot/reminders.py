"""Persistent storage and time handling for scheduled Discord reminders."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def parse_schedule_time(value, timezone_name):
    """Parse a local ISO date/time and reject nonexistent or ambiguous times."""
    try:
        local = datetime.fromisoformat(value)
        zone = ZoneInfo(timezone_name)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError("Use a valid ISO date/time and IANA timezone.") from exc

    if local.tzinfo is not None:
        raise ValueError("Enter local time without an offset; choose a timezone separately.")

    first = local.replace(tzinfo=zone, fold=0)
    second = local.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second.utcoffset():
        raise ValueError(
            "That local time is ambiguous or skipped by daylight saving time. "
            "Choose another time."
        )
    if first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != local:
        raise ValueError("That local time does not exist because of a daylight saving change.")
    return local, first.astimezone(timezone.utc)


class ReminderStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    local_start TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    recurrence TEXT NOT NULL CHECK (recurrence IN ('once', 'weekly')),
                    next_run_utc TEXT NOT NULL,
                    remind_before_minutes INTEGER NOT NULL DEFAULT 15,
                    status TEXT NOT NULL DEFAULT 'scheduled',
                    created_by INTEGER NOT NULL
                )"""
            )

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def create(self, guild_id, channel_id, title, local_start, timezone_name,
               recurrence, next_run_utc, created_by, remind_before_minutes=15):
        if recurrence not in ("once", "weekly"):
            raise ValueError("Repeat must be once or weekly.")
        with self._connect() as db:
            cursor = db.execute(
                """INSERT INTO reminders
                   (guild_id, channel_id, title, local_start, timezone,
                    recurrence, next_run_utc, remind_before_minutes, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (guild_id, channel_id, title, local_start.isoformat(),
                 timezone_name, recurrence, next_run_utc.isoformat(),
                 remind_before_minutes, created_by),
            )
            return cursor.lastrowid

    def list_for_guild(self, guild_id):
        with self._connect() as db:
            return db.execute(
                """SELECT * FROM reminders
                   WHERE guild_id = ? AND status = 'scheduled'
                   ORDER BY next_run_utc""",
                (guild_id,),
            ).fetchall()

    def cancel(self, guild_id, reminder_id):
        with self._connect() as db:
            cursor = db.execute(
                """UPDATE reminders SET status = 'cancelled'
                   WHERE id = ? AND guild_id = ? AND status = 'scheduled'""",
                (reminder_id, guild_id),
            )
            return cursor.rowcount == 1

    def due(self, now=None):
        now = now or datetime.now(timezone.utc)
        with self._connect() as db:
            return db.execute(
                """SELECT * FROM reminders
                   WHERE status = 'scheduled' AND next_run_utc <= ?
                   ORDER BY next_run_utc""",
                (now.isoformat(),),
            ).fetchall()

    def delivered(self, reminder):
        with self._connect() as db:
            if reminder["recurrence"] == "once":
                db.execute(
                    "UPDATE reminders SET status = 'completed' WHERE id = ?",
                    (reminder["id"],),
                )
                return

            local_start = datetime.fromisoformat(reminder["local_start"])
            next_local = local_start + timedelta(days=7)
            for _ in range(3):
                try:
                    _, next_run = parse_schedule_time(
                        next_local.isoformat(), reminder["timezone"]
                    )
                    break
                except ValueError:
                    # Skip the rare weekly occurrence that falls into a DST
                    # gap or repeated local clock hour.
                    next_local += timedelta(days=7)
            next_run -= timedelta(minutes=reminder["remind_before_minutes"])
            db.execute(
                """UPDATE reminders SET local_start = ?, next_run_utc = ?
                   WHERE id = ?""",
                (next_local.isoformat(), next_run.isoformat(), reminder["id"]),
            )

    def failed(self, reminder_id):
        with self._connect() as db:
            db.execute(
                "UPDATE reminders SET status = 'failed' WHERE id = ?",
                (reminder_id,),
            )
