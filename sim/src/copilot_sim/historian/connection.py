"""SQLite connection bootstrap.

Plan §Historian: WAL mode, idempotent schema bootstrap. We also enable
foreign keys (a no-op today, useful when a future schema migration adds
one) and pick `synchronous = NORMAL` to keep batch writes under control
without giving up durability across program crashes.

`open_db` also runs a post-bootstrap sanity check for the
`environment_json` column on `drivers` — `CREATE TABLE IF NOT EXISTS`
is a no-op against an existing pre-event-overlay DB, so without this
check the next write would crash mid-run with a cryptic SQLite error.
We surface a clear `IncompatibleHistorianError` instead. Hackathon
mode: we don't ship `ALTER TABLE` migrations.
"""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

_SCHEMA_FILENAME = "schema.sql"


class IncompatibleHistorianError(RuntimeError):
    """Raised when an existing DB is from a schema version that lacks the
    columns we now require. Action is always "delete the file and rerun".
    """


def _load_schema() -> str:
    return (
        resources.files("copilot_sim.historian")
        .joinpath(_SCHEMA_FILENAME)
        .read_text(encoding="utf-8")
    )


def _verify_event_overlay_schema(conn: sqlite3.Connection, db_path: Path) -> None:
    """Confirm the event-overlay schema additions made it onto the DB.

    `CREATE TABLE IF NOT EXISTS` keeps the OLD `drivers` definition if a
    table by that name already exists — so a pre-event DB will never gain
    the `environment_json` column or the `environmental_events` table.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(drivers)").fetchall()}
    if "environment_json" not in cols:
        raise IncompatibleHistorianError(
            f"Historian schema at {db_path} predates the event-overlay change. "
            f"Delete {db_path} and rerun. "
            "(Hackathon-mode: we don't ship ALTER TABLE migrations.)"
        )
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "environmental_events" not in tables:
        raise IncompatibleHistorianError(
            f"Historian at {db_path} is missing `environmental_events`. Delete {db_path} and rerun."
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
    _verify_event_overlay_schema(conn, db_path)
    return conn
