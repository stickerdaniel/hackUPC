# B5 — Run/Scenario Identity

## TL;DR

Use a human-readable slug as `run_id` (`{location}-{YYYY-MM-DD}-{HHmm}`,
e.g. `barcelona-2026-04-25-0900`). Add a `scenarios` table for metadata and
`config_json` / `seed` columns. Runs are immutable once written. Phase 3 lists
and compares runs by querying `scenarios`.

---

## Background

The demo centrepiece is "same printer, different climates" — Barcelona (mild,
humid) vs Phoenix (hot, dry) runs displayed side-by-side from one SQLite
historian. The run identity scheme must satisfy four needs simultaneously:

1. Unambiguous DB key for every telemetry row.
2. Legible enough for a chatbot to surface and for the operator to say aloud.
3. Reproducible: re-running with the same seed and config must produce
   identical telemetry.
4. Comparable: `compare_runs(run_a, run_b)` must resolve both arguments
   without guessing.

---

## Options Considered

| Option | Pros | Cons |
|---|---|---|
| UUID v4 | Globally unique, no collisions | Opaque; chatbot must look up a name anyway; bad for live demo narration |
| Auto-increment integer | Simple | Meaningless without a name column; ordering fragile across imports |
| Human-readable slug (chosen) | Self-documenting; safe to say on stage; works as both PK and display name | Requires a uniqueness convention; slight collision risk if two runs start in same minute |
| Slug + short UUID suffix | Belt-and-braces uniqueness | More typing, uglier in chatbot output |

A plain slug is sufficient for a hackathon with O(10) runs. A four-character
random suffix (`barcelona-2026-04-25-0900-a3f2`) can be added if needed, but
is not the default recommendation.

---

## Recommendation

### run_id format

```
{location}-{YYYY-MM-DD}-{HHmm}
```

Generated in Python:

```python
from datetime import datetime, timezone

def make_run_id(location: str, dt: datetime | None = None) -> str:
    """Generate a human-readable, URL-safe run identifier.

    Args:
        location: Scenario location slug, e.g. 'barcelona' or 'phoenix'.
        dt: Datetime of run start (UTC). Defaults to now.

    Returns:
        str: e.g. 'barcelona-2026-04-25-0900'
    """
    dt = dt or datetime.now(timezone.utc)
    slug = location.lower().replace(" ", "-")
    return f"{slug}-{dt.strftime('%Y-%m-%d-%H%M')}"
```

### Table additions

Keep telemetry rows denormalised — `run_id` is a plain `TEXT` foreign key
stored directly in the `telemetry` table. A separate `scenarios` table holds
all metadata so Phase 3 can list and compare runs without scanning telemetry:

```sql
CREATE TABLE scenarios (
    run_id        TEXT PRIMARY KEY,
    scenario_name TEXT NOT NULL,       -- "Barcelona Mild Climate"
    location      TEXT NOT NULL,       -- "barcelona"
    started_at    TEXT NOT NULL,       -- ISO-8601 UTC
    seed          INTEGER NOT NULL,    -- for full reproducibility
    config_json   TEXT NOT NULL        -- JSON blob: temp_profile, humidity, dt, etc.
);
```

Telemetry table gains one column: `run_id TEXT NOT NULL REFERENCES scenarios`.

### Immutability

Runs are append-only once the first tick is written. The simulation loop
inserts into `scenarios` before the first tick and never updates that row.
Phase 3 must never mutate historian rows.

### Phase 3 run listing and compare_runs

```python
def list_runs(db) -> list[dict]:
    return db.execute(
        "SELECT run_id, scenario_name, location, started_at FROM scenarios ORDER BY started_at DESC"
    ).fetchall()

def compare_runs(db, run_a: str, run_b: str) -> dict:
    """Accepts run_id slugs or prefix matches."""
    rows = db.execute(
        "SELECT * FROM scenarios WHERE run_id LIKE ? OR run_id LIKE ?",
        (f"{run_a}%", f"{run_b}%"),
    ).fetchall()
    # join with telemetry summary stats per run, return side-by-side dict
    ...
```

Prefix matching lets the chatbot resolve `"barcelona"` to the most recent
Barcelona run without requiring the full slug.

---

## Open Questions

- Should `location` be a controlled enum (`barcelona | phoenix | custom`) or
  a free string? Enum is safer for demo but a free string lets us add new
  cities without a schema change.
- If we run stochastic simulations (Phase 2 Pattern C), do we log the RNG
  state at each tick, or is storing the initial `seed` enough? Initial seed
  is sufficient if the simulation is fully sequential with no external I/O.
- Do we need a `status` column (`running | complete | failed`) in `scenarios`
  so Phase 3 can skip incomplete runs? Useful for streaming demos.

---

## References

- TRACK-CONTEXT.md §3.3 — Engine must be deterministic; stochasticity seeded.
- TRACK-CONTEXT.md §4 Phase 2 — "Persistence to CSV, JSON, or SQLite — every
  tick, every component, every driver, timestamp, run ID."
- TRACK-CONTEXT.md §4 Phase 2 Advanced — "What-if scenarios — same printer,
  different climates / duty cycles."
- TRACK-CONTEXT.md §4 Phase 3 — "Every response must be traceable to a
  specific timestamp / component / run ID."
