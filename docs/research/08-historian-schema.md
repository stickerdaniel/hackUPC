# 08 — Historian Schema, Storage Choice, and Run Identity

> Phase 2 persistence layer: the single SQLite file that Phase 2 writes every tick and Phase 3 (Next.js + AI SDK) queries via tool-calling. Locks storage, schema, indexes, and `run_id` format.

## TL;DR

- **Storage: SQLite, single file at `data/historian.sqlite`.** Writable from Python (Phase 1/2 sim, `sqlite3` stdlib), readable from Node (Phase 3, `better-sqlite3`, synchronous, zero-config, ships precompiled binaries). One file we can check into git for demos, copy into a Vercel deploy, or hand to a judge.
- **Schema: long form, one row per `(run_id, ts, component, metric_name)`.** Component-level fields (`health`, `status`) live on a separate `component_state` row; environmental drivers live on a separate `drivers` table keyed by `(run_id, ts)`. No wide row, no NULL-padding.
- **Indexes:** primary keys cover the hot lookup paths; one extra index on `component_state(run_id, component, ts)` and on `metrics(run_id, component, metric_name, ts)`.
- **`run_id` format (locked):** `{scenario}-{profile}-{YYYYMMDD}-{seq}` — e.g. `barcelona-baseline-20260425-1`, `phoenix-aggressive-20260425-2`. ASCII, lowercase, hyphen-only, sortable, greppable.
- **Events table** for maintenance and failure transitions: `events(run_id, ts, component, kind, payload_json)`.
- **Volume:** ~26k metric rows + ~13k component-state rows + ~4.4k driver rows per run. SQLite eats this for breakfast; whole demo fits in a few MB.

## Background

Phase 2 must persist **every tick, every component, every driver** with timestamp + run id (TRACK-CONTEXT §3.2, §4 Phase 2 minimum bar). Phase 3 must query that historian via tool calls and cite specific rows (TRACK-CONTEXT §4 Phase 3 grounding protocol).

The candidate "wide row" `(run_id, ts, component, health, status, metric_name, metric_value, driver_temp, driver_humidity, driver_load, driver_maint)` has two problems:

1. **Multi-metric components.** Nozzle has both `clog_pct` and `fatigue_damage`; blade has `thickness_mm` and `wear_depth`. A single `metric_name` / `metric_value` pair forces either one row per metric (which then duplicates `health` and `status` across rows for the same `(run_id, ts, component)`) or smashing all metrics into one JSON blob (unqueryable from SQL tools).
2. **Driver duplication.** Drivers are per-tick, not per-component. Putting them on the component row repeats each driver value 3× per tick.

Splitting along these natural boundaries removes the duplication and makes every Phase 3 tool call a one-line SQL.

## Decision

### Storage

SQLite, file path `data/historian.sqlite`. WAL mode on. Read-heavy on the Phase 3 side, single-writer on Phase 2 side — exactly SQLite's sweet spot.

Rejected:
- **CSV + JSON** — no indexes, Phase 3 has to load the whole run to answer "what was the nozzle health at 14:30?". Tool calls become slow and the LLM context fills with raw rows.
- **Parquet** — great for analytics, but reading from Node needs `parquetjs` or DuckDB-WASM; both add complexity for no win at this scale.

### Schema (full DDL)

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- One row per simulation run / scenario.
CREATE TABLE runs (
  run_id      TEXT PRIMARY KEY,
  scenario    TEXT NOT NULL,        -- e.g. 'barcelona', 'phoenix'
  profile     TEXT NOT NULL,        -- e.g. 'baseline', 'aggressive', 'chaos'
  started_at  TEXT NOT NULL,        -- ISO-8601, UTC
  dt_seconds  INTEGER NOT NULL,     -- tick size
  seed        INTEGER,              -- RNG seed for determinism
  notes       TEXT
);

-- Per-tick raw drivers + the system-level print outcome (one row per tick, per run).
-- Drivers are the brief's 4-driver schema, matching `domain.drivers.Drivers`.
CREATE TABLE drivers (
  run_id                  TEXT NOT NULL,
  ts                      TEXT NOT NULL,        -- ISO-8601
  temperature_stress      REAL NOT NULL,        -- 0..1, deviation from optimal
  humidity_contamination  REAL NOT NULL,        -- 0..1, unified per the brief (NOT split)
  operational_load        REAL NOT NULL,        -- 0..1
  maintenance_level       REAL NOT NULL,        -- 0..1
  -- §3.4 system-level observable, top-level on PrinterState
  print_outcome           TEXT NOT NULL,        -- 'OK' | 'QUALITY_DEGRADED' | 'HALTED'
  -- Coupling factors computed once per tick by build_coupling_context, persisted
  -- so the co-pilot can attribute degradation upstream without re-running the engine.
  coupling_factors_json   TEXT NOT NULL,        -- {"powder_spread_quality": 0.83, "sensor_bias_c": -1.2, ...}
  PRIMARY KEY (run_id, ts),
  FOREIGN KEY (run_id) REFERENCES runs(run_id)
) WITHOUT ROWID;

