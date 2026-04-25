# 00 — System Overview

> Where to start if you have 10 minutes to understand the whole digital twin.

---

## What this is

A **coupled digital twin** for the HP Metal Jet S100 binder-jetting metal 3D printer. Built for the HackUPC 2026 HP "When AI meets reality / Build the Brain Behind the Machine" challenge. Scope: **Stage 1 (the model) + Stage 2 (the clock + historian)**. Stage 3 (chatbot, voice, frontend) is deferred.

The core deliverable is a **deterministic state machine** that, given the previous tick's state and the four environmental/operational drivers, produces:

- The **true** next state of every modeled component (health index, status, physical metrics).
- The **observed** state — what the operator and the maintenance policy are actually allowed to see, after each component's reading runs through its own (possibly degraded) sensor model.
- The full **coupling context** — every cross-component effect that mattered this tick, persisted as JSON for attribution queries.

---

## The three subsystems × six components

The HP brief mandates one component from each of three subsystems. We model **two per subsystem** so each pair forms an **explainable feedback loop**:

| Subsystem | Components | Pair logic |
|---|---|---|
| **Recoating** | Recoater Blade · Linear Rail | Rail wear and blade alignment together set powder spread quality |
| **Printhead Array** | Nozzle Plate · Cleaning Interface | Clogged nozzles need more cleaning; degraded cleaning leaves more residual clogs |
| **Thermal Control** | Heating Element · Temperature Sensor | Sensor readings drive the heater controller; heater + sensor age each other |

Six components, six different classical failure laws: Archard wear (blade), Lundberg-Palmgren cubic (rail), Coffin-Manson + Poisson (nozzle), power-law cycle wear (cleaning), Arrhenius (heater), Arrhenius bias drift (sensor). See [`components/`](components/) for one file per component.

---

## The four drivers

Every tick takes four environmental/operational scalars in `[0, 1]`:

- `temperature_stress` — ambient °C deviation from optimal
- `humidity_contamination` — air moisture and powder purity
- `operational_load` — print hours / cycles intensity
- `maintenance_level` — how well the machine is being cared for (0 = neglect, 1 = perfect)

Plus a per-scenario `Environment` carrying static context (base ambient °C, weekly runtime hours, vibration level) and running counters. See [`01-data-contract.md`](01-data-contract.md).

---

## The execution flow per tick

```
prev_state ──▶ build_coupling_context(prev, drivers, env, dt)    [engine/coupling.py]
                  │  produces 4 *_effective drivers + 10 named factors
                  ▼
              for each component_id in COMPONENT_IDS [registry]:
                  rng = derive_component_rng(seed, tick+1, component_id)
                  next_components[cid] = component.step(prev_self, coupling, drivers, env, dt, rng)
                  ↑ all six step()s read from the same prev + coupling
                    (double-buffered — update order can't change results)
                  ▼
              derive_print_outcome(next_components)  ──▶  OK / QUALITY_DEGRADED / HALTED
                  │
                  ▼
              next_state = PrinterState(...)
              observed = build_observed_state(next_state, sensors_rng)   [§3.4 sensor pass]
              return next_state, observed, coupling
```

This is implemented in `sim/src/copilot_sim/engine/engine.py:35`. See [`02-engine-architecture.md`](02-engine-architecture.md).

---

## What makes the components *coupled*

A coupled system is more than a collection of independent decay curves. Three engineering rules enforce coupling:

1. **Single coupling entry point** (`engine/coupling.py`). Every cross-component effect flows through one function that produces a `CouplingContext`. Components never read each other's metrics directly.
2. **Double-buffered update**. Every component step reads from the same immutable `prev_state` + same `coupling`. Update order can't change the result.
3. **Persisted attribution**. The 10 named coupling factors land in the historian's `coupling_factors_json` column per tick, so any failure can be walked back to its upstream causes after the fact without re-running the simulation.

The five cascades — powder, thermal, sensor↔heater, cleaning↔nozzle, rail↔blade — are detailed in [`03-coupling-and-cascades.md`](03-coupling-and-cascades.md).

---

## Stage 2 — the clock + historian

Stage 1 is a pure function. Stage 2 wraps it in a time-advancing loop:

```
                ┌──────────────────────┐
input drivers ─▶│  Phase 1 — Engine    │──▶  PrinterState (true)
(sin / OU /     │  Engine.step()       │     + ObservedPrinterState (§3.4)
 duty / step)   │  + coupling context  │
                └──────────────────────┘
                          │
                          ▼
                ┌──────────────────────┐
                │  Historian (SQLite)  │   ── 7 tables, WAL, WITHOUT ROWID
                │  runs · drivers ·    │      coupling_factors_json per tick
                │  component_state ·   │      true + observed mirrors
                │  metrics · obs_*     │      events + environmental_events
                │  · events · env_evts │
                └──────────────────────┘
                          │
                          ▼
                ┌──────────────────────┐
                │  Heuristic Policy    │   reads observed only (so it can be
                │  (3 rules)           │   fooled by a drifting sensor — like
                │                      │   a real operator)
                └──────────────────────┘
                          │
                          ▼
                ┌──────────────────────┐
                │  Streamlit dashboard │   four panels: decay heatmap +
                │                      │   cascade attribution + true vs
                │                      │   observed + maintenance timeline
                └──────────────────────┘
```

