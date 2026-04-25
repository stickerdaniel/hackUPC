# 20 — Stage 2: Clock, Drivers, Historian, Dashboard

> Phase 2 deliverable. The clock that drives the engine, the four driver generators, the chaos overlay, the named-event overlay, and the SQLite historian that backs everything.

---

## The simulation loop

Source: `sim/src/copilot_sim/simulation/loop.py:41`.

```python
@dataclass(slots=True)
class SimulationLoop:
    engine: Engine
    profile: DriverProfile
    policy: HeuristicPolicy | None
    writer: HistorianWriter
    horizon_ticks: int
    dt_seconds: int = 604800        # 1 simulated week
    start_time: datetime | None = None

    def run(self, initial_state: PrinterState) -> PrinterState:
        state = initial_state
        for tick_index in range(self.horizon_ticks):
            step = self.profile.sample(tick_index)              # → SampledStep
            new_state, observed, coupling = self.engine.step(
                state, step.drivers, step.env, dt=1.0
            )

            self.writer.write_tick(true_state=new_state, observed=observed,
                                   drivers=step.drivers, env=step.env,
                                   coupling=coupling, ts_iso=ts_iso)

            for fired in step.fired_events:
                self.writer.write_environmental_event(...)

            state = new_state

            if self.policy is not None:
                actions = self.policy.decide(observed, tick=new_state.tick)
                for action in actions:
                    state, event = self.engine.apply_maintenance(state, action)
                    self.writer.write_event(event, ts_iso=ts_iso)

        self.writer.close()
        return state
```

Per-tick flow, locked by `docs/research/20-engine-architecture.md` §what-lives-outside-the-engine:

1. **Sample drivers + environment** from the `DriverProfile` (`drivers_src/assembly.py`).
2. **Call the engine** with `(prev, drivers, env, dt=1.0)` → get `(true, observed, coupling)`.
3. **Persist tick** to the historian (7 tables).
4. **Write environmental events** that fired this tick (named, scheduled).
5. **Ask the policy** for `MaintenanceAction`s, each applied via `engine.apply_maintenance` *between* ticks (never inside step) and persisted as `OperatorEvent` rows.
6. Loop until `horizon_ticks`.

**Determinism contract**: same seed + same scenario YAML = byte-identical historian. The engine and the driver profile each own their RNG; nothing in the loop introduces non-determinism.

---

## The DriverProfile — assembly of the four generators + overlays

Source: `sim/src/copilot_sim/drivers_src/assembly.py`.

Per tick: `generators (scalars) → chaos.apply(scalars) → clip drivers to [0, 1] → Drivers/Environment construction → events.apply(Drivers, Environment) → SampledStep`.

```python
@dataclass(slots=True)
class DriverProfile:
    temperature_gen: DriverGenerator
    humidity_gen: DriverGenerator
    load_gen: DriverGenerator
    maintenance_gen: DriverGenerator
    base_environment: Environment
    chaos: ChaosOverlay
    events: EventOverlay
    seed: int = 0

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng((int(self.seed), 0xD7_1A_E9))
        self.chaos.roll(self.seed)        # pre-roll Poisson/Bernoulli arrivals
        self.events.roll(self.seed)       # no-op (deterministic schedule)

    def sample(self, tick_index: int) -> SampledStep:
        rng = self._rng
        temp  = self.temperature_gen.sample(tick_index, env, rng)
        humid = self.humidity_gen.sample(tick_index, env, rng)
        load  = self.load_gen.sample(tick_index, env, rng)
        maint = self.maintenance_gen.sample(tick_index, env, rng)

        temp, humid, maint = self.chaos.apply(tick_index, temp, humid, maint)

        drivers = Drivers(
            temperature_stress=float(np.clip(temp, 0.0, 1.0)),
            ...
        )

        output_tick = tick_index + 1
        drivers, env, fired = self.events.apply(output_tick, drivers, env)

        return SampledStep(drivers=drivers, env=env, fired_events=tuple(fired))
```

The driver clip happens **before** events because event-defined `driver_overrides` are validated to `[0, 1]` at YAML-load (in `EventCfg`). So no post-event clip is needed.

---

## The four driver generators

Source: `sim/src/copilot_sim/drivers_src/generators.py`.

### Temperature — `SinusoidalSeasonalTemp`

Annual cosine + weekly wobble + mean-reverting AR(1) noise:

```python
phase = 2π * tick / period_weeks                # period_weeks = 52
seasonal = base - amplitude * cos(phase)        # winter low → summer high
weekly_wobble = 0.02 * (sin(2π·tick/7) + 0.5·sin(2π·tick/3.5 + 1.7))
innovation = N(0, noise_sigma)
self._noise_state += noise_theta * (innovation - self._noise_state)
value = seasonal + weekly_wobble + self._noise_state
return clip(value, 0, 1)
```