-- Per-tick, per-component TRUE health + status (engine-internal ground truth).
-- Six components: blade, rail, nozzle, cleaning, heater, sensor.
CREATE TABLE component_state (
  run_id     TEXT NOT NULL,
  ts         TEXT NOT NULL,
  component  TEXT NOT NULL,         -- 'blade' | 'rail' | 'nozzle' | 'cleaning' | 'heater' | 'sensor'
  health     REAL NOT NULL,         -- 0..1, true health
  status     TEXT NOT NULL,         -- FUNCTIONAL | DEGRADED | CRITICAL | FAILED  (NEVER 'UNKNOWN' on true state)
  age_ticks  INTEGER NOT NULL,
  PRIMARY KEY (run_id, ts, component),
  FOREIGN KEY (run_id, ts) REFERENCES drivers(run_id, ts)
) WITHOUT ROWID;

CREATE INDEX idx_state_component_ts
  ON component_state(run_id, component, ts);

-- Per-tick, per-component, per-metric TRUE physical quantities.
CREATE TABLE metrics (
  run_id       TEXT NOT NULL,
  ts           TEXT NOT NULL,
  component    TEXT NOT NULL,
  metric_name  TEXT NOT NULL,       -- 'clog_pct' | 'fatigue_damage' | 'thickness_mm' | 'alignment_error_um' | 'cleaning_efficiency' | 'drift_frac' | 'bias_c' | 'noise_sigma_c' | ...
  metric_value REAL NOT NULL,
  PRIMARY KEY (run_id, ts, component, metric_name),
  FOREIGN KEY (run_id, ts, component) REFERENCES component_state(run_id, ts, component)
) WITHOUT ROWID;

CREATE INDEX idx_metrics_lookup
  ON metrics(run_id, component, metric_name, ts);

-- §3.4 OBSERVED layer — what a sensor or print-quality signal actually exposes.
-- Mirrors component_state but values can be NULL (sensor absent / dropped out)
-- and observed_status can be 'UNKNOWN'. The maintenance policy and co-pilot
-- consume THIS layer, not the true layer above.
CREATE TABLE observed_component_state (
  run_id            TEXT NOT NULL,
  ts                TEXT NOT NULL,
  component         TEXT NOT NULL,
  observed_health   REAL,                 -- nullable when not derivable
  observed_status   TEXT NOT NULL,        -- FUNCTIONAL | DEGRADED | CRITICAL | FAILED | UNKNOWN
  sensor_note       TEXT NOT NULL,        -- 'ok' | 'noisy' | 'drift' | 'stuck' | 'absent' | mixed-tag
  PRIMARY KEY (run_id, ts, component),
  FOREIGN KEY (run_id, ts, component) REFERENCES component_state(run_id, ts, component)
) WITHOUT ROWID;

-- Per-metric observed values + per-metric sensor health.
CREATE TABLE observed_metrics (
  run_id                    TEXT NOT NULL,
  ts                        TEXT NOT NULL,
  component                 TEXT NOT NULL,
  metric_name               TEXT NOT NULL,
  observed_value            REAL,         -- NULL when sensor absent / stuck-at-None
  sensor_health_for_metric  REAL,         -- 0..1, NULL when no sensor on this metric
  PRIMARY KEY (run_id, ts, component, metric_name),
  FOREIGN KEY (run_id, ts, component, metric_name) REFERENCES metrics(run_id, ts, component, metric_name)
) WITHOUT ROWID;

-- Sparse events log: operator actions (TROUBLESHOOT/FIX/REPLACE), status transitions, chaos injections.
CREATE TABLE events (
  run_id       TEXT NOT NULL,
  ts           TEXT NOT NULL,
  component    TEXT,                -- nullable: machine-wide events allowed
  kind         TEXT NOT NULL,       -- OperatorEventKind ∈ {'TROUBLESHOOT', 'FIX', 'REPLACE'} | 'STATUS_CHANGE' | 'CHAOS' | 'FAILURE'
  payload_json TEXT NOT NULL,       -- arbitrary structured detail (rationale, magnitudes, etc.)
  PRIMARY KEY (run_id, ts, kind, component)
);

