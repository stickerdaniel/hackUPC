"""SQLite connection bootstrap.

Plan §Historian: WAL mode, idempotent schema bootstrap. We also enable
foreign keys (a no-op today, useful when a future schema migration adds
one) and pick `synchronous = NORMAL` to keep batch writes under control
without giving up durability across program crashes.
"""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

_SCHEMA_FILENAME = "schema.sql"


def _load_schema() -> str:
    return (
        resources.files("copilot_sim.historian")
        .joinpath(_SCHEMA_FILENAME)
        .read_text(encoding="utf-8")
    )


def open_db(path: str | Path) -> sqlite3.Connection:
    """Open (or create) the historian DB and bootstrap the schema."""
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_load_schema())
    return conn