The weekly wobble is a "realism touch" — without it, the temperature curve looks unrealistically perfect. The wobble adds a 2 % amplitude jiggle at weekly + half-weekly periods that visually breaks the perfect sine.

### Humidity — `OUHumidity` (Ornstein-Uhlenbeck mean-reverting)

```python
shock = N(0, 1)
next_x = self._state + theta * (mean - self._state) + sigma * shock
self._state = clip(next_x, 0, 1)
return self._state
```

OU is the **standard stochastic process for noisy-but-bounded signals**: humidity drifts but always reverts to factory-baseline mean. The half-life is `ln(2)/theta ≈ 14 weeks` at default `theta = 0.05` — slow but defensible for an indoor humidity-controlled facility.

### Load — `MonotonicDutyLoad` OR `SmoothSyntheticOperationalLoad`

`MonotonicDutyLoad`: linear annual drift + 3-week wobble. Simpler.

`SmoothSyntheticOperationalLoad`: OU mean-reverting around a seasonal target + Bernoulli idle/overload weeks (5 % idle, 4 % overload). Used in `barcelona-baseline.yaml` because it's more realistic — captures real factory cadence.

### Maintenance — `StepMaintenance` (piecewise constant)

```python
schedule = [{"tick": 0, "value": 0.7}, {"tick": 26, "value": 0.5}, ...]
```

The most recent entry whose `tick <=` current wins. Maintenance changes are step events (a manager makes a decision), not continuous.

---

## The chaos overlay (Stochastic Realism bonus)

Source: `sim/src/copilot_sim/drivers_src/chaos.py`.

**Pre-rolled at scenario load**, not per-tick sampling. A separate inner RNG keyed on `(seed, 0xC4_A0_5E)` produces immutable tick sets:

```python
class ChaosOverlay:
    enabled: bool = False
    horizon_ticks: int = 0
    temp_spike_lambda_per_year: float = 4.0
    contamination_burst_lambda_per_year: float = 6.0
    skipped_maintenance_p: float = 0.10

    temp_spike_ticks: Set[int] = field(default_factory=frozenset)
    contamination_burst_ticks: Set[int] = field(default_factory=frozenset)
    skipped_maintenance_ticks: Set[int] = field(default_factory=frozenset)

    def roll(self, seed: int) -> None:
        rng = np.random.default_rng((int(seed), 0xC4_A0_5E))
        years = self.horizon_ticks / 52.0
        temp_count = int(rng.poisson(self.temp_spike_lambda_per_year * years))
        contam_count = int(rng.poisson(self.contamination_burst_lambda_per_year * years))
        # Pick exact ticks for each event...

    def apply(self, tick, t, h, m):
        if tick in self.temp_spike_ticks:
            t = min(1.0, t + 0.30)
        if tick in self.contamination_burst_ticks:
            h = min(1.0, h + 0.40)
        if tick in self.skipped_maintenance_ticks:
            m = 0.0
        return t, h, m
```

The pre-roll design means **chaos schedule is stable across process restarts** even if per-component RNGs evolve. A separate RNG tag (`0xC4_A0_5E`) ensures chaos and component RNGs don't interact.

**Disabled by default** in `barcelona-baseline.yaml` and `phoenix-aggressive.yaml`. Enable in `chaos-stress-test.yaml` or by adding `chaos.enabled: true` to a scenario.

---

## The named-event overlay (narrative one-offs)

Source: `sim/src/copilot_sim/drivers_src/events.py`.

Distinct from chaos in three ways:

1. **Named** — every event carries a `name` that lands on the historian's `environmental_events` table, so a Phase 3 chatbot can answer "what happened in week 27?" with real attribution.
2. **Scheduled** — fires on a deterministic `output_tick` from the YAML, no RNG.
3. **Both surfaces** — events can patch either `Drivers` (e.g., zero `maintenance_level`) or `Environment` (e.g., spike `vibration_level`). Chaos can only touch the three drivers it knows about.

Used for: earthquake, HVAC failure, operator holiday, etc. Example YAML:

```yaml
events:
  - tick: 27
    name: hvac_failure
    duration: 4
    driver_overrides:
      humidity_contamination: 0.85
    env_overrides:
      vibration_level: 0.40
    disable_human_maintenance: true
```

The `disable_human_maintenance: true` flag prevents the heuristic policy from intervening during the event window — useful for showing what happens when the operator can't respond (e.g., during a holiday).

---

## The historian schema (SQLite WAL)

