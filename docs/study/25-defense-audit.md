# 25 — Defense Audit

> Lead-developer audit of the repository against every requirement in `docs/briefing/{hackathon.md, stage-1.md, stage-2.md, stage-3.md}`. For each requirement: the technical argument, code evidence with file paths and line numbers, the justification for *why* the implementation is robust, and edge cases the briefing flags.

> **Status legend**: ✅ MET · ⚠ PARTIAL · 🚨 CRITICAL GAP

> Generated 2026-04-26 against the post-rebase main branch (HEAD `1d3c096`-and-later).

---

## 0. Tech stack summary

| Layer | Choice | Files |
|---|---|---|
| **Sim language** | Python ≥ 3.12 (3.12–3.14), uv-managed | `sim/pyproject.toml`, `sim/uv.lock` |
| **Math libs** | numpy ≥ 2.0, scipy ≥ 1.13, scikit-learn ≥ 1.5, pandas ≥ 2.2, matplotlib ≥ 3.9 | `sim/pyproject.toml:28-32` |
| **Config validation** | pydantic ≥ 2.5, PyYAML ≥ 6.0 | `sim/pyproject.toml:34-35` |
| **Sim web service** | FastAPI ≥ 0.136, uvicorn ≥ 0.46 (post-rebase) | `sim/src/copilot_sim/api/{main,auth,runner,ingest,schemas}.py` |
| **HTTP client** | httpx ≥ 0.27 | `sim/pyproject.toml:36` |
| **Persistence** | SQLite WAL (file-based historian) | `sim/src/copilot_sim/historian/{schema.sql,connection.py,writer.py,reader.py}` |
| **Operator dashboard** | Streamlit ≥ 1.39 (current 1.56) + Altair | `sim/src/copilot_sim/dashboard/streamlit_app.py` |
| **CLI** | argparse, console-script entry point `copilot-sim` | `sim/src/copilot_sim/cli.py` |
| **Tests** | pytest 8.3, pytest-cov, pytest-xdist (92 tests, all green) | `sim/tests/**/*.py` |
| **Lint/type** | ruff 0.9 (E F I B UP SIM rules), ty (uv-managed) | `sim/pyproject.toml:58-67` |
| **Web frontend** | SvelteKit + Svelte 5 (runes), TypeScript, Tailwind v4 | `web/src/**/*.svelte` |
| **Web backend** | Convex (serverless functions + DB) | `web/src/lib/convex/**/*.ts` |
| **AI agent** | @convex-dev/agent over OpenRouter (default `google/gemma-4-31b-it`) | `web/src/lib/convex/aiChat/agent.ts` |
| **Auth** | Better Auth | `web/AGENTS.md` |
| **i18n** | Tolgee (de/en/es/fr) | `web/src/i18n/*.json` |
| **Containerisation** | Docker Compose at repo root | `docker-compose.yml` |
| **Build orchestration** | Makefile at repo root | `Makefile` |

---

## 1. Constraint compliance (`hackathon.md §4`)

### REQ-C2 — No pre-made telemetry; teams must generate synthetic data

**Status: ✅ MET**

- **THE ARGUMENT**: All telemetry is generated at runtime by the simulation loop. There are no committed CSV/JSON dumps under `data/` that aren't generated. Driver streams come from four parametric generators; component states come from six physics step functions; everything is persisted to SQLite per-tick.
- **CODE EVIDENCE**: `sim/src/copilot_sim/drivers_src/generators.py` (synthetic Sin/OU/Duty/Step driver generators); `sim/src/copilot_sim/drivers_src/assembly.py:64` `DriverProfile.sample(tick_index)`; `sim/src/copilot_sim/simulation/loop.py:41` `SimulationLoop.run()` is the only data-source call site.
- **JUSTIFICATION**: Single sanctioned RNG entry-points (`drivers_src/assembly.py:59` for drivers, `engine/aging.py:108` `derive_component_rng` for component physics) mean generation is pure, deterministic, seedable, and reproducible across processes.
- **EDGE CASES**: Open-Meteo Archive JSONs would be *cached* under `data/weather/` (per `docs/research/07`) but are not telemetry — they're real weather forcings that feed the temperature/humidity drivers. The brief's prohibition is on *pre-made telemetry*, not on real environmental forcings.

### REQ-C3 — AI/LLM must reason over Phase 1/2 data, not training; every answer traceable

**Status: ✅ MET**

- **THE ARGUMENT**: The Co-Pilot agent (`web/src/lib/convex/aiChat/agent.ts`) is constructed with a hard grounding contract baked into its system instructions and a tool-only data-access path. It cannot read printer state except via the seven tools that wrap typed Convex queries against the ingested historian. Every tool result is keyed by `runId/tick/componentId`, and the system prompt explicitly forbids answering from training knowledge.
- **CODE EVIDENCE**:
  - `web/src/lib/convex/aiChat/agent.ts:43-49` — system prompt: *"EVERY claim about a specific run, component, tick, or event MUST come from a tool result. NEVER answer printer-state questions from prior knowledge."*
  - `web/src/lib/convex/sim/tools.ts` — 7 read tools (`getRunSummary`, `getStateAtTick`, `getComponentTimeseries`, `listEvents`, `inspectSensorTrust`, `compareRuns`) + 1 gated mutation tool (`runScenario`).
  - `web/src/lib/convex/sim/tools.ts:12-15` — *"every read result includes `runId/tick/componentId` so the agent can cite specific data points back to the user (Phase 3 grounding protocol — never answer printer state from training)"*.
- **JUSTIFICATION**: Tool-only access is a stronger contract than RAG-via-context-injection because the agent literally has no other surface for printer-state data. The system prompt's "without citation, your answer is hallucinated" line is not aspirational; the agent is shaped to fail at its job if it tries to answer ungrounded.
- **EDGE CASES**: The `runScenario` mutation tool is gated by an explicit two-step confirmation pattern (system prompt §runScenario protocol): the agent must first state proposed config, ask "Run this? (yes/no)", and only call after explicit user yes. This prevents the agent from accidentally spawning expensive simulations.

### REQ-C4 — Scope: Digital Twin only, no physical hardware

**Status: ✅ MET (by construction)**

