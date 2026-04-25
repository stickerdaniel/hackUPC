# Distributed Splashing Turtle — HackUPC Metal Jet S100 Engine Implementation

## Context

We're building the simulation engine for the HackUPC 2026 "When AI meets reality" project — a digital twin of the HP Metal Jet S100 binder-jet 3D printer that scores Phase 1 (mathematical model) and Phase 2 (time-advancing simulation + historian). All design decisions are locked through a Socratic walkthrough; the domain types are already implemented in code (`sim/src/copilot_sim/domain/`); every other subpackage is empty. This plan implements the rest.

The key strategic shifts that informed this plan:
- Time step changed from hourly to **weekly** (multi-year horizon makes hourly inputs infeasible).
- Component count expanded from the brief's mandatory 3 to **6** (two per subsystem, per team agreement).
- Canvas's uniform `metric += base · Π(1+driver)` template re-grounded against **named failure laws** (Archard / Lundberg-Palmgren / Coffin-Manson + Poisson / wear-per-cycle / Arrhenius) to satisfy the brief's "≥ 2 standard mathematical failure models" requirement.
- §3.4 observability split (true vs observed state) wired through the engine's return so the maintenance policy reads only `ObservedPrinterState`, enabling the sensor-fault-vs-component-fault story.

Outcome: a deterministic, seeded, six-component coupled simulation that writes both true and observed states to a SQLite historian over multi-year runs across three demoable scenarios.

## Locked decisions (one-line each)

- `dt = 1` simulated week (168 sim-hours), default horizon 5 years (260 ticks).
- Six components: blade + rail + nozzle + cleaning + heater + sensor (two per subsystem).
- Coupled discrete-time, double-buffered; all components read same `t-1` `PrinterState`; `CouplingContext` built once per tick.
- Status thresholds: `≥ 0.75 / ≥ 0.45 / ≥ 0.20 / < 0.20` → FUNCTIONAL / DEGRADED / CRITICAL / FAILED.
- Maintenance damper `(1 − 0.8·maintenance_quality)` everywhere; `(1 − cleaning_effectiveness)` is the special damper for nozzle clog reset only.
- Sawtooth resets via `Engine.apply_maintenance(MaintenanceAction)`, separate from `Engine.step()`. Per-component reset rules per `OperatorEventKind ∈ {TROUBLESHOOT, FIX, REPLACE}` from doc 09.
- Universal Weibull baseline: `H_total = (1 − weighted_metrics) · exp(−(age_ticks·weeks_per_tick / η_weeks)^β)`. Per-component (η_weeks, β) pairs lifted from doc 22.
- Per-component foundations:
  - Blade — Archard's wear law (multipliers map to k / F / s / H amplifiers).
  - Rail — Lundberg-Palmgren cubic load-life (`effective_load^3`).
  - Nozzle — Coffin-Manson + Palmgren-Miner (literal physics) + Poisson clog hazard.
  - Cleaning — power-law wear-per-cycle in `cumulative_cleanings`.
  - Heater — Arrhenius acceleration factor (drift leads, power follows in same tick, intra-component).
  - Sensor — Arrhenius bias drift + sub-linear noise growth.
- Drivers: 4 brief-mandated values in `Drivers` (already coded). Sibling `Environment` carries `ambient_temperature_C`, `weekly_runtime_hours`, `vibration_level` (constant per scenario), `cumulative_cleanings`, `hours_since_maintenance`, `start_stop_cycles`.
- Driver generators: sinusoidal seasonal (temp), Ornstein-Uhlenbeck (humidity_contamination), monotonic + weekly duty-cycle (operational_load), step function (maintenance_level).
- Chaos overlay (driver-layer only, pre-rolled at scenario load): Poisson temp spikes (λ = 4/yr), contamination bursts (λ = 6/yr), Bernoulli skipped maintenance (p = 0.1). Disabled by default.
- Cleaning cycles per week: `auto_cleanings = weekly_runtime_hours / 4` plus `+3` on maintenance ticks.
- Historian: SQLite WAL with seven tables — `runs`, `drivers` (carries print_outcome + coupling_factors_json), `component_state`, `metrics`, `observed_component_state`, `observed_metrics`, `events`. `WITHOUT ROWID` on time-series tables.
- `PrintOutcome` derivation: `HALTED` if any component status is FAILED; `QUALITY_DEGRADED` if any CRITICAL or `min(component_health) < 0.40`; else `OK`.
- Maintenance heuristic policy reads `ObservedPrinterState` only. Triggers (in order): `UNKNOWN` → `TROUBLESHOOT(component)`; observed health < 0.20 → `REPLACE(component)`; observed health < 0.45 → `FIX(component)`; monthly fallback `FIX` of longest-unmaintained component.
- Three scenarios: `barcelona-baseline` (nominal), `phoenix-aggressive` (heat + load stress), `chaos-stress-test` (chaos enabled, sensor drift dominant).
- CLI: `copilot-sim run <scenario>`, `copilot-sim list-scenarios`, `copilot-sim inspect <run_id>`.
- Tests: minimum hackathon-grade — one smoke per component + one 5-year integration smoke.
- Branching: direct push to main, ~17–20 well-messaged conventional commits.
- Sensor sign convention: always `+1` (sensor reads consistently low), simpler story.