Source: `sim/src/copilot_sim/historian/schema.sql`.

**Seven tables**, all time-series tables `WITHOUT ROWID` (SQLite stores row data inline with the index — single B-tree lookup):

```sql
runs (run_id PRIMARY KEY, scenario, profile, dt_seconds, seed,
      started_at_iso, horizon_ticks, notes)

drivers (run_id, tick, ts_iso, sim_time_s,
         temperature_stress, humidity_contamination, operational_load, maintenance_level,
         base_ambient_C, weekly_runtime_hours,
         print_outcome, coupling_factors_json, environment_json,
         PRIMARY KEY (run_id, tick)) WITHOUT ROWID

component_state (run_id, tick, component_id, health_index, status, age_ticks,
                 PRIMARY KEY (run_id, tick, component_id)) WITHOUT ROWID

metrics (run_id, tick, component_id, metric, value,
         PRIMARY KEY (run_id, tick, component_id, metric)) WITHOUT ROWID

observed_component_state (run_id, tick, component_id,
                          observed_health_index, observed_status, sensor_note,
                          PRIMARY KEY (run_id, tick, component_id)) WITHOUT ROWID

observed_metrics (run_id, tick, component_id, metric,
                  observed_value, sensor_health,
                  PRIMARY KEY (run_id, tick, component_id, metric)) WITHOUT ROWID

events (event_seq PRIMARY KEY AUTOINCREMENT, run_id, tick, ts_iso, sim_time_s,
        kind, component_id, payload_json)
INDEX idx_events_run_tick ON events (run_id, tick)

environmental_events (event_seq PRIMARY KEY AUTOINCREMENT, run_id, tick, ts_iso, sim_time_s,
                      name, payload_json)
INDEX idx_env_events_run_tick ON environmental_events (run_id, tick)
```

### Why `WITHOUT ROWID`?

By default, SQLite stores every row as `(rowid, content)` in a B-tree, with secondary indexes pointing back to the rowid. For our time-series tables where the natural primary key is `(run_id, tick, ...)`, this means **every lookup is two B-tree traversals**: one on the index, one on the rowid.

`WITHOUT ROWID` makes the primary key itself the B-tree key, with row data stored inline. **Single B-tree lookup**, ~2× faster, and ~30 % smaller on disk. At 6 components × 3 metrics × 260 ticks per run, the savings matter.

### Why `coupling_factors_json` and `environment_json`?

These are the **attribution channels**. Storing the full coupling factor dict + the full Environment per tick lets a Phase 3 chatbot or the dashboard's panel 2 walk back any failure to its root drivers **without re-running the engine**. The brief's *Realism & Fidelity* pillar explicitly demands this: "every failure event traceable to its root input drivers".

### WAL pragmas

The writer sets:

```sql
PRAGMA journal_mode=WAL;        -- write-ahead log: writers don't block readers
PRAGMA synchronous=NORMAL;      -- fsync only on checkpoint (faster, still safe)
PRAGMA busy_timeout=5000;       -- retry for 5s if locked
```

This lets the **Streamlit dashboard read the live historian** in read-only mode while a simulation is still writing — no locking, no inconsistency.

---

## The HistorianWriter — batched insert

Source: `sim/src/copilot_sim/historian/writer.py`.

Buffers `executemany` arrays per table and flushes every `flush_every` ticks (default 50). `close()` flushes the tail and commits.

For a 5-year run (260 ticks) at 6 components × 3 metrics:
- `metrics` table: ~4,680 rows
- `component_state`: ~1,560 rows
- `drivers`: 260 rows
- `observed_*` mirrors: ~6,240 rows total
- Plus events. Roughly **~13,000 rows per run**, sub-second writes, well under 10 MB SQLite. Safe to commit a seeded `historian.sqlite` to git as a fallback for ~5 demo runs.

---

## The CLI — `copilot-sim`

Source: `sim/src/copilot_sim/cli.py`.

```
copilot-sim run <scenario.yaml> [--db-path PATH] [--flush-every N] [--notes TEXT]
copilot-sim list-scenarios
copilot-sim inspect [run_id] [--db-path PATH] [--failure-analysis]
```

**`copilot-sim inspect <run_id> --failure-analysis`** is the brief's *Failure Analysis* deliverable in one command. It:

1. Reads the run summary from `runs`.
2. Computes per-component first DEGRADED / CRITICAL / FAILED tick from `component_state` status transitions.
3. For each transition, queries `coupling_factors_json` at that tick and surfaces the **top-3 factors by absolute magnitude**.

Output looks like:

```
failure analysis (per-component first transitions):
  blade       DEGRADED=t=42  CRITICAL=t=78   FAILED=t=119
      at-DEGRADED (tick 42): humidity_contamination_effective=0.580, blade_loss_frac=0.350, ...
      at-CRITICAL (tick 78): humidity_contamination_effective=0.690, blade_loss_frac=0.560, ...
      at-FAILED  (tick 119): humidity_contamination_effective=0.720, blade_loss_frac=0.710, ...
```

This is **the single command judges should see** for the Stage 2 *Failure Analysis* deliverable.

---

## The Streamlit dashboard

Source: `sim/src/copilot_sim/dashboard/streamlit_app.py`.

**Four panels** in narrative order:

1. **Driver-coupled component decay** — drivers + status heatmap + selected-tick rule. Shows all six components decaying over the horizon, with status colour bands and event glyphs.
2. **Cascade attribution** — for each CRITICAL/FAILED component, queries `coupling_factors_json` at the transition tick and renders the top-3 factors with cascade-chain text (e.g., "sensor_bias ↑ → control_temp_error ↑ → heater_drift ↑ → HEATER").
3. **True vs observed** — per-component sensor-trust verdict. Shows the §3.4 story made visible: where the operator's view diverges from ground truth.
4. **Maintenance event timeline** — per-component glyphs by `OperatorEventKind` (FIX = triangle-up, REPLACE = triangle-down, TROUBLESHOOT = diamond).

Launch:
```bash
cd sim
uv run streamlit run src/copilot_sim/dashboard/streamlit_app.py
```

The dashboard reads the live SQLite historian (WAL allows concurrent reads while a simulation is running) and uses Altair for chart rendering + matplotlib for deck PNG export.

---

## Scenario YAML — the run configuration

Source: `sim/scenarios/*.yaml`, validated by `simulation/scenarios.py` (pydantic).

Example structure (`barcelona-baseline.yaml`):

```yaml
run:
  scenario: barcelona
  profile: baseline
  seed: 42
  horizon_ticks: 260       # 5 years × 52 weeks
  dt_seconds: 604800       # 1 week

environment:
  base_ambient_C: 22.0
  amplitude_C: 8.0
  weekly_runtime_hours: 60
  vibration_level: 0.10

drivers:
  temperature_stress: {kind: sinusoidal_seasonal, base: 0.30, amplitude: 0.10, ...}
  humidity_contamination: {kind: ornstein_uhlenbeck, mean: 0.35, theta: 0.05, sigma: 0.04}
  operational_load: {kind: smooth_synthetic, mean: 0.55, ...}
  maintenance_level: {kind: step, schedule: [{tick: 0, value: 0.7}]}

chaos: {enabled: false}
policy: {kind: heuristic}
historian: {path: data/historian.sqlite}
```

The pydantic models (`_Strict` with `extra="forbid"`) reject any unknown key — catches typos at YAML load instead of at runtime. Per-key range checks on `env_overrides` (e.g. `vibration_level ∈ [0, 1]`) catch the kind of mistake where someone writes `vibration_level: 8.5` (intending 0.85) and gets 50× rail wear.

### What changes between scenarios?

Comparing `barcelona-baseline.yaml` and `phoenix-aggressive.yaml`:

| Field | Barcelona | Phoenix | Why |
|---|---|---|---|
| `base_ambient_C` | 22 | 32 | Phoenix is hotter |
| `amplitude_C` | 8 | 12 | Phoenix has wider seasonal swings |
| `weekly_runtime_hours` | 60 | 110 | Phoenix is high-duty |
| `temperature_stress.base` | 0.30 | 0.65 | Phoenix runs at higher stress |
| `humidity.mean` | 0.35 | 0.30 | Phoenix is drier |
| `maintenance.value` | 0.7 | 0.5 | Phoenix has worse maintenance |

This is a **clean A/B**: same horizon, same seed, same scenario shape — only climate + duty change. Different components fail first per climate (Phoenix → heater + sensor; Barcelona → blade + nozzle). That's the *What-If Scenarios* bonus pillar from stage-1.md and stage-2.md.

---

## Cross-references

- The engine `step()` it calls: [`02-engine-architecture.md`](02-engine-architecture.md).
- The maintenance policy: [`21-policy-and-maintenance.md`](21-policy-and-maintenance.md).
- The cascade story persisted in `coupling_factors_json`: [`03-coupling-and-cascades.md`](03-coupling-and-cascades.md).
- Stage 2 brief: `docs/briefing/stage-2.md`.
- Research backing: `docs/research/06-driver-profiles-and-time.md` (drivers), `docs/research/07-weather-api.md` (live weather plan), `docs/research/08-historian-schema.md` (schema design).
