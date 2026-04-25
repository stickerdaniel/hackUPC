-- Historian schema. Plan §Historian: seven tables, WITHOUT ROWID on the
-- time-series tables so SQLite stores the row inline with the index.
-- All time-series tables compose the run_id + tick (+ component_id +
-- metric) primary key so a future query like "give me the heater drift
-- for run X" hits a single B-tree lookup.

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    scenario TEXT NOT NULL,
    profile TEXT,
    dt_seconds INTEGER NOT NULL,
    seed INTEGER NOT NULL,
    started_at_iso TEXT NOT NULL,
    horizon_ticks INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS drivers (
    run_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    ts_iso TEXT NOT NULL,
    sim_time_s REAL NOT NULL,
    temperature_stress REAL NOT NULL,
    humidity_contamination REAL NOT NULL,
    operational_load REAL NOT NULL,
    maintenance_level REAL NOT NULL,
    base_ambient_C REAL,
    weekly_runtime_hours REAL,
    print_outcome TEXT,
    coupling_factors_json TEXT,
    -- Full per-tick Environment snapshot. Keeps event-driven env
    -- overrides (vibration_level, amplitude_C) queryable per row.
    environment_json TEXT,
    PRIMARY KEY (run_id, tick)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS component_state (
    run_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    component_id TEXT NOT NULL,
    health_index REAL NOT NULL,
    status TEXT NOT NULL,
    age_ticks INTEGER NOT NULL,
    PRIMARY KEY (run_id, tick, component_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS metrics (
    run_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    component_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    PRIMARY KEY (run_id, tick, component_id, metric)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS observed_component_state (
    run_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    component_id TEXT NOT NULL,
    observed_health_index REAL,
    observed_status TEXT,
    sensor_note TEXT,
    PRIMARY KEY (run_id, tick, component_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS observed_metrics (
    run_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    component_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    observed_value REAL,
    sensor_health REAL,
    PRIMARY KEY (run_id, tick, component_id, metric)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS events (
    event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    ts_iso TEXT NOT NULL,
    sim_time_s REAL NOT NULL,
    kind TEXT NOT NULL,
    component_id TEXT,
    payload_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_run_tick ON events (run_id, tick);

-- Named environmental events (earthquake, HVAC failure, holiday, ...).
-- Distinct from `events` (operator/policy timeline). Multi-tick events
-- write one row per active tick so a per-tick query at any tick in the
-- window sees the override.
CREATE TABLE IF NOT EXISTS environmental_events (
    event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    ts_iso TEXT NOT NULL,
    sim_time_s REAL NOT NULL,
    name TEXT NOT NULL,
    payload_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_env_events_run_tick ON environmental_events (run_id, tick);