## Implementation approach (recommended)

### Module / file layout

All paths under `sim/src/copilot_sim/`. Existing empty `__init__.py`s become real modules.

```
engine/
  aging.py           # weibull_baseline, maintenance_damper, status_from_health, clip01,
                     # derive_component_rng(scenario_seed, tick, component_id)
  coupling.py        # build_coupling_context(prev, drivers, env, dt) → CouplingContext
  assembly.py        # derive_print_outcome, build_observed_state
  engine.py          # Engine class: step(prev, drivers, env, dt), apply_maintenance(state, action)

components/
  registry.py        # ComponentSpec dict; engine consumes registry, never imports per-component files
  blade.py rail.py nozzle.py cleaning.py heater.py sensor.py
  # each exports: step(prev_self, coupling, drivers, env, dt, rng) → ComponentState
  #               reset(prev_self, kind, payload) → ComponentState
  #               initial_state() → ComponentState
  #               sensor_model() → SensorModel

drivers_src/
  environment.py     # Environment dataclass (loop-managed mutable counters)
  generators.py      # SinusoidalSeasonalTemp, OUHumidity, MonotonicDutyLoad, StepMaintenance
  chaos.py           # ChaosOverlay (pre-rolls Poisson event ticks at construction)
  assembly.py        # DriverProfile.sample(tick) → tuple[Drivers, Environment]

sensors/
  model.py           # SensorModel protocol + SensorState
  factories.py       # make_sensor_model(component_id, sensor_state)

historian/
  schema.sql
  connection.py      # open_db with WAL pragmas, bootstrap idempotently
  writer.py          # HistorianWriter (write_run, write_tick, write_event, close)
  reader.py          # for CLI inspect + dashboard
  run_id.py

policy/
  heuristic.py       # HeuristicPolicy.decide(observed, last_action_tick, tick) → list[MaintenanceAction]

simulation/
  scenarios.py       # pydantic ScenarioConfig + load_scenario(path)
  bootstrap.py       # initial_printer_state() from registry
  loop.py            # SimulationLoop(engine, profile, policy, writer).run(horizon_ticks)

cli.py               # entry point: copilot-sim run/list-scenarios/inspect

dashboard/
  streamlit_app.py   # 6 charts (deferred slot for AI-surrogate parity)
```

Scenarios at `sim/scenarios/{barcelona-baseline,phoenix-aggressive,chaos-stress-test}.yaml`.

Tests under `sim/tests/`:
- `components/test_<each>_smoke.py` — six files, one tick each. Three universal assertions for every component:
  1. **Health bounds**: `0.0 ≤ health_index ≤ 1.0` for all ticks.
  2. **Status monotonicity (without maintenance)**: status only progresses through `FUNCTIONAL → DEGRADED → CRITICAL → FAILED`, never backwards.
  3. **Metric direction (without maintenance)**: per-component expected directions, declared in a `EXPECTED_METRIC_DIRECTIONS: Mapping[str, Literal["non_decreasing", "non_increasing"]]` table:
     - Blade: `wear_level`, `edge_roughness` → non_decreasing
     - Rail: `misalignment`, `friction_level` → non_decreasing
     - Nozzle: `clog_pct`, `thermal_fatigue` → non_decreasing
     - Cleaning: `wiper_wear`, `residue_saturation` → non_decreasing; **`cleaning_effectiveness` (derived) → non_increasing**
     - Heater: `resistance_drift`, `power_draw` → non_decreasing
     - Sensor: `bias_offset` (with sign convention `+1` → non_decreasing), `noise_sigma` → non_decreasing; **`reading_accuracy` (derived) → non_increasing**

  The shared assertion helper `assert_metrics_in_expected_direction(prev_state, curr_state, component_id)` reads the table and applies the right monotonicity check per metric. Same helper is reused inside the 5-year integration test as a sanity invariant between consecutive ticks (skipped on maintenance ticks).