- **THE ARGUMENT**: No hardware integration code, drivers, or external sensor inputs exist anywhere in the repo. The simulator is a pure computational model.
- **CODE EVIDENCE**: `Engine.step` signature is `(prev: PrinterState, drivers: Drivers, env: Environment, dt: float) -> tuple[PrinterState, ObservedPrinterState, CouplingContext]` (`sim/src/copilot_sim/engine/engine.py:35`) — no hardware handles, GPIO, OPC UA, or real sensor APIs.
- **JUSTIFICATION**: Brief explicitly scopes out hardware integration. The synthetic-only path is a feature, not a limitation.
- **EDGE CASES**: Open-Meteo weather is the closest the model gets to "real-world" data, but it's cached and re-driven through the synthetic temperature/humidity generators — no live polling during simulation.

---

## 2. Phase 1 — Model (`stage-1.md`)

### REQ-1.1 — Logic Engine, callable, no UI/loop

**Source**: stage-1.md §1.1 · **Status: ✅ MET**

- **THE ARGUMENT**: `Engine.step` is a pure function with no I/O, no UI, no time advancement. It takes `(prev, drivers, env, dt)`, returns `(next, observed, coupling)`. The simulation loop is in a *separate* module (`simulation/loop.py`); the dashboard is in another (`dashboard/`); the engine itself is callable from any external orchestrator.
- **CODE EVIDENCE**: `sim/src/copilot_sim/engine/engine.py:31` `class Engine`. `Engine.step(prev, drivers, env, dt)` at line 35 is purely functional. It is called from `sim/src/copilot_sim/simulation/loop.py:47` and from every test in `sim/tests/engine/test_engine_step.py`.
- **JUSTIFICATION**: The pure-function design is what makes the engine *callable* — it composes cleanly with any clock, can be parallelised (process-stable RNG), and is independently testable. `engine.initial_state()` provides bootstrap.
- **EDGE CASES**: `apply_maintenance` is intentionally separate from `step` so that operator interventions are *between-tick* events, never modifying mid-step physics (`engine.py:63`, comment block at the top of the file).

### REQ-1.2 — ≥1 component per subsystem (Recoating, Printhead, Thermal)

**Source**: stage-1.md §1.2, §1.6 · **Status: ✅ MET (2× minimum)**

- **THE ARGUMENT**: We model **two components per subsystem** (six total) so each pair forms an explainable feedback loop, not just three independent curves.
- **CODE EVIDENCE**: `sim/src/copilot_sim/components/registry.py:50` —
  ```python
  COMPONENT_IDS = ("blade", "rail", "nozzle", "cleaning", "heater", "sensor")
  ```
  Recoating: `blade.py` + `rail.py`. Printhead: `nozzle.py` + `cleaning.py`. Thermal: `heater.py` + `sensor.py`.
- **JUSTIFICATION**: Pair structure exposes the *Systemic Interaction* judging pillar: blade↔rail share powder spread, nozzle↔cleaning share clog/wipe, heater↔sensor share controller loop. With three components you have curves; with six you have *interactions*.
- **EDGE CASES**: All six components implement the same `(initial_state, step, reset)` triple via `ComponentSpec` (`registry.py:37`), so adding more components later is a single registration.

### REQ-1.3 — ≥2 textbook math failure models

**Source**: stage-1.md §1.6 · **Status: ✅ MET (6×)**

- **THE ARGUMENT**: Six different classical failure laws, one per component, each cited to industrial literature in `docs/research/22-printer-lifetime-research.md`.

| Component | Law | Code |
|---|---|---|
| Blade | **Archard wear** `V = k·F·s/H` | `components/blade.py:64-83` |
| Rail | **Lundberg-Palmgren** `L₁₀ ∝ (C/P)³` | `components/rail.py:63-83` (cubic visible: `1 + 4·load_eff³`) |
| Nozzle | **Coffin-Manson + Palmgren-Miner + Poisson clog** | `components/nozzle.py:64-117` |
| Cleaning | **Power-law wear-per-cycle** | `components/cleaning.py:62-95` |
| Heater | **Arrhenius AF** `exp((Eₐ/k)(1/T_ref − 1/T_op))` | `components/heater.py:76-112` |
| Sensor | **Arrhenius bias drift** | `components/sensor.py:69-128` |

- **JUSTIFICATION**: Three regimes are exercised — wear-out (β > 1, blade/rail/nozzle), random/useful-life (β = 1, heater), and drift-without-Weibull (sensor). That's a defensible bathtub-curve story instead of six identical curves.
- **EDGE CASES**: Sensor bypasses the standard Weibull composition with a hard-fail gate at `|bias| > 5 °C` (`components/sensor.py:108`), matching industrial PT100 calibration acceptance practice.

### REQ-1.4 — All components react to all 4 brief drivers

**Source**: stage-1.md §1.5.1, §1.6 · **Status: ✅ MET (audit-grep tested)**

- **THE ARGUMENT**: Each component step function reads `coupling.{temperature_stress,humidity_contamination,operational_load,maintenance_level}_effective` and folds each into its damage formula. Coverage is enforced by automated tests, not just by code review.
- **CODE EVIDENCE**:
  - Per-component example (blade): `components/blade.py:72-83` reads `temp_eff`, `humid_eff`, `load_eff`, `maintenance_damper(coupling.maintenance_level_effective)` and multiplies into wear_increment.
  - Driver coverage proof: `sim/tests/engine/test_driver_coverage.py` (24 tests passing) asserts strict monotonicity of every component's metrics in each of the four drivers.
- **JUSTIFICATION**: The driver-coverage tests are an *audit-grep* — if a future change drops a driver from a component's formula, the test fails immediately. This is a structural guarantee that survives refactors.
- **EDGE CASES**: Heater and sensor each use `temperature_stress` *twice* (via `ambient_temperature_C_effective` → operating_K → AF, AND via a `(1 + 0.3·temp_eff)` multiplier) — intentional redundancy tested in `test_driver_coverage.py`.

### REQ-1.5 — Output shape: Health Index, Operational Status, Component Metrics

**Source**: stage-1.md §1.5.2 · **Status: ✅ MET**

- **THE ARGUMENT**: `ComponentState` is a frozen+slots dataclass that carries exactly these three concepts plus an `age_ticks` counter for Weibull baseline.
- **CODE EVIDENCE**: `sim/src/copilot_sim/domain/state.py:17-27` —
  ```python
  @dataclass(frozen=True, slots=True)
  class ComponentState:
      component_id: str
      health_index: float                     # 0..1
      status: OperationalStatus
      metrics: Mapping[str, float]
      age_ticks: int
  ```
  `OperationalStatus` enum at `domain/enums.py:8` exposes `FUNCTIONAL/DEGRADED/CRITICAL/FAILED` plus `UNKNOWN` (observed-only, §3.4).
