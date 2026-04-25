# B4 — Historian Schema

**TL;DR:** Use SQLite (stdlib `sqlite3`, no extra deps). One telemetry table in long format,
indexed on `(run_id, ts)` and `(run_id, component)`. Phase 3 tool calls map directly to
SQL queries; no ORM needed.

---

## Background

Phase 2 writes one row per component per tick (e.g. 3 components × N ticks = 3N rows).
Phase 3 chatbot tools (`query_health`, `get_failure_events`, `compare_runs`,
`current_status`, `recommend_action`) need sub-second reads on a few thousand to a few
hundred-thousand rows — well within SQLite's sweet spot for a hackathon demo.

---

## Options Considered

### SQLite
- `sqlite3` is Python stdlib — zero extra dependencies.
- File-based; the whole historian is a single `.db` file that demos easily.
- Supports arbitrary SQL: window functions, GROUP BY, subqueries, JOIN — exactly what the
  Phase 3 tool layer needs.
- `better-sqlite3` available on npm if a Node layer is ever needed.

### Parquet / CSV
- pandas + pyarrow needed for Parquet (`pip install pyarrow`); CSV needs no deps.
- Column-oriented Parquet is fast for analytics but requires loading into a DataFrame
  before filtering — awkward for the chatbot tool calls which want ad-hoc row fetches.
- CSV is append-only and has no indexing; querying "latest health per component for run X"
  means a full scan every time.
- Neither format supports the agentic ReAct loop pattern cleanly without an in-process
  query engine (DuckDB, polars) — an extra moving part.

**Verdict:** SQLite wins on every axis that matters here: queryability, zero deps,
file portability, and direct SQL tool calls.

---

## Recommendation

### Format: SQLite

Single file `historian.db`, one table. Long format (one row per component per tick) keeps
the schema stable when new components are added and makes aggregation queries trivial.

### Full DDL

```sql
CREATE TABLE IF NOT EXISTS telemetry (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           TEXT    NOT NULL,
    ts               REAL    NOT NULL,   -- Unix epoch seconds (float for sub-second)
    component        TEXT    NOT NULL,   -- e.g. 'recoater_blade', 'nozzle_plate', 'heating_element'
    health           REAL    NOT NULL,   -- 0.0 (dead) to 1.0 (new)
    status           TEXT    NOT NULL,   -- FUNCTIONAL | DEGRADED | CRITICAL | FAILED
    metric_name      TEXT    NOT NULL,   -- component-specific quantity name
    metric_value     REAL    NOT NULL,   -- value of that quantity
    driver_temp      REAL    NOT NULL,   -- ambient temperature stress (°C deviation)
    driver_humidity  REAL    NOT NULL,   -- humidity / contamination coefficient
    driver_load      REAL    NOT NULL,   -- operational load (print hours or cycles)
    driver_maint     REAL    NOT NULL    -- maintenance level coefficient
);

CREATE INDEX IF NOT EXISTS idx_run_ts
    ON telemetry (run_id, ts);

CREATE INDEX IF NOT EXISTS idx_run_component
    ON telemetry (run_id, component);

CREATE INDEX IF NOT EXISTS idx_run_status
    ON telemetry (run_id, status);
```

**Why long format?** Each component can expose a different physical metric
(`blade_thickness_mm`, `nozzle_clog_pct`, `heater_resistance_ohm`). Storing
`(metric_name, metric_value)` as a pair means the schema never changes when components
are added or swapped. Wide format would require nullable columns or schema migrations.

**Multi-component per tick:** each component gets its own row at the same `ts`. A tick
with 3 components writes 3 rows sharing the same `run_id` and `ts`.

### Sample Queries the Chatbot Tools Will Use

**`current_status` — latest health per component for run X:**

```sql
SELECT component, health, status, metric_name, metric_value, ts
FROM telemetry
WHERE run_id = :run_id
  AND ts = (
      SELECT MAX(ts) FROM telemetry WHERE run_id = :run_id
  );
```

**`get_failure_events` — ticks where any component entered CRITICAL or FAILED:**

```sql
SELECT ts, component, health, status, metric_name, metric_value
FROM telemetry
WHERE run_id = :run_id
  AND status IN ('CRITICAL', 'FAILED')
ORDER BY ts ASC;
```

**`compare_runs` — average health per component across two runs:**

```sql
SELECT component, run_id, AVG(health) AS avg_health, MIN(health) AS min_health
FROM telemetry
WHERE run_id IN (:run_a, :run_b)
GROUP BY component, run_id
ORDER BY component, run_id;
```

---

## Open Questions

1. **dt granularity:** if dt = 1 min and runs are 10 h long, that is 600 ticks × 3
   components = 1 800 rows per run — very small. Even at 1-s dt and 24 h that is only
   ~260 k rows; SQLite handles this trivially.
2. **Multiple metrics per component per tick:** current schema assumes one metric row per
   component per tick. If a component needs two metrics simultaneously (e.g. nozzle: both
   `clog_pct` and `temp_stress`), either (a) write two rows with different `metric_name`
   values, or (b) add a `metric_name2 / metric_value2` pair. Option (a) keeps the schema
   clean at the cost of doubling rows; decide in Phase 1 implementation.
3. **Run metadata:** a separate `runs` table (run_id, start_ts, scenario_name, notes) may
   be useful for `compare_runs` but is not required for the minimum bar.

---

## References

- Python `sqlite3` stdlib: https://docs.python.org/3/library/sqlite3.html
- `better-sqlite3` npm: https://github.com/WiseLibs/better-sqlite3
- pandas Parquet I/O (requires `pyarrow` or `fastparquet`):
  https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_parquet.html
- SQLite limits and performance characteristics:
  https://www.sqlite.org/limits.html