- `engine/test_coupling.py` — coupling math regressions.
- `engine/test_engine_step.py` — one tick, six components, observed shape.
- `engine/test_driver_coverage.py` — parametric: for each component × each driver, varying that driver from 0 → 1 with others held neutral changes the metric increment in the expected direction (3 stressors increase, maintenance_level decreases). This test is what guarantees the brief minimum requirement #3.
- `engine/test_rng_determinism.py` — same `(scenario_seed, tick, component_id)` always yields the same RNG stream regardless of iteration order or process restart. Catches the `PYTHONHASHSEED` trap.
- `simulation/test_full_run.py` — 5-year integration; finishes without crash, DB non-empty.

### Implementation order (strict dependency-first)

1. `engine/aging.py` (no other imports).
2. `engine/coupling.py` (depends on domain only).
3. `components/registry.py` skeleton (signatures + initial-state factories + dummy step bodies returning `prev_self`).
4. Six per-component step functions, each alongside its smoke test (any order — they don't depend on each other; the registry decouples them from the engine).
5. `engine/assembly.py` (`derive_print_outcome`, `build_observed_state` glue).
6. `engine/engine.py` (`Engine.step`, `Engine.apply_maintenance`).
7. `sensors/model.py` + `sensors/factories.py` + wire into `Engine.step`.
8. `drivers_src/` (environment, generators, chaos, assembly).
9. `policy/heuristic.py`.
10. `historian/` (schema, connection, run_id, writer, reader).
11. `simulation/` (bootstrap, scenarios, loop).
12. Three scenario YAMLs.
13. `cli.py`.
14. `simulation/test_full_run.py` integration test — first end-to-end run.
15. `dashboard/streamlit_app.py`.

### Commit splitting and parallel workstreams

The implementation track is sequential (each commit depends on the previous compiling); the docs track can run in parallel from a clear dependency point. Three groups:

**Track A — Implementation (sequential, single-owner)**

A1. `chore(sim): scaffold engine/components/drivers/sensors/historian/policy/simulation packages`
A2. `feat(engine): add aging helpers (weibull, damper, status thresholds, derive_component_rng)`
A3. `feat(engine): build CouplingContext from prev PrinterState + drivers + env`
A4. `feat(components): add registry + initial-state factories for the six components`
A5. `feat(components): implement blade Archard step + smoke test`
A6. `feat(components): implement rail Lundberg-Palmgren step + smoke test`
A7. `feat(components): implement nozzle Coffin-Manson + Poisson clog step + smoke test`
A8. `feat(components): implement cleaning power-law wear step + smoke test`
A9. `feat(components): implement heater Arrhenius step + smoke test`
A10. `feat(components): implement sensor Arrhenius drift step + smoke test`
A11. `feat(engine): wire Engine.step orchestration + derive_print_outcome` ← **architecture stabilises here**
A12. `feat(engine): add apply_maintenance reset rules per OperatorEventKind`
A13. `feat(sensors): add per-component sensor models and ObservedPrinterState builder`
A14. `feat(drivers): add Environment, sinusoidal/OU/duty/step generators, chaos overlay`
A15. `feat(historian): add SQLite WAL schema + writer/reader + run_id`
A16. `feat(policy): add heuristic maintenance policy`
A17. `feat(simulation): add SimulationLoop + scenario loader + 3 scenario YAMLs`
A18. `feat(cli): add copilot-sim run/list-scenarios/inspect` ← **CLI commands stabilise here**
A19. `feat(cli): add inspect --failure-analysis (per-component first-DEGRADED/CRITICAL/FAILED tick + top coupling factors at each transition)`
A20. `test(simulation): add 5-year integration smoke + driver coverage + RNG determinism` ← **first verified scenario runs available here**
A21. `feat(dashboard): add Streamlit dashboard with 6 charts` ← **dashboard available for screenshots / video here**

**Track B — Documentation skeletons (parallelisable, can start after A11)**

These are written by a *different owner* than Track A. They do NOT block on A21 finishing — only on the architecture being clear enough to describe (A11) and the CLI surface being stable enough to document (A18).

B1. `docs(readme): add sim setup + scenario run instructions` (after A18 — CLI stable)
B2. `docs(report): scaffold technical report — sections 1–5 (modelling + simulation design + observability)` (after A11)
B3. `docs(deck): scaffold deck slides 1–6 (mission + Phase 1 brain + Phase 1 cascade + Phase 2 clock)` (after A11)
B4. `docs(demo): rough demo flow + minute-by-minute structure` (after A18)

These commits intentionally leave placeholder text where results will land — `<chart pending>`, `<TODO: insert run-id>`, `<TODO: blade fails at week N from chaos-stress-test>`. They do not fabricate numbers.

**Track C — Documentation results (must follow A20 + first real scenario runs)**

C1. `docs(report): fill Phase 1 results — driver coverage matrix verified, sample failure trajectories from each scenario` (after A20)
C2. `docs(report): fill Phase 2 results — failure analysis per component, A/B chart data, evaluation against pillars` (after A20 + dashboard screenshots)
C3. `docs(deck): finalise slides with charts + screenshots from real runs` (after A21)
C4. `docs(demo): finalise script with exact run IDs + chart timestamps` (after A21)
C5. `docs(walkthrough): record + link 3-minute Loom video` (after A21, Saturday evening)

**Track D — Submission gate (final, blocks on all tracks)**

D1. `chore(submission): bundle deck PDF + report PDF + walkthrough link + repo URL`
D2. Submit to Devpost by **2026-04-26 09:15 CEST**

### Parallelism rules

- **Track B can start the moment A11 is merged** (engine architecture is observable). Owner: whoever isn't writing engine code — likely Daniel or Jana while Chris drives Track A.
- **Track A continues uninterrupted** through B's work; B doesn't touch implementation files.
- **Track C is gated on A20** (real run data exists) but each C commit is small and parallel-safe. C1 and C3 can run simultaneously once A20 lands.
- **Walkthrough recording (C5) needs the dashboard (A21) running.** Plan a single Saturday-evening recording session after the dashboard is stable; if the dashboard slips, fall back to a screen recording of CLI output + matplotlib PNGs.
- **Direct-push-to-main still applies for both tracks**, but Track B/C commits should never modify implementation files (zero merge-conflict risk that way).

### Earliest-start gantt (informal)

```
A1───A2───A3───A4───A5..A10───A11───A12..A18───A19───A20───A21
                                │                      │     │
                                │        B1 (after A18)│     │
                                │           │          │     │
                                B2 (skeleton)──────────┼─C1──┼──C2─────┐
                                │                      │     │         │
                                B3 (skeleton)──────────┼──┼──┼─C3──────┤
                                │                      │     │         │
                                B4 (skeleton)──────────┼──┼──┼──C4─────┤
                                                       │     │         │
                                                       │     └─C5──────┤
                                                       │               │
                                                       └───────────────D1───D2 (submit)
```

Every commit must:
1. Keep `pytest`, `ruff`, and `ty` green individually so direct-push to main is safe.
2. End the *narrative* portion of its message with a `## Synthetic prompt` block — a short distilled instruction that would reproduce the diff if pasted into a fresh coding session. Useful for reviewers; required by `AGENTS.md`.
3. End the *whole* message with a `Co-Authored-By:` trailer crediting Jana Rawe (https://github.com/jaaana) on every implementation commit.

**No model / agent attribution.** The plan and every commit message must NOT mention which model or AI agent wrote the code, including via "Generated with …" lines, references to "Claude", "GPT", "AI", "Opus", "Sonnet", or any other model name or hint. Commit messages should read as if a human developer wrote them. (This overrides any older `AGENTS.md` example that included a "Generated with …" line — that line is dropped from the convention going forward; AGENTS.md should be patched in the same commit that removes the model-attribution requirement from the local convention.)

**Trailer placement matters.** Git parses trailers as the final block of the message, separated from preceding text by a blank line. So the order is:

```
<type>(scope): subject line

<short body explaining what and why>

## Synthetic prompt

> <distilled instruction>

Co-Authored-By: Jana Rawe <jaaana@users.noreply.github.com>
```

Note the **blank line between the synthetic-prompt narrative block and the `Co-Authored-By:` trailer**. Without that blank line, git's trailer parser may misparse and GitHub may not render Jana as a co-author. With the blank line, the trailer block is unambiguous.

The `Co-Authored-By:` trailer is mandatory for **every** commit on this branch regardless of who wrote it, because it credits Jana as a project teammate.

Worked example:

```
feat(components): implement blade Archard step + smoke test

Adds blade.step that applies Archard's wear law to wear_level and
edge_roughness, with all four brief drivers wired in (temp_stress
bumps hardness softening, contamination + humidity amplify k,
production_load + weekly_runtime_hours/40 drive F·s, maintenance
quality damps via the shared aging helper). Smoke test asserts
health stays in [0,1], status only progresses forward, and damage
metrics move in their per-component expected directions over 50
unmaintained ticks.

## Synthetic prompt

> Implement components/blade.py with Archard's wear law: wear_level
> and edge_roughness recurrences using all four drivers + rail
> coupling, the (1 - 0.8·M) damper from engine.aging, and the
> min(1.0, ...) clamp. Add a smoke test under tests/components/
> that runs 50 ticks at neutral drivers and asserts health bounds
> + status monotone-forward + per-metric expected directions.

Co-Authored-By: Jana Rawe <jaaana@users.noreply.github.com>
```

Use the `git commit -m "$(cat <<'EOF' ... EOF)"` HEREDOC pattern to preserve the blank line between the synthetic prompt block and the trailer exactly.

### Critical interfaces

```python
# engine/engine.py
class Engine:
    def __init__(self, scenario_seed: int, registry: ComponentRegistry) -> None: ...
    def step(self, prev: PrinterState, drivers: Drivers, env: Environment, dt: float
            ) -> tuple[PrinterState, ObservedPrinterState, CouplingContext]: ...
    def apply_maintenance(self, state: PrinterState, action: MaintenanceAction
            ) -> tuple[PrinterState, OperatorEvent]: ...

# engine/coupling.py
def build_coupling_context(prev: PrinterState, drivers: Drivers,
                           env: Environment, dt: float) -> CouplingContext: ...

# components/<x>.py — uniform per-component contract
def step(prev_self: ComponentState, coupling: CouplingContext, drivers: Drivers,
         env: Environment, dt: float, rng: np.random.Generator) -> ComponentState: ...
def reset(prev_self: ComponentState, kind: OperatorEventKind,
          payload: Mapping[str, float]) -> ComponentState: ...
def initial_state() -> ComponentState: ...

# sensors/model.py
class SensorModel(Protocol):
    def observe(self, true: ComponentState, rng: np.random.Generator
            ) -> ObservedComponentState: ...

# drivers_src/generators.py
class DriverGenerator(Protocol):
    def sample(self, tick: int, env: Environment, rng: np.random.Generator) -> float: ...

# historian/writer.py
class HistorianWriter:
    def __init__(self, conn: sqlite3.Connection, run_id: str) -> None: ...
    def write_run(self, scenario: str, profile: str, dt_seconds: int,
                  seed: int, notes: str) -> None: ...
    def write_tick(self, true_state: PrinterState, observed: ObservedPrinterState,
                   drivers: Drivers, env: Environment, coupling: CouplingContext,
                   ts_iso: str) -> None: ...
    def write_event(self, event: OperatorEvent, ts_iso: str) -> None: ...
    def close(self) -> None: ...
```

`Engine.step` returns `CouplingContext` so the loop can persist `coupling_factors_json` without re-deriving.

**RNG strategy (corrected from earlier draft).** Per-component RNGs are derived deterministically from `(scenario_seed, tick, component_id_digest)` rather than spawned sequentially. Concretely each component step receives:

```python
import hashlib

def _component_id_digest(component_id: str) -> int:
    """Stable, process-independent uint64 digest. Python's built-in hash() is
    PYTHONHASHSEED-salted and would break reproducibility across runs."""
    return int.from_bytes(
        hashlib.blake2b(component_id.encode("utf-8"), digest_size=8).digest(),
        byteorder="big",
        signed=False,
    )

def derive_component_rng(scenario_seed: int, tick: int, component_id: str) -> np.random.Generator:
    return np.random.default_rng((scenario_seed, tick, _component_id_digest(component_id)))
```

`blake2b` (or any cryptographic digest) is used specifically to dodge the `PYTHONHASHSEED` trap with `hash(str)`. The result is bit-identical across processes, machines, and Python versions. Helper lives in `engine/aging.py` and is the only sanctioned way to obtain a per-component RNG; verified by `engine/test_rng_determinism.py` which runs the same `(seed, tick, component_id)` twice with shuffled component iteration order and asserts identical generated samples.

### Driver coverage matrix (audited against brief minimum #3)

The brief requires every component to react to all four drivers. Audit:

| Component | temperature_stress | humidity_contamination | operational_load | maintenance_level |
| :--- | :-: | :-: | :-: | :-: |
| Blade | **add `(1 + 0.1·temp_stress_eff)`** for hardness softening | ✓ (k amplifier) | ✓ (F amplifier + s scaling) | ✓ (damper) |
| Rail | **add `(1 + 0.1·temp_stress_eff)`** for lubricant viscosity | ✓ (humidity term) | ✓ (cubic load-life) | ✓ (damper) |
| Nozzle | ✓ (Coffin-Manson Δε_p) + clog hazard | ✓ (clog hazard β) | ✓ (firings/week) | ✓ (damper) |
| Cleaning | **add `(1 + 0.2·temp_stress_eff)`** for binder drying on wiper | ✓ (residue + wiper wear) | ✓ (auto cleanings) | ✓ (damper) |
| Heater | ✓ via BOTH `ambient_temperature_C` AND `(1 + 0.3·temp_stress_eff)` multiplier | ✓ (oxidation amplifier) | ✓ (duty + self-heating) | ✓ (damper) |
| Sensor | ✓ via BOTH `ambient_temperature_C` AND `(1 + 0.3·temp_stress_eff)` multiplier | ✓ (solder corrosion) | ✓ (noise growth term) | ✓ (calibration) |

**`ambient_temperature_C` is derived from the brief Driver, not independent of it.** Environment carries `base_ambient_C` (the per-scenario nominal — e.g. 22 for Barcelona, 32 for Phoenix). The per-tick effective ambient that the heater / sensor Arrhenius reads is

```
ambient_temperature_C_effective = env.base_ambient_C + env.amplitude_C · (2·temp_stress_eff − 1)
```

so when the deterministic driver generator + chaos overlay produces a high `temperature_stress` value for this tick, the resulting Kelvin temperature seen by the Arrhenius AF computation rises accordingly. The brief Driver flows through into the heater/sensor physics via this derived field. The additional `(1 + 0.3·temp_stress_eff)` multiplier in the recurrence is the second visible coupling, so any auditor sees the Drivers field referenced explicitly in the formula text.

Three further small couplings (blade / rail / cleaning) close the temperature_stress gap there. Each is physically defensible (hardness softening, lubricant thinning, binder drying) and small enough not to dominate the main physics.

This audit lives in the test suite as `engine/test_driver_coverage.py` — a parametric test that, for every component:

- varying **`temperature_stress`** from 0 → 1 (others held neutral) → strictly *larger* metric increment over one tick;
- varying **`humidity_contamination`** from 0 → 1 → strictly *larger* metric increment;
- varying **`operational_load`** from 0 → 1 → strictly *larger* metric increment;
- varying **`maintenance_level`** from 0 → 1 → strictly *smaller* metric increment (better maintenance ⇒ less degradation).

The maintenance assertion direction is inverted versus the three stressor drivers because `(1 − 0.8·maintenance_quality)` is a damper, not an amplifier.

### Scenario YAML schema (one example, three files)

```yaml
# sim/scenarios/barcelona-baseline.yaml
run:
  scenario: barcelona
  profile: baseline
  seed: 42
  horizon_ticks: 260       # 5 years × 52 weeks
  dt_seconds: 604800       # 1 week
environment:
  base_ambient_C: 22.0       # nominal scenario temperature (Barcelona ~22°C, Phoenix ~32°C)
  amplitude_C: 8.0           # ± swing the per-tick temperature_stress driver maps onto
                             # ambient_temperature_C_eff = base_ambient_C + amplitude_C·(2·temp_stress_eff − 1)
  weekly_runtime_hours: 60
  vibration_level: 0.10
drivers:
  temperature_stress:
    kind: sinusoidal_seasonal
    base: 0.30
    amplitude: 0.10
    period_weeks: 52
  humidity_contamination:
    kind: ornstein_uhlenbeck
    mean: 0.35
    theta: 0.05
    sigma: 0.04
  operational_load:
    kind: monotonic_duty_cycle
    base: 0.55
    monotonic_drift_per_year: 0.02
    duty_cycle_amplitude: 0.10
  maintenance_level:
    kind: step
    schedule: [{tick: 0, value: 0.7}]
chaos:
  enabled: false
policy:
  kind: heuristic
historian:
  path: data/historian.sqlite
```

`phoenix-aggressive` overrides `environment.base_ambient_C: 32.0, amplitude_C: 12.0`, `temperature_stress.base = 0.65, amplitude = 0.20`, `operational_load.base = 0.85`, `weekly_runtime_hours = 110`. `chaos-stress-test` flips `chaos.enabled: true` with `temp_spike_lambda_per_year: 4`, `contamination_burst_lambda_per_year: 6`, `skipped_maintenance_p: 0.10`, plus elevated initial sensor `noise_sigma_c`.

Pydantic `ScenarioConfig` validates these; unknown `kind:` values fail-fast at load time.

### Risks acknowledged and mitigated in the plan

- **RNG determinism**: per-component RNGs are derived from `(scenario_seed, tick, component_id_hash)` (NOT sequential `spawn()`), so reordering component iteration cannot change results.
- **Maintenance damper coverage**: centralise in `engine/aging.py:maintenance_damper(M_eff)`, lint-grep for direct `maintenance_level_effective` reads outside it.
- **Stuck-window dropout determinism**: pre-roll Poisson dropout ticks at sensor-factory construction time, not per-tick sampling.
- **Print outcome tie-breakers**: strict `<` everywhere, frozen in a table-driven test.
- **Per-commit green-ness**: components 5–10 each return `prev_self` until that commit lands, so the rest of the engine compiles + tests pass at every step.
- **Integration test runtime**: use `executemany` + transaction batching every 50 ticks to keep the 5-year run under 5 seconds.
- **Sensor self-observation**: the `sensor` component reports its own true `bias_c` as the observed value (no meta-sensor on the sensor). Documented in `sensors/factories.py`.
- **Driver coverage**: each component exercises all four drivers per the matrix above; verified by `engine/test_driver_coverage.py`.
- **Failure analysis**: `copilot-sim inspect <run_id> --failure-analysis` produces a deterministic per-component report so the team can answer "when and why did each component fail" without eyeballing charts.

## Submission deliverables (parallel docs workstream)

The brief mandates four deliverables beyond the working sim. These are split across **Track B (skeletons, parallel with implementation)** and **Track C (results, after first verified runs)** in the commit plan below — *not* a single commit each at the end.

- **README setup** (Track B1) — repo-root `README.md` gets a "Build the sim" section: `uv sync`, `uv run pytest`, `uv run copilot-sim run scenarios/barcelona-baseline.yaml`, `uv run streamlit run …`. Plus the team table, the strategic bet, the demo script anchor. Can start after A18 (CLI stable).
- **Technical report** (Track B2 skeleton + C1+C2 results) — `docs/report/technical-report.md` written from the doc-16 outline, sections 1–8 (executive summary, problem & approach, Phase 1 modelling, Phase 2 simulation design, §3.4 observability, AI maintenance agent, challenges & solutions, evaluation against pillars). Sections 1–5 (modelling/architecture) drafted from research docs in B2, sections 6–8 (results, evaluation) filled from real runs in C1/C2. Pandoc-export to PDF as the final D1 bundling step.
- **Architecture deck** (Track B3 skeleton + C3 results) — `docs/report/deck.md` (markdown source) + a `make deck` target that exports to PDF/PPTX via Pandoc / Marp. Nine slides per doc 16: Title, Mission, Phase 1 brain, Phase 1 cascade + AI surrogate, Phase 2 clock + historian, §3.4 sensor-fault story, Maintenance A/B, Barcelona vs Phoenix what-if, Closing. Slides 1–6 structure can be drafted in B3 from the research; chart screenshots and concrete numbers land in C3 after the dashboard is up.
- **Demo script + walkthrough** (Track B4 skeleton + C4 numbers + C5 video) — `docs/report/demo-script.md` with the 5-minute minute-by-minute split (Daniel, Chris, Jana, Leonie, criisshg). B4 captures the rough flow; C4 fills in exact run IDs and chart timestamps; C5 is the Saturday-evening Loom recording (with fallback to screen-recorded CLI output + matplotlib PNGs if the dashboard isn't ready).

**Anti-fabrication rule**: skeleton commits (B-track) must mark missing data with explicit placeholders (`<TODO: blade fails at week N>`, `<chart pending>`). No prose may claim a number that isn't yet measured. C-track commits replace placeholders with real values pulled from the historian or `inspect --failure-analysis` output.

## Critical files to modify / create

- `sim/src/copilot_sim/engine/{aging,coupling,assembly,engine}.py`
- `sim/src/copilot_sim/components/{registry,blade,rail,nozzle,cleaning,heater,sensor}.py`
- `sim/src/copilot_sim/sensors/{model,factories}.py`
- `sim/src/copilot_sim/drivers_src/{environment,generators,chaos,assembly}.py`
- `sim/src/copilot_sim/historian/{schema.sql,connection,writer,reader,run_id}.py`
- `sim/src/copilot_sim/policy/heuristic.py`
- `sim/src/copilot_sim/simulation/{scenarios,bootstrap,loop}.py`
- `sim/src/copilot_sim/cli.py`
- `sim/src/copilot_sim/dashboard/streamlit_app.py`
- `sim/scenarios/{barcelona-baseline,phoenix-aggressive,chaos-stress-test}.yaml`
- `sim/tests/components/test_{blade,rail,nozzle,cleaning,heater,sensor}_smoke.py`
- `sim/tests/engine/{test_coupling,test_engine_step,test_driver_coverage,test_rng_determinism}.py`
- `sim/tests/simulation/test_full_run.py`

## Reusable existing code

- `sim/src/copilot_sim/domain/` — all dataclasses (`Drivers`, `CouplingContext`, `ComponentState`, `PrinterState`, `ObservedComponentState`, `ObservedPrinterState`, `MaintenanceAction`, `OperatorEvent`) and enums (`OperationalStatus`, `PrintOutcome`, `Severity`, `OperatorEventKind`).
- `sim/pyproject.toml` — all required deps already locked; no new dependencies needed.
- `references/` submodules — vendored upstream source for Streamlit, scikit-learn, httpx, pydantic to read while implementing.

## Verification

```bash
# 1. Per-package green
cd sim
uv run pytest                          # all unit + integration smoke tests pass
uv run ruff check .                    # lint clean
uv run ruff format --check .           # format clean
uv run ty                              # type check clean

# 2. Run a scenario end-to-end
uv run copilot-sim run scenarios/barcelona-baseline.yaml
# expected: writes data/historian.sqlite, prints final tick summary,
# at least one component should have visible aging by year 5

# 3. Inspect the historian
uv run copilot-sim inspect <run_id>
# expected: prints final per-component health + status, total events,
# print_outcome distribution

# 3a. Deterministic failure analysis (Phase 2 self-check answer)
uv run copilot-sim inspect <run_id> --failure-analysis
# expected: per-component report listing first DEGRADED tick, first
# CRITICAL tick, first FAILED tick (or "never"), top three coupling
# factors at each transition (read from coupling_factors_json),
# any chaos events that fired in the lead-up window.
# This is the programmatic answer to "when and why did each component fail".

# 4. Run all three scenarios
uv run copilot-sim run scenarios/barcelona-baseline.yaml
uv run copilot-sim run scenarios/phoenix-aggressive.yaml
uv run copilot-sim run scenarios/chaos-stress-test.yaml
# expected: three distinct run_ids in the historian, each with different
# failure trajectories

# 5. Open the dashboard
uv run streamlit run src/copilot_sim/dashboard/streamlit_app.py
# expected: scenario selector, six charts populated from the historian,
# true-vs-observed toggle works on the sensor-fault story panel

# 6. Demo dry-run
# Eye-test the chart shapes against the expected narratives:
# - barcelona-baseline: smooth sawtooth, clear long-term Weibull drift
# - phoenix-aggressive: heater fails first, sensor follows, dramatic
# - chaos-stress-test: visible chaos events on driver curves, cascading
#   into component health curves with attribution traceable through
#   coupling_factors_json
```

If any of step 2–6 don't show the expected behaviour, the calibration is the lever — adjust per-component `base_rate` constants, Weibull η scaling, and chaos rates in the scenario YAMLs without changing engine code.

### Submission readiness check (final gate before pushing the demo)

```bash
# 7. Submission deliverables present
ls docs/report/{technical-report.md,deck.md,demo-script.md}
# expected: all three files exist, non-empty

# 8. README setup section is current
grep -A3 "## Build the sim" README.md
# expected: contains uv sync + copilot-sim run instructions

# 9. Walkthrough video recorded (Saturday evening fallback)
ls docs/report/walkthrough.mp4 2>/dev/null || echo "no Loom yet — record before Sun 08:00 CEST"

# 10. Submission package compiled
make submission   # bundles deck PDF + report PDF + repo URL + video link
```

The brief expects all of these in the Devpost submission by 09:15 CEST Sunday 2026-04-26.