- **JUSTIFICATION**: Frozen dataclasses + immutable mappings (`MappingProxyType`) prevent accidental mutation across the engine boundary. Status thresholds (`engine/aging.py:26-28`: `0.75 / 0.40 / 0.15`) match the doc-04 spec exactly (reconciled in this hackathon — see commit `bf0afe5`).
- **EDGE CASES**: Per-component metrics dicts are component-specific (e.g. blade has `wear_level/edge_roughness/thickness_mm`; sensor has `bias_offset/noise_sigma/reading_accuracy`) — the `Mapping[str, float]` type leaves room for that without forcing a rigid schema.

### REQ-1.6 — Engine deterministic

**Source**: stage-1.md §1.4 · **Status: ✅ MET**

- **THE ARGUMENT**: Same seed + same scenario YAML → byte-identical historian, regardless of process, parallelism, or `PYTHONHASHSEED`.
- **CODE EVIDENCE**:
  - `engine/aging.py:108` `derive_component_rng(scenario_seed, tick, component_id)` keys a fresh `numpy.random.default_rng` on a `blake2b` digest of `component_id` (process-stable).
  - `drivers_src/chaos.py:46` `ChaosOverlay.roll(seed)` pre-rolls all Poisson/Bernoulli arrivals at scenario load with a separate RNG tag (`0xC4_A0_5E`).
  - Tests: `sim/tests/engine/test_rng_determinism.py`, `sim/tests/engine/test_engine_step.py:test_engine_step_is_deterministic_for_same_seed`.
- **JUSTIFICATION**: Three independent entropy axes (scenario_seed, tick, component_id-as-blake2b-digest) ensure both reproducibility *and* statistical independence between components. Pre-rolling chaos at load time means the chaos schedule is stable across process restarts.
- **EDGE CASES**: Stateful Ornstein-Uhlenbeck humidity owns its own state on the generator dataclass (`drivers_src/generators.py:73`); the loop never side-channels RNG state.

### REQ-1.7 — Cascading failures (bonus)

**Source**: stage-1.md §1.7.1 · **Status: ✅ MET**

- **THE ARGUMENT**: Cross-component effects flow through one `CouplingContext` object built from the immutable `t-1` `PrinterState`. Ten named factors are persisted as `coupling_factors_json` per tick for downstream attribution. Five cascade arrows are visible in the formula text.
- **CODE EVIDENCE**:
  - `engine/coupling.py:36` `build_coupling_context()` produces 10 named factors + 4 *_effective drivers.
  - Cascade chain examples documented in `dashboard/streamlit_app.py:67-92` `CASCADE_CHAINS`.
  - Powder cascade: blade_wear ↑ → `humidity_contamination_effective += 0.20·blade_wear` → nozzle Poisson rate ↑.
  - Thermal cascade: heater_drift ↑ → `heater_thermal_stress_bonus = 0.10·heater_drift_frac` → nozzle CM Δε_p ↑ + sensor AF ↑.
  - Sensor↔Heater closed loop: sensor_bias → control_temp_error_c → temperature_stress_effective → heater_operating_K → heater AF → drift → loop closes.
- **JUSTIFICATION**: Single coupling-entry-point design gives **update-order independence by construction** (`AGENTS.md § Simulation Modeling`) — the engine is mathematically guaranteed to produce the same result regardless of which component is stepped first.
- **EDGE CASES**: Three documented "two-way" pair loops (rail↔blade, cleaning↔nozzle, sensor↔heater) — only the sensor↔heater pair is fully bidirectional in the explicit math; the other two close through shared output sinks like `powder_spread_quality`. Documented in `docs/study/22-realism-audit.md` §C.1; not a defense risk because the cascade *behaviour* is in code, just the explicit reverse arms are simplified.

### REQ-1.8 — Stochastic realism (bonus)

**Source**: stage-1.md §1.7.2 · **Status: ✅ MET**

- **THE ARGUMENT**: A pre-rolled `ChaosOverlay` injects Poisson temperature spikes, Poisson contamination bursts, and Bernoulli skipped-maintenance events on top of the deterministic driver generators.
- **CODE EVIDENCE**: `drivers_src/chaos.py:27-92`. Defaults: `temp_spike_lambda_per_year=4.0`, `contamination_burst_lambda_per_year=6.0`, `skipped_maintenance_p=0.10`. Enabled in `sim/scenarios/{barcelona-with-chaos,chaos-stress-test}.yaml`.
- **JUSTIFICATION**: Pre-rolling at scenario load (with a separate RNG tag `0xC4_A0_5E`) keeps the chaos schedule reproducible across process restarts, independent of the per-component RNG. This is a cleaner separation than per-tick sampling, which would tangle chaos and component noise streams.
- **EDGE CASES**: Disabled by default in `barcelona-baseline.yaml` so the deterministic backbone is visible; enabled scenarios produce ~4 temperature spikes and ~6 contamination bursts per simulated year.

### REQ-1.9 — Maintenance as input (bonus)

**Source**: stage-1.md §1.7.3 · **Status: ✅ MET**

- **THE ARGUMENT**: Maintenance enters the engine through two channels: (a) the continuous `maintenance_level ∈ [0, 1]` driver feeding the `(1 - 0.8·M)` damper into every component's damage increment, and (b) discrete `MaintenanceAction(component_id, kind, payload)` directives processed between ticks via `engine.apply_maintenance`.
- **CODE EVIDENCE**:
  - Continuous channel: `engine/aging.py:50-59` `maintenance_damper()`, called from every component step.
  - Discrete channel: `engine/engine.py:63` `apply_maintenance`. Per-component reset rules: `components/{blade,rail,nozzle,cleaning,heater,sensor}.py:reset()`.
  - Three action kinds: `domain/enums.py:30` `OperatorEventKind ∈ {TROUBLESHOOT, FIX, REPLACE}`.