CREATE INDEX idx_events_kind ON events(run_id, kind, ts);
```

**§3.4 observability split — why two state tables, not one.** The brief (§3.4) requires a clean separation between *true state* (engine-internal ground truth) and *observed state* (what the operator/policy/co-pilot perceives via sensors and print outcomes). The maintenance policy and the future co-pilot must consume `observed_component_state` and `observed_metrics`; only the engine and the deck-side analytics may read `component_state` and `metrics`. This is the structural condition for ever distinguishing *component fault* from *sensor fault* — without it, an LLM has nothing to compare. Mirrors `domain.state.PrinterState` vs `ObservedPrinterState`.

### `run_id` format — locked

```
{scenario}-{profile}-{YYYYMMDD}-{seq}
```

Rules:

- `scenario` ∈ `{barcelona, phoenix, reykjavik, ...}` — geography or named profile, lowercase.
- `profile` ∈ `{baseline, aggressive, chaos, maintained, ...}` — duty / driver intensity.
- `YYYYMMDD` — local date the run was kicked off.
- `seq` — integer starting at 1, increments per same-day same-(scenario, profile) re-run.

Examples: `barcelona-baseline-20260425-1`, `phoenix-aggressive-20260425-2`, `reykjavik-chaos-20260426-1`.

ASCII-only, hyphen-separated, lexicographically sortable by date, trivially greppable in CLI demos.

## Why this fits our case

- **One row per `(run, ts, component, metric)`** lets Phase 3 answer "show me nozzle clog over the last hour" with one indexed `WHERE run_id=? AND component='nozzle_plate' AND metric_name='clog_pct' AND ts BETWEEN ? AND ?` — covered exactly by `idx_metrics_lookup`.
- **Drivers separated** removes 3× duplication and makes "what were the drivers when the nozzle hit CRITICAL?" a single join on `(run_id, ts)`.
- **Status on `component_state`, not on metric rows** means status transitions are one-row-per-tick; we don't have to deduplicate when scanning.
- **`WITHOUT ROWID`** on the heavy time-series tables: SQLite stores rows directly in the primary-key B-tree, which is the index Phase 3 actually queries. Saves space and a level of indirection.
- **Events table is sparse** — failures and maintenance happen rarely, so it stays small and fast to scan even with `LIKE '%'` style debugging queries.
- **`better-sqlite3` is synchronous** — perfect for AI SDK tool calls: the tool function body is `db.prepare(sql).all(params)` with no `await`, no connection pool, no surprises in serverless edge runtimes.
- **Volume sanity check (6 components).** 4400 ticks × 6 components × ~2 metrics ≈ 53k metric rows; ×2 again for the observed mirror (~53k more); + 26k state rows (×2 for observed); + 4.4k driver rows (now also carrying `print_outcome` + `coupling_factors_json`); + ~50 event rows. ~190k rows total per run, still well under 10 MB SQLite. Full DB for ~5 demo runs comfortably fits in git.

## References

- SQLite, [`WITHOUT ROWID` Optimization](https://www.sqlite.org/withoutrowid.html) — when a covering primary key beats the default rowid table.
- SQLite, [Write-Ahead Logging](https://www.sqlite.org/wal.html) — concurrent reader during the Phase 2 write loop.
- WiseLibs, [`better-sqlite3`](https://github.com/WiseLibs/better-sqlite3) — synchronous Node binding, prebuilt binaries, used here for Phase 3 tool calls.
- TRACK-CONTEXT §3 Data Contract, §4 Phase 2 minimum bar (CSV/JSON/SQLite explicitly allowed), §4 Phase 3 grounding protocol (every answer cites a row).
- `04-aging-baselines-and-normalization.md` — defines the `status` enum thresholds the chatbot will surface.

## Open questions

- **Timestamp type.** Going with ISO-8601 TEXT for human-readability in `sqlite3` CLI demos; if range scans get slow we switch to INTEGER unix-seconds with no schema change other than the column type.
- **Multiple components of the same kind.** Current schema assumes one of each (`blade`, `rail`, `nozzle`, `cleaning`, `heater`, `sensor`). If we model multiple heating zones we add a `component_id` suffix (`heater_z1`) rather than a separate column — keeps the PK shape.
- **Snapshot vs. delta.** We persist absolute values every tick (snapshot). Cheaper to query, slightly more storage. Fine at this scale.
- **Where the file lives in Phase 3 deploy.** Likely bundled into the Next.js app under `/app/data/historian.sqlite` and opened read-only at boot. Confirmed reachable from Vercel runtimes via the Node.js runtime (not Edge); revisit if we move to Edge.