`dt = 1` simulated week, default horizon 260 ticks (5 years). See [`20-stage2-clock-historian.md`](20-stage2-clock-historian.md) and [`21-policy-and-maintenance.md`](21-policy-and-maintenance.md).

---

## The §3.4 twist — sensors lie too

The HP organisers explicitly opened a twist (`TRACK-CONTEXT.md §3.4`): sensors are optional per component, sensors decay and fail too, and print outcome is itself a first-class signal. We split:

- `PrinterState` = engine ground truth (used internally only).
- `ObservedPrinterState` = what the operator/policy/co-pilot are allowed to see.

Each component has a `SensorModel` (`sim/src/copilot_sim/sensors/factories.py`):

- **Gaussian** — direct readout + small noise (blade, rail, nozzle, cleaning).
- **Sensor-mediated heater** — the heater's observed metrics flow *through* the temperature sensor's bias and noise. When the sensor fails, the heater's observed view goes `None` and `observed_status = UNKNOWN`.
- **Self-sensor** — the sensor reports its own bias.

The maintenance policy reads `ObservedPrinterState` only, never truth. So a drifting sensor can cause the operator to misdiagnose a "drifting heater" — exactly the sensor-fault-vs-component-fault story the brief rewards. See [`components/15-sensor.md`](components/15-sensor.md).

---

## Determinism contract

The brief mandates "same inputs → same outputs". The implementation goes further: **same seed + same scenario YAML = byte-identical historian**, regardless of process, parallelism, or `PYTHONHASHSEED`.

Three engineering rules:

1. **Per-component, per-tick RNG** via `derive_component_rng(seed, tick, component_id)` using a `blake2b(component_id)` digest as the third entropy axis. Independent of Python's salted `hash()`.
2. **Driver generators share one seeded `numpy.random.default_rng((seed, 0xD7_1A_E9))`**. Stateful generators (Ornstein-Uhlenbeck humidity) own their state on the dataclass.
3. **Chaos arrivals pre-rolled at scenario load** with a separate RNG tag (`0xC4_A0_5E`). Schedule is stable across process restarts.

Tests in `sim/tests/engine/test_rng_determinism.py` enforce both invariants.

---

## Where to start reading

| If you are... | Read in this order |
|---|---|
| **Defending the math** at the pitch | This file → [`03-coupling-and-cascades.md`](03-coupling-and-cascades.md) → the 6 component files in [`components/`](components/) → [`22-realism-audit.md`](22-realism-audit.md) |
| **Adding a new component** | This file → [`02-engine-architecture.md`](02-engine-architecture.md) → [`components/10-blade.md`](components/10-blade.md) (template) → [`components/registry.py`](../../sim/src/copilot_sim/components/registry.py) |
| **Debugging a weird simulation** | [`02-engine-architecture.md`](02-engine-architecture.md) → [`03-coupling-and-cascades.md`](03-coupling-and-cascades.md) → `inspect <run_id> --failure-analysis` CLI |
| **Improving realism** | [`22-realism-audit.md`](22-realism-audit.md) → [`23-improvement-roadmap.md`](23-improvement-roadmap.md) |
| **Pitching to judges** | This file → [`22-realism-audit.md`](22-realism-audit.md) §I (the one-question answer) |

---

## File map for the simulator code

| Concern | Path |
|---|---|
| Engine + coupling | `sim/src/copilot_sim/engine/{engine,coupling,aging,assembly}.py` |
| Six component step + reset | `sim/src/copilot_sim/components/{blade,rail,nozzle,cleaning,heater,sensor}.py` |
| Component registry (canonical iteration order) | `sim/src/copilot_sim/components/registry.py` |
| §3.4 sensor models | `sim/src/copilot_sim/sensors/{model,factories}.py` |
| Phase 2 clock + driver layer | `sim/src/copilot_sim/simulation/loop.py`, `drivers_src/*.py` |
| Historian (SQLite WAL) | `sim/src/copilot_sim/historian/{schema.sql,writer.py,reader.py}` |
| Heuristic policy | `sim/src/copilot_sim/policy/heuristic.py` |
| Dashboard | `sim/src/copilot_sim/dashboard/streamlit_app.py` |
| CLI (`copilot-sim run/inspect/list-scenarios`) | `sim/src/copilot_sim/cli.py` |
| Scenario YAMLs | `sim/scenarios/*.yaml` |
| Reference docs | `docs/research/0?-*.md`, `docs/research/22-printer-lifetime-research.md` |