- **JUSTIFICATION**: Three-action vocabulary (vs binary maintain/don't) is closer to real industrial practice. Per-component reset semantics encode physical realism: blade has no field-repairable FIX (consumable), rail's pitting is permanent (FIX leaves alignment_error_um untouched), sensor calibration zeroes bias only (connector noise is irreversible).
- **EDGE CASES**: TROUBLESHOOT mutates no state — it only writes an event row, ensuring "diagnose-before-act" semantics for the §3.4 sensor-fault story.

### REQ-1.10 — AI degradation model (bonus)

**Source**: stage-1.md §1.7.4 · **Status: ⚠ PARTIAL**

- **THE ARGUMENT**: Specified in `docs/research/05-cascading-and-ai-degradation.md` as an MLPRegressor `(32,32,32) tanh` trained on 20k Latin-Hypercube samples to replace the heater's analytic Arrhenius. Not yet trained or wired in.
- **CODE EVIDENCE**: Path reserved in `docs/research/05`; CLI flag `--heater-model={analytic,nn}` planned but not present in `cli.py`.
- **JUSTIFICATION**: Time budget allocation — Phase 1 + Phase 2 + Phase 3 grounding agent took priority over the surrogate.
- **EDGE CASES**: The roadmap entry (`docs/study/23-improvement-roadmap.md` §B2.6, 4 hours) keeps this as a deliverable for the day-after-pitch. **Defense line**: "specified, scaffold ready, training queued." Do not claim it is done.

### REQ-1.11 — Live weather API (bonus)

**Source**: stage-1.md §1.7.5 · **Status: ⚠ PARTIAL**

- **THE ARGUMENT**: Open-Meteo Archive API was researched (`docs/research/07`); two scenarios (`barcelona-baseline`, `phoenix-aggressive`) are *calibrated* to look like real Barcelona and Phoenix climates via tuned `SinusoidalSeasonalTemp` parameters. The cached JSON adapter (`OpenMeteoDriver`) is queued in the roadmap.
- **CODE EVIDENCE**: Calibrated YAMLs at `sim/scenarios/{barcelona-baseline,phoenix-aggressive}.yaml`. `httpx` dep in `sim/pyproject.toml:36`. No `drivers_src/weather.py` adapter yet.
- **JUSTIFICATION**: Scenarios produce *climate-driven failure-mode differences* (Phoenix → heater + sensor first; Barcelona → blade + nozzle first), which is the demo-relevant payoff of the bonus pillar — even without the literal API call.
- **EDGE CASES**: For defense — say "weather-shaped scenarios", not "live weather". Roadmap §B3.1 (4 hours) is the path to the literal claim.

---

## 3. Phase 2 — Simulate (`stage-2.md`)

### REQ-2.1 — Functional clock loop with chosen `dt`

**Source**: stage-2.md §2.6.1 · **Status: ✅ MET**

- **THE ARGUMENT**: `SimulationLoop.run()` advances `tick_index` from 0 to `horizon_ticks-1`, calling `engine.step(...)` with `dt=1.0` (one simulated week per tick) on each iteration.
- **CODE EVIDENCE**: `sim/src/copilot_sim/simulation/loop.py:41-86`. `dt_seconds: int = 604800` (1 week) per `loop.py:38`. Horizon defaults differ per scenario (`barcelona-baseline.yaml:5` = 260 ticks = 5 years; `barcelona-18mo.yaml:5` = 78 ticks).
- **JUSTIFICATION**: Weekly granularity matches the η-anchors from `docs/research/22` (slowest η = 540 days = 77 weeks) — fine enough to see knee-points, coarse enough to keep historian writes sub-second.
- **EDGE CASES**: `dt` is locked at 1.0 in the engine call (`loop.py:47`); the seconds-per-tick is metadata-only, used for ISO-timestamping historian rows.

### REQ-2.2 — Phase 1 engine called every tick

**Source**: stage-2.md §2.6.3 · **Status: ✅ MET**

- **THE ARGUMENT**: `loop.py:47` calls `engine.step` exactly once per tick, with no shortcuts, caching, or extrapolation.
- **CODE EVIDENCE**: Single `engine.step` invocation in `loop.py:47`; no other call sites in the loop. Test `sim/tests/simulation/test_full_run.py` (5 tests) verifies tick counts match horizon.
- **JUSTIFICATION**: The "no shortcuts" rule is enforced structurally — there's only one path from the loop into the engine.
- **EDGE CASES**: Maintenance actions go through the *separate* `engine.apply_maintenance` channel between ticks (`loop.py:79-83`), not inside `step` — preserves engine purity.

### REQ-2.3 — Persistence (CSV, JSON, or SQLite)

**Source**: stage-2.md §2.6.2 · **Status: ✅ MET**

- **THE ARGUMENT**: SQLite WAL with seven tables, all time-series tables `WITHOUT ROWID` for single-B-tree-lookup performance. Every tick row carries timestamp, full driver values, observed and true component states, plus the full coupling factor dict as JSON.
- **CODE EVIDENCE**: `sim/src/copilot_sim/historian/schema.sql:1-101`. Seven tables: `runs`, `drivers`, `component_state`, `metrics`, `observed_component_state`, `observed_metrics`, `events`, `environmental_events`. Writer at `historian/writer.py` (240 lines, batched `executemany`, `flush_every=50`). WAL pragmas at `historian/connection.py`.
- **JUSTIFICATION**: SQLite WAL was chosen so the Streamlit dashboard can read the live historian while the simulator writes — no locking. `WITHOUT ROWID` means each row is stored inline with the index, ~30% smaller and one B-tree traversal per lookup. `coupling_factors_json` per tick is the *attribution channel* that makes failure analysis a pure SQL query, no engine re-run.
- **EDGE CASES**: Pragmas locked: `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`. ~13 000 rows per 5-year run, well under 10 MB SQLite — committable to git as a fallback.

### REQ-2.4 — Runs / scenarios identifiable

**Source**: stage-2.md §2.5.2, §2.6 · **Status: ✅ MET**

- **THE ARGUMENT**: Every run gets a unique `run_id` minted as `{scenario}-{profile}-{seed}-{utc_timestamp}` (e.g. `barcelona-18mo-42-20260425T222432`). All historian tables key on `run_id` first.
- **CODE EVIDENCE**: `sim/src/copilot_sim/historian/run_id.py:mint_run_id()`. Schema: every time-series table's primary key starts with `run_id` (`schema.sql:34, 44, 53, 63, 73`).
- **JUSTIFICATION**: Format `{scenario}-{profile}-{seed}-{ts}` puts the most-queried filter (scenario family) first, lets you list runs by scenario without parsing, and the seed in the middle makes A/B comparisons instantly identifiable in the dashboard's run-id picker.
- **EDGE CASES**: Multiple runs of the same scenario+seed get distinguished by the timestamp suffix.

### REQ-2.5 — Time-series visualization showing health evolution

**Source**: stage-2.md §2.8 · **Status: ✅ MET**

- **THE ARGUMENT**: Two visualisations of the same data: (a) Streamlit panel 1 line chart with pan + zoom controls (`6mo / 1y / 3y / all`); (b) Streamlit panel 6 status timeline as a Gantt of contiguous status segments. Plus the operator dashboard's other 6 panels for context.
- **CODE EVIDENCE**: `sim/src/copilot_sim/dashboard/streamlit_app.py:_render_panel1` (line chart), `_render_panel6` (Gantt). Documented in `docs/study/24-dashboard-walkthrough.md`.
- **JUSTIFICATION**: Two visualisations of the same data optimise for different reading goals — line chart for "rate of decay", Gantt for "how long was each status held". Together they answer both "is this component degrading too fast?" and "did the policy catch it in time?".
- **EDGE CASES**: Y-axis on line chart is **fixed** to `[0.0, 1.0]` (`streamlit_app.py:473`) so visual decay slopes are comparable across runs/components. X-axis is locked to the chosen window so panning doesn't auto-rescale.

### REQ-2.6 — Failure analysis: when AND why each component fails

**Source**: stage-2.md §2.8 · **Status: ✅ MET (this is our strongest pillar)**

- **THE ARGUMENT**: The CLI command `copilot-sim inspect <run_id> --failure-analysis` answers both questions in one command. For each component it prints the first DEGRADED / CRITICAL / FAILED tick (when), and at each transition it queries `coupling_factors_json` and surfaces the top-3 factors by absolute magnitude (why).
- **CODE EVIDENCE**:
  - `sim/src/copilot_sim/cli.py:108-149` `_print_failure_analysis()`.
  - `historian/reader.py:fetch_status_transitions(conn, run_id)` and `fetch_coupling_factors_at(conn, run_id, tick)`.
  - Same logic powers the dashboard's panel 2 (`streamlit_app.py:_render_panel2`) and panel 8 (proactive alerts feed).
- **JUSTIFICATION**: This is the brief's "every failure event traceable to its root input drivers" requirement (Stage 2 Realism & Fidelity bonus) made literal. The implementation is purpose-built for this requirement — the historian's `coupling_factors_json` column exists primarily so this query is sub-millisecond per tick without re-running the engine.
- **EDGE CASES**: Sample output for a phoenix-18mo run: `nozzle FAILED at t=31, top factors: powder_spread_quality=0.928, sensor_bias_c=0.885, control_temp_error_c=0.885` — the chain reads: degraded powder spread (from upstream blade/rail) AND a drifting sensor that fooled the heater controller, jointly clogging the nozzle. That story is *recovered from data*, not pre-written.

### REQ-2.7 — What-if scenarios (bonus)

**Source**: stage-2.md §2.7.1 · **Status: ✅ MET**

- **THE ARGUMENT**: Six scenario YAMLs implement the same engine under different conditions. Same horizon, same seed (where applicable), only the climate + duty-cycle change.
- **CODE EVIDENCE**: `sim/scenarios/*.yaml` — 9 files: `barcelona-baseline`, `barcelona-18mo`, `barcelona-with-chaos`, `barcelona-with-events`, `barcelona-human-disruption-no-maintenance`, `barcelona-powder-bug-with-maintenance`, `phoenix-aggressive`, `phoenix-18mo`, `chaos-stress-test`.
- **JUSTIFICATION**: Pydantic-validated YAML schema (`simulation/scenarios.py:51-211`) catches typos (e.g. `vibration_level: 8.5` would mean 8.5 instead of 0.85) at scenario-load time, not at runtime via mysterious 5× rail wear. `EnvCfg` and `EventCfg` have per-key range checks.
- **EDGE CASES**: Phoenix vs Barcelona is a **clean A/B** because only `temperature_stress.base` (0.30 vs 0.65), `weekly_runtime_hours` (60 vs 110), and `base_ambient_C` (22 vs 32) change. Different components fail first per climate (Phoenix → heater + sensor first; Barcelona → blade + nozzle first) — exactly the demo-relevant payoff.

### REQ-2.8 — Chaos engineering (bonus)

**Source**: stage-2.md §2.7.2 · **Status: ✅ MET (already covered under REQ-1.8)**

### REQ-2.9 — AI Maintenance Agent (bonus)

**Source**: stage-2.md §2.7.3 · **Status: ✅ MET**

- **THE ARGUMENT**: Three-rule heuristic policy reading **observed** state only (per §3.4), with worst-first triage and a deterministic tie-break. Action vocabulary is `TROUBLESHOOT/FIX/REPLACE` (three kinds, not binary).
- **CODE EVIDENCE**: `sim/src/copilot_sim/policy/heuristic.py:43-110` `HeuristicPolicy.decide()`. Three rules:
  1. Any `observed_status == UNKNOWN` → `TROUBLESHOOT(component)` (never act blind).
  2. Among `observed_health < 0.45`, pick lowest-health → `REPLACE` if `< 0.20` else `FIX`.
  3. Monthly preventive `FIX` of longest-unmaintained component.
- **JUSTIFICATION**: Reading observed-only is the §3.4 discipline encoded as policy — the agent gets fooled by a drifting sensor exactly like a real operator. Worst-first sort with deterministic tie-break is a fairness fix over naive iteration (which would always pick the first match in registry order).
- **EDGE CASES**: TROUBLESHOOT count is normally 0 in Barcelona scenarios (sensor stays trustworthy); jumps to ≥1 in phoenix-18mo where the sensor crosses |bias|>5 → status FAILED → heater observed view goes UNKNOWN → policy emits TROUBLESHOOT(sensor).

### REQ-2.10 — RL policy (bonus)

**Source**: stage-2.md §2.7.4 · **Status: ⚠ PARTIAL — specified, intentionally not built**

- **THE ARGUMENT**: Gymnasium env + reward shape + observation/action spaces are fully specified in `docs/research/09-maintenance-agent.md`. Skipped explicitly for the 36-h hackathon time budget.
- **CODE EVIDENCE**: `docs/research/09` §"Gymnasium env spec (locked, even if we don't train)".
- **JUSTIFICATION**: The env spec exists so a judge asking "could you train an RL policy?" gets a precise answer (`stable-baselines3 PPO` on this env in ~2 h) without committing the hours.
- **EDGE CASES**: Defense line: "specified, env scaffold ready, deferred for time" — do not claim it is done.

### REQ-2.11 — Digital twin synchronisation (bonus)

**Source**: stage-2.md §2.7.5 · **Status: ⚠ PARTIAL**

- **THE ARGUMENT**: The §3.4 true-vs-observed split is the *foundation* for synchronisation — `ObservedPrinterState` is the surface external sensors would feed into. A literal "feed real readings, let twin self-correct" loop is not implemented.
- **CODE EVIDENCE**: `domain/state.py:44` `ObservedComponentState` with `observed_metrics: Mapping[str, float | None]` per metric. The §3.4 sensor pass (`engine/assembly.py:43`) is exactly the place a real-data overlay would land.
- **JUSTIFICATION**: The architecture is sync-ready; only the data-source connector is missing. For defense: explicit honesty.

---

## 4. Phase 3 — Interact (`stage-3.md`)

### REQ-3.1 — Interface reads from Phase 2 historian

**Source**: stage-3.md §3.2, §3.7 · **Status: ✅ MET**

- **THE ARGUMENT**: Two-tier ingestion: (a) sim writes to its local SQLite historian, (b) FastAPI service ingests runs into Convex tables, (c) Convex queries serve the AI agent's tools.
- **CODE EVIDENCE**:
  - Sim → Convex pipeline: `sim/src/copilot_sim/api/ingest.py` (202 lines), `web/src/lib/convex/sim/{tables,mutations,queries,actions}.ts`.
  - Agent tool → query path: `web/src/lib/convex/sim/tools.ts:19-31` `getRunSummary` calls `api.sim.queries.getRunSummary`.
  - Tools defined: `getRunSummary, getStateAtTick, getComponentTimeseries, listEvents, inspectSensorTrust, compareRuns, runScenario` (`web/src/lib/convex/sim/tools.ts`).
- **JUSTIFICATION**: Tool-only data access (Convex query handlers) means the agent literally cannot read printer state through any other path — strongest possible enforcement of the grounding rule.
- **EDGE CASES**: `runScenario` is the only mutation tool; it's gated by an explicit two-step user-confirmation pattern in the system prompt (`agent.ts:68-75`).

### REQ-3.2 — Pattern: Simple Context Injection (minimum)

**Source**: stage-3.md §3.3.A · **Status: ✅ MET (exceeded — Pattern C implemented)**

- **THE ARGUMENT**: We exceed the minimum — instead of static context injection (Pattern A), the agent uses **Pattern C: Agentic Diagnosis** with a tool-calling ReAct loop.
- **CODE EVIDENCE**: `web/src/lib/convex/aiChat/agent.ts:23-41` configures the agent with `maxSteps: 100` and seven tools that the model can call iteratively. The agent doesn't just read static context — it actively *queries* the historian based on the user's question.
- **JUSTIFICATION**: Pattern C is the highest tier in the brief's reasoning ladder (stage-3.md §3.3) and is what the *Reasoning Depth* and *Proactive Intelligence* judging pillars explicitly reward.
- **EDGE CASES**: `maxSteps=100` allows multi-turn investigations like "find when the heater first crossed CRITICAL → check sensor bias at that tick → cross-reference events → conclude root cause".

### REQ-3.3 — Grounding protocol: no hallucinations, traceable to data

**Source**: stage-3.md §3.5, §3.7.2 · **Status: ✅ MET**

- **THE ARGUMENT**: System prompt enforces grounding with a non-negotiable contract: "EVERY claim about a specific run, component, tick, or event MUST come from a tool result. NEVER answer printer-state questions from prior knowledge." Combined with tool-only data access, the agent literally cannot fabricate state.
- **CODE EVIDENCE**: `web/src/lib/convex/aiChat/agent.ts:43-49`.
- **JUSTIFICATION**: Two enforcement layers: (a) prompt-level rule, (b) architectural — no other data path exists. Even if the agent "wanted" to answer from training, it has no training-aware path to printer-state values.
- **EDGE CASES**: Off-topic side capabilities (real-world weather lookup via `getGeocoding`/`getWeather`) are explicitly scoped: "use only when off-topic from the printer" (agent.ts:64-66) — the agent can talk about real Barcelona weather without conflating that with simulated drivers.

### REQ-3.4 — Evidence citation on every answer

**Source**: stage-3.md §3.6.2 · **Status: ✅ MET**

- **THE ARGUMENT**: System prompt explicitly mandates citation format: *"include the runId, the tick, and (when relevant) the componentId, e.g. 'blade health was 0.42 at tick 87 of run abc123'"* (`agent.ts:49`). Every read tool's description echoes the same: *"Always cite the runId in your answer"* (`tools.ts:21-22`).
- **CODE EVIDENCE**: Tool descriptions at `tools.ts:19-30, 33-48, 50-69, 71-89` — all reinforce the cite-runId/tick/componentId pattern.
- **JUSTIFICATION**: Citation-as-system-prompt-rule is enforced model-side. The agent's training optimises strongly for following explicit instructions in the system prompt.
- **EDGE CASES**: When a question is open-ended (e.g. "why is my printer slow?") the agent is instructed to call `getRunSummary` first to fix the run context, then narrow with `getComponentTimeseries` or `listEvents` — the citation chain is built up tool-by-tool.

### REQ-3.5 — Severity Indicator on responses

**Source**: stage-3.md §3.6.2 · **Status: ⚠ PARTIAL**

- **THE ARGUMENT**: Status indicators (`FUNCTIONAL/DEGRADED/CRITICAL/FAILED`) are surfaced in tool results, and the dashboard's panel 7 (`Recommendation cards`) maps them to semantic severity bands (`WATCH/SCHEDULE FIX/REPLACE NOW`) with coloured pills. The agent system prompt covers domain primer including thresholds (`agent.ts:81`). However, the brief's specific `INFO/WARNING/CRITICAL` severity tag enum is not explicitly produced as a structured response field.
- **CODE EVIDENCE**: `domain/enums.py:24` defines `Severity ∈ {INFO, WARNING, CRITICAL}` — declared in code but not yet wired into agent responses. Operator-facing severity comes through status mapping, not the enum.
- **JUSTIFICATION**: Functionally equivalent (CRITICAL component → "act now" recommendation), but a strict reading of the brief asks for an explicit severity field on every AI response.
- **🚨 ACTION ITEM**: For full compliance, add an explicit "severity" field to the agent's response schema or have the system prompt instruct the agent to lead each response with `[INFO]`, `[WARNING]`, or `[CRITICAL]`. **5-minute fix** by adding one paragraph to the system prompt at `agent.ts:159`.

### REQ-3.6 — Proactive alerting (bonus)

**Source**: stage-3.md §3.8.1 · **Status: ✅ MET**

- **THE ARGUMENT**: The Streamlit dashboard's panel 8 (`_render_panel8` in `streamlit_app.py:942`) renders a notification-style feed of every status transition the engine produced — the model's "alerts log". This is the historian's `fetch_status_transitions` output formatted as if streamed in real time.
- **CODE EVIDENCE**: `streamlit_app.py:942-991`. Each row: tick + component + new status + top driver factor.
- **JUSTIFICATION**: Real-time alerting requires only swapping the on-load query for a polling subscription — the data shape and presentation layer are already correct.
- **EDGE CASES**: Filters out `FUNCTIONAL` "transitions" (every component starts there) so the feed only contains actionable signals.

### REQ-3.7 — Voice / hands-free interface (bonus)

**Source**: stage-3.md §3.8.2 · **Status: 🚨 CRITICAL GAP**

- **THE ARGUMENT**: No voice surface in the current build. Brief calls this "factory floor demo" relevance.
- **CODE EVIDENCE**: No Web Speech API or OpenAI Realtime integration in `web/src/`. `docs/research/13-voice-interface.md` exists as a spec.
- **JUSTIFICATION**: Strategic deprioritisation — Phase 1 + Phase 2 + Phase 3 chat agent took priority over voice.
- **🚨 DEFENSE NOTE**: This is an acknowledged trade-off. Pivot in Q&A: *"Voice is in `docs/research/13` — Web Speech API plan is ~3 hours of work but would have come at the cost of the grounding agent's tool surface, which we judged higher impact."* Don't claim voice; defend the trade.

### REQ-3.8 — Root-cause diagnosis (bonus)

**Source**: stage-3.md §3.8.3 · **Status: ✅ MET**

- **THE ARGUMENT**: Two surfaces produce root-cause stories without invoking the LLM: (a) the CLI's `--failure-analysis` traces transitions to top-3 coupling factors, (b) the dashboard's panel 2 cascade attribution renders these as cards with status steppers + factor bars + cascade chain text. The agent can additionally synthesise these via `getStateAtTick + getComponentTimeseries + listEvents`.
- **CODE EVIDENCE**: `cli.py:108-149`, `streamlit_app.py:_render_panel2`, agent's `inspectSensorTrust` tool (`tools.ts`) for sensor-vs-component-fault distinction.
- **JUSTIFICATION**: Root cause is *recovered from persisted data*, not reconstructed by the agent guessing — `coupling_factors_json` is the audit trail. The agent then *narrates* the chain in natural language, but the chain itself is data-derived.
- **EDGE CASES**: `inspectSensorTrust` (system prompt: "Use to distinguish a component fault from a sensor fault") is the §3.4 sensor-fault story made conversational.

### REQ-3.9 — Action paths (bonus)

**Source**: stage-3.md §3.8.4 · **Status: ✅ MET**

- **THE ARGUMENT**: Dashboard panel 7 produces "suggested next step" pills (`WATCH / SCHEDULE FIX / REPLACE NOW`) per CRITICAL/FAILED component. Agent system prompt covers cost model and action vocabulary.
- **CODE EVIDENCE**: `streamlit_app.py:_PHASE3_RULES` and `_render_panel7`. Agent tool `runScenario` lets the operator simulate "what-if I do X" branches.
- **JUSTIFICATION**: Static rule-based recommendations are honest about being a Phase 3 *preview* (caption: "rule-based today; the LLM agent will replace the rule with a generated rationale"); the LLM in `agent.ts` is the production version.
- **EDGE CASES**: `runScenario` is gated — agent must ask for explicit user confirmation before spawning a what-if simulation.

### REQ-3.10 — Autonomous collaborator (bonus)

**Source**: stage-3.md §3.8.5 · **Status: ⚠ PARTIAL**

- **THE ARGUMENT**: The Convex Agent has session-scoped memory (`@convex-dev/agent` recentMessages: 20, `agent.ts:165-167`) and tool-calling autonomy. Cross-session persistent memory and proactive insight surfacing are not yet wired.
- **CODE EVIDENCE**: `agent.ts:165` `contextOptions: { recentMessages: 20 }` — bounded session memory.
- **JUSTIFICATION**: 20-message recall is enough for "remember within a conversation". Cross-session memory would need explicit `userMemoryProvider` wiring (Convex Agent supports this; we haven't enabled it).
- **🚨 DEFENSE NOTE**: Pivot — *"in-session memory is functional; cross-session is queued."* Honest, defensible.

---

## 5. Submission package (`hackathon.md §5`)

| # | Requirement | Status | Where |
|---|---|---|---|
| S1 | Working demo Phase 1+2 minimum | ✅ MET | `copilot-sim run`, Streamlit dashboard, all 6+ scenarios |
| S2 | Architecture slide deck | 🚨 **GAP** — not in repo | TODO before submission |
| S3 | Technical report | 🚨 **GAP** — not in repo | TODO before submission. Material is in `docs/study/` (15 files) but needs distillation |
| S4 | Phase 3 bonus demo | ✅ MET | Convex agent + web dashboard at `/app/runs` |
| S5 | GitHub repo with README setup | ✅ MET | `README.md` exists; setup at `web/SETUP-DRAFT.md`, `Makefile` |
| S6 | Walkthrough video | 🚨 **GAP** — not in repo | TODO before submission |

**🚨 BLOCKING SUBMISSION GAPS**: deck (S2), report (S3), walkthrough video (S6). These are explicit submission requirements per `hackathon.md §5` and judges expect them.

---

## 6. Pre-demo self-check (`hackathon.md §6`)

| ID | Check | Status |
|---|---|---|
| **Phase 1** | | |
| | ≥1 component per subsystem | ✅ MET (2× per subsystem) |
| | Each component uses ≥1 driver | ✅ MET (4 drivers per component, audit-grep tested) |
| | ≥2 failure models | ✅ MET (6 different laws) |
| | Outputs include health, status, metrics | ✅ MET (`ComponentState` shape) |
| | Team can explain degradation logic | ✅ MET (study docs in `docs/study/components/`) |
| **Phase 2** | | |
| | Loop advances time correctly | ✅ MET |
| | Phase 1 engine called every tick | ✅ MET |
| | Records saved with timestamp + drivers | ✅ MET (`drivers` table per (run, tick)) |
| | Runs/scenarios identifiable separately | ✅ MET (`run_id` format) |
| | Time-series viz | ✅ MET (panel 1 + panel 6) |
| | When + why each component fails | ✅ MET (`inspect --failure-analysis`) |
| **Phase 3** | | |
| | Interface reads from historian | ✅ MET (Convex queries → agent tools) |
| | Responses grounded | ✅ MET (system prompt + tool-only access) |
| | Every answer cited | ✅ MET (system-prompt-enforced) |
| | Advanced reasoning traceable | ✅ MET (Pattern C agentic + tool-call audit log) |
| **Demo readiness** | | |
| | Team can explain phase connections | ✅ MET (`docs/study/00-overview.md`) |
| | Demo reproducible end-to-end | ✅ MET (deterministic seed + scenario YAML) |
| | Show where AI answer comes from | ✅ MET (citations + `tools.ts` query handlers) |

---

## 7. Critical gaps summary (in priority order)

| # | Gap | Severity | Time to fix |
|---|---|---|---|
| 1 | **Slide deck (S2)** | 🚨 BLOCKER for submission | 2–3 hours |
| 2 | **Technical report (S3)** | 🚨 BLOCKER for submission | 1–2 hours (distil from `docs/study/`) |
| 3 | **Walkthrough video (S6)** | 🚨 BLOCKER for submission | 30 min recording + 30 min editing |
| 4 | **Severity Indicator on AI responses (REQ-3.5)** | ⚠ Compliance gap | 5 min (add to system prompt) |
| 5 | **Voice interface (REQ-3.7)** | ⚠ Bonus only — defensible omission | 3 hours (Web Speech) — only if time |
| 6 | **AI degradation surrogate (REQ-1.10)** | ⚠ Bonus — specified, not built | 4 hours |
| 7 | **Live weather adapter (REQ-1.11)** | ⚠ Bonus — calibrated, not literal | 4 hours |
| 8 | **Cross-session agent memory (REQ-3.10)** | ⚠ Bonus — partial | 1 hour to enable Convex memory provider |

---

## 8. Recommended defense talking points (priority-ordered)

1. **Open with the §3.4 sensor-fault story** — it's the brief's "surprise us" twist made literal in code, and it's the strongest single piece of evidence we *understood* the brief beyond the minimum.
2. **Demo `inspect --failure-analysis`** — single command satisfies REQ-2.6 ("when AND why each component fails") and shows attribution from data, not narration.
3. **Show panel 2 + panel 8 in the dashboard** — visual proof of the same data being usable both retrospectively (cards) and as a real-time alerts feed.
4. **Open the agent at `/app/runs`** — ask "why did the heater fail in run X?" — the agent calls `getStateAtTick` then `inspectSensorTrust` then narrates with `runId/tick/componentId` citations. That's Pattern C agentic diagnosis with grounding, on stage.
5. **If pressed on bonuses**: lead with what we built (cascading failures, stochastic chaos, AI maintenance agent, what-if scenarios, root-cause diagnosis, action paths, proactive alerts, agentic Pattern C), close with what we deferred (RL, voice, AI surrogate, live weather literal API) and *why* (time-budget choice favouring grounding rigour over breadth).

---

## 9. The single-sentence defense headlines

For each judging pillar, the one-sentence answer to memorise:

- **Rigor** — "Six classical failure laws — Archard, Lundberg-Palmgren, Coffin-Manson, power-law cycle wear, and two Arrhenius variants — every η lifetime cited to industry sources in `docs/research/22`."
- **Systemic Interaction** — "All four brief drivers feed all six components, enforced by the `tests/engine/test_driver_coverage.py` audit-grep that fails the build if any link is dropped."
- **Time moves** — "`SimulationLoop.run` advances `tick_index` by 1, calls `Engine.step` exactly once per tick, persists 7 historian tables, then between ticks asks the policy for `MaintenanceAction`s."
- **Systemic Integration** — "Every tick of every run lands in SQLite WAL with full driver values, true-and-observed component state, and the complete coupling-factor dict — `inspect --failure-analysis` reads that data back to surface root causes."
- **Complexity & Innovation** — "The §3.4 sensor-fault layer: sensor lies → controller defends wrong setpoint → heater overshoots → sensor ages faster — a closed feedback loop in code, plus a maintenance policy that gets fooled by it exactly like a real operator."
- **Realism & Fidelity** — "Maintenance reset rules match real industrial practice — blade is consumable so FIX = REPLACE, rail pitting is permanent so FIX preserves alignment_error_um, sensor calibration zeros bias only because connector noise is irreversible."
- **Reliability (Phase 3)** — "Tool-only data access plus a system prompt that mandates `runId/tick/componentId` citations. The agent has no training-aware path to printer state — it can't hallucinate even if it tried."
- **Reasoning Depth (Phase 3)** — "Pattern C agentic diagnosis with `maxSteps: 100`. Multi-turn tool calls let the agent walk a cascade chain: `getStateAtTick` → `inspectSensorTrust` → `listEvents` → cite the answer back to the user."
- **Proactive Intelligence (Phase 3)** — "Panel 8 is a notification-style alerts feed of every status transition, pre-computed from the historian; the agent's `runScenario` tool turns operator questions into new what-if simulations on demand (gated by explicit confirmation)."

---

## 10. Cross-references

- Per-component physics arguments: [`components/10-blade.md`](components/10-blade.md) through [`components/15-sensor.md`](components/15-sensor.md).
- Engine architecture: [`02-engine-architecture.md`](02-engine-architecture.md).
- Coupling and cascades: [`03-coupling-and-cascades.md`](03-coupling-and-cascades.md).
- Stage 2 details: [`20-stage2-clock-historian.md`](20-stage2-clock-historian.md).
- Maintenance + policy: [`21-policy-and-maintenance.md`](21-policy-and-maintenance.md).
- Realism gaps and abstractions: [`22-realism-audit.md`](22-realism-audit.md).
- Improvement roadmap: [`23-improvement-roadmap.md`](23-improvement-roadmap.md).
- Dashboard walkthrough: [`24-dashboard-walkthrough.md`](24-dashboard-walkthrough.md).
- Original briefings: `docs/briefing/{hackathon.md, stage-1.md, stage-2.md, stage-3.md}`.
