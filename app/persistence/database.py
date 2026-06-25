"""Local SQLite persistence layer.

SQLite file lives at ``.local/work-agents.sqlite3`` relative to the
project directory. Tables are created automatically on first use.
"""

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

# Default location inside the project directory.
DB_PATH = Path(".local/work-agents.sqlite3")


async def get_db() -> aiosqlite.Connection:
    """Return an async SQLite connection with WAL mode and foreign keys."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await _migrate(db)
    return db


async def _migrate(db: aiosqlite.Connection) -> None:
    """Idempotent schema migration."""
    await db.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id         TEXT PRIMARY KEY,
            workflow_id    TEXT NOT NULL DEFAULT '',
            conversation_id TEXT NOT NULL DEFAULT '',
            status         TEXT NOT NULL DEFAULT 'pending',
            arguments      TEXT NOT NULL DEFAULT '{}',
            result         TEXT,
            error          TEXT,
            created_at     TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS run_events (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id        TEXT NOT NULL REFERENCES runs(run_id),
            sequence      INTEGER NOT NULL,
            event_type    TEXT NOT NULL,
            data          TEXT NOT NULL DEFAULT '{}',
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_run_events_run_id
            ON run_events(run_id);

        CREATE INDEX IF NOT EXISTS idx_run_events_sequence
            ON run_events(run_id, sequence);

        CREATE TABLE IF NOT EXISTS workflow_definitions (
            id            TEXT PRIMARY KEY,
            name          TEXT NOT NULL DEFAULT '',
            description   TEXT NOT NULL DEFAULT '',
            definition    TEXT NOT NULL DEFAULT '{}',
            enabled       INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    await db.commit()


async def close_db(db: aiosqlite.Connection) -> None:
    await db.close()
