# Engine Architecture — Coupled Discrete-Time Step Function

> Documents the engine architecture **as already implemented** in
> [`sim/src/copilot_sim/domain/`](../../sim/src/copilot_sim/domain/) (commit `64b3e0d`)
> and locked by [`AGENTS.md` § Simulation Modeling](../../AGENTS.md). This doc is a
> *written* spec for the report; the canonical source of truth is the code +
> AGENTS.md rule. Last updated: 2026-04-25.

---

## TL;DR

The Phase 1 engine is a **coupled discrete-time map** `next_state = f(prev_state, drivers, dt)`. Every tick:

1. Read the **immutable** `t-1` `PrinterState` (true ground-truth view).
2. Build **one** `CouplingContext` that captures every cross-component effect — four `*_effective` drivers + a named `factors` dict.
3. Invoke each of the six per-component `step()` functions from the **same** snapshot, using the same `CouplingContext`.
4. Assemble the new `PrinterState` at `t`.
5. Pass the new state through per-component sensor models to produce `ObservedPrinterState` (the §3.4 split).
6. Derive `print_outcome ∈ {OK, QUALITY_DEGRADED, HALTED}` from the new state.

Update order **cannot** affect results because all six `step()` calls read `prev_state` only — there is no within-tick algebraic loop. Damage accumulators are monotone non-decreasing between maintenance events, and coupling gains are sub-unity, so the system is provably bounded ([doc 05 §stability](./05-cascading-and-ai-degradation.md#stability-and-bounded-feedback-argument)).

---

## Why coupled, not independent

The brief lists "cascading failures" as a Phase 1 bonus and explicitly seeds the cascade idea ("degraded blade → contaminated powder → clogs nozzle"). A naive simulator runs each component as an independent decay curve; a coupled simulator lets degradation in one component change the **operating environment** of others. The latter is what produces emergent failure trajectories the dashboard can attribute via `coupling_factors_json`, and it's what the Phase 1 + Phase 2 evaluation pillar "Systemic Interaction" rewards.

The coupled formulation also gives us the §3.4 sensor-fault story for free: the temperature sensor's bias appears as `factors["control_temp_error_c"]` in the context, which the heater step consumes — so a drifting sensor mechanically accelerates heater Arrhenius aging without either component reading the other directly.

---

## The five domain types

All implemented as `@dataclass(frozen=True, slots=True)` with `MappingProxyType` freezers for nested mappings (immutability is enforced; if you try to mutate a `PrinterState` you get a `FrozenInstanceError`).

### `Drivers`  ([`drivers.py`](../../sim/src/copilot_sim/domain/drivers.py))

The four input drivers from the brief, exactly as `TRACK-CONTEXT.md §3.1` specifies. **Not split.** `humidity_contamination` is one driver; powder contamination cascades in via `humidity_contamination_effective`, not via a separate driver.

```python
@dataclass(frozen=True, slots=True)
class Drivers:
    temperature_stress: float
    humidity_contamination: float
    operational_load: float
    maintenance_level: float
```

### `CouplingContext` ([`coupling.py`](../../sim/src/copilot_sim/domain/coupling.py))

Built once per tick by `engine.coupling.build_coupling_context(prev_state, drivers, dt)`. Carries the four *effective* drivers (raw drivers post-coupling) and a named `factors` mapping. The factors dict is the canonical place to expose any cross-component derived quantity to the step functions and to the historian (`coupling_factors_json`).

```python
@dataclass(frozen=True, slots=True)
class CouplingContext:
    temperature_stress_effective: float
    humidity_contamination_effective: float
    operational_load_effective: float
    maintenance_level_effective: float
    factors: Mapping[str, float]
```

[Doc 05 §CouplingContext derivation](./05-cascading-and-ai-degradation.md#couplingcontext-derivation) lists the eight named factors locked for v1: `powder_spread_quality`, `blade_loss_frac`, `rail_alignment_error`, `heater_drift_frac`, `heater_thermal_stress_bonus`, `sensor_bias_c`, `sensor_noise_sigma_c`, `control_temp_error_c`, `cleaning_efficiency`, `nozzle_clog_pct`.

### `PrinterState` and `ComponentState` ([`state.py`](../../sim/src/copilot_sim/domain/state.py))

The **true** state, used internally by the engine.

```python
@dataclass(frozen=True, slots=True)
class ComponentState:
    component_id: str
    health_index: float                       # 0.0..1.0
    status: OperationalStatus                 # FUNCTIONAL | DEGRADED | CRITICAL | FAILED
    metrics: Mapping[str, float]              # physical quantities
    age_ticks: int

@dataclass(frozen=True, slots=True)
class PrinterState:
    tick: int
    sim_time_s: float
    components: Mapping[str, ComponentState]  # 6 keys: blade, rail, nozzle, cleaning, heater, sensor
    print_outcome: PrintOutcome               # OK | QUALITY_DEGRADED | HALTED
```

`status` on the true layer is **never** `UNKNOWN` — that value is reserved for the observed layer when no sensor reading is recoverable.

### `ObservedPrinterState` and `ObservedComponentState` ([`state.py`](../../sim/src/copilot_sim/domain/state.py))

The **observed** state, derived from the true state by applying per-component sensor models. This is what the maintenance policy and any future co-pilot consume.

```python
@dataclass(frozen=True, slots=True)
class ObservedComponentState:
    component_id: str
    observed_metrics: Mapping[str, float | None]      # None ⇒ sensor absent / stuck-at-None
    sensor_health: Mapping[str, float | None]         # 0..1 per metric, None ⇒ no sensor
    sensor_note: str                                  # "ok" | "noisy" | "drift" | "stuck" | "absent" | mixed-tag
    observed_health_index: float | None               # None when too many sensors failed
    observed_status: OperationalStatus | None         # may be UNKNOWN
```

The reference implementation of the per-metric sensor model is [doc 19](./19-temperature-sensor.md) — every sensored component reuses the same `(true, sensor_state) → (observed, sensor_note)` shape.

### `MaintenanceAction` and `OperatorEvent` ([`events.py`](../../sim/src/copilot_sim/domain/events.py))

```python
class OperatorEventKind(Enum):
    TROUBLESHOOT = "TROUBLESHOOT"   # inspect; no state change, sets last_inspected_tick
    FIX = "FIX"                     # partial recovery (component-specific)
    REPLACE = "REPLACE"             # full reset (component-specific)
```

The maintenance policy ([doc 09](./09-maintenance-agent.md)) emits `MaintenanceAction(component_id, kind, payload)`. Per-component reset rules live in doc 09 §maintenance effect model. Every action also writes one `OperatorEvent` row to the historian's `events` table.

---

## `Engine.step()` — the orchestration

```python
class Engine:
    def step(
        self,
        prev: PrinterState,
        drivers: Drivers,
        dt: float,
    ) -> tuple[PrinterState, ObservedPrinterState]:
        # 1. Coupling — read prev_state once, derive everything cross-component
        coupling = build_coupling_context(prev, drivers, dt)

        # 2. Six per-component step()s, all reading the SAME prev snapshot
        #    + the SAME coupling. Order does not matter.
        next_components = {
            "blade":    blade_step   (prev.components["blade"],    coupling, drivers, dt),
            "rail":     rail_step    (prev.components["rail"],     coupling, drivers, dt),
            "nozzle":   nozzle_step  (prev.components["nozzle"],   coupling, drivers, dt),
            "cleaning": cleaning_step(prev.components["cleaning"], coupling, drivers, dt),
            "heater":   heater_step  (prev.components["heater"],   coupling, drivers, dt),
            "sensor":   sensor_step  (prev.components["sensor"],   coupling, drivers, dt),
        }

        # 3. Derive system-level outcome
        print_outcome = derive_print_outcome(next_components, coupling)

        # 4. Assemble the new TRUE state (frozen, returned as a fresh value)
        next_state = PrinterState(
            tick=prev.tick + 1,
            sim_time_s=prev.sim_time_s + dt,
            components=PrinterState.freeze_components(next_components),
            print_outcome=print_outcome,
        )

        # 5. Apply per-component sensor models → OBSERVED state
        observed = build_observed_state(next_state)

        return next_state, observed

    def apply_maintenance(
        self,
        state: PrinterState,
        action: MaintenanceAction,
    ) -> PrinterState:
        # Per-component reset rule (see doc 09).
        # Returns a fresh PrinterState with the targeted component mutated.
        ...
```

**What this design buys:**

- **Determinism by construction.** Same `(prev, drivers, dt, seed)` ⇒ identical `next_state`. No global mutable state, no within-tick aliasing.
- **Update-order independence.** All six `step()` calls receive `prev` and `coupling` — neither can see another's `next` slice. Reordering the six calls cannot change the result.
- **Single coupling pass.** `build_coupling_context` runs once per tick, not six times. Every cross-component effect lives in one place; new couplings are one `factors[…] = …` edit.
- **§3.4 split is a separate pass.** The sensor models run on the new true state in step 5 — they are not in the engine's hot path and can be turned off (`build_observed_state(state) == state` shape) without changing the true engine output.
- **Maintenance is out-of-band.** `apply_maintenance` is a separate entry point called by the loop between `step()` calls, never inside one. Keeps the per-tick math clean.

---

## Determinism & seeding

A single `seed: int` config field is threaded through every stochastic element:

- The chaos overlay ([doc 06 §chaos](./06-driver-profiles-and-time.md#chaos--stochastic-layer-phase-2-bonus-pattern-c)) draws all Poisson interarrivals up-front via `rng = np.random.default_rng(seed)`.
- The Poisson clog hazard in the nozzle step ([doc 02](./02-nozzle-plate-coffin-manson.md)) uses the same `rng`.
- The dropout events in the sensor model ([doc 19](./19-temperature-sensor.md)) use the same `rng`.
- The OU integrator for humidity ([doc 06](./06-driver-profiles-and-time.md)) uses the same `rng`.

Same `seed` + same `Drivers` sequence ⇒ byte-identical historian. Different scenarios get different seeds (`seed=42` "nominal", `seed=7` "rough lot", `seed=999` "HVAC failure week"). `numpy.random.default_rng` is the only RNG; no `random.random`, no `numpy.random` global state.

---

## What lives outside the engine

The engine is intentionally narrow:

- **Driver generation** — sinusoidal Temp / OU Humidity / duty-cycle Load / step Maintenance + chaos overlay live in `sim/src/copilot_sim/drivers_src/` ([doc 06](./06-driver-profiles-and-time.md)). The engine does not generate drivers; it consumes them.
- **Historian persistence** — writing to SQLite lives in `sim/src/copilot_sim/historian/` ([doc 08](./08-historian-schema.md)). The engine does not know about persistence.
- **Maintenance policy** — choosing when and what to maintain lives in `sim/src/copilot_sim/policy/` ([doc 09](./09-maintenance-agent.md)). The engine just receives `MaintenanceAction` and applies the per-component reset rule.
- **Loop / clock** — owning the `tick → drivers → engine.step → historian.write` cycle lives in `sim/src/copilot_sim/simulation/`. The engine is a pure function of state.

This decoupling matches the brief's Phase 1 / Phase 2 split: the engine **is** Phase 1, callable by an external Phase 2 loop.

---

## References

- [`AGENTS.md` § Simulation Modeling](../../AGENTS.md) — the canonical "all components read from the same immutable previous PrinterState; double-buffered" rule.
- [`sim/src/copilot_sim/domain/`](../../sim/src/copilot_sim/domain/) — the implemented domain types.
- [`TRACK-CONTEXT.md §2 Chosen Phase 1 component scope`](../../TRACK-CONTEXT.md) — the six-component pair selection.
- [`TRACK-CONTEXT.md §3 Data Contract`](../../TRACK-CONTEXT.md) — input/output contract.
- [`TRACK-CONTEXT.md §3.4 Observability`](../../TRACK-CONTEXT.md) — true-vs-observed split that motivates `ObservedPrinterState`.
- [Doc 05 — coupling matrix](./05-cascading-and-ai-degradation.md) — what `build_coupling_context` computes.
- [Doc 04 — composition rule](./04-aging-baselines-and-normalization.md) — `H_total = H_baseline · H_driver`, status thresholds.
- Per-component step specs: [01](./01-recoater-blade-archard.md) [17](./17-linear-rail.md) [02](./02-nozzle-plate-coffin-manson.md) [18](./18-cleaning-interface.md) [03](./03-heating-elements-arrhenius.md) [19](./19-temperature-sensor.md).

---

## Open questions

- **Where does `derive_print_outcome` live?** Inside `Engine.step()` for now. If the policy ever needs to influence outcome (e.g. a failed mid-print abort decision), promote it to its own module.
- **`apply_maintenance` ordering vs `step()`.** Current contract: the loop calls `apply_maintenance(state, action)` *between* ticks, never inside `step()`. If we ever want a "pause-mid-tick to maintain" feature, this contract has to break — flagged.
- **Multi-component maintenance.** `MaintenanceAction` targets one `component_id`. The LLM-as-policy stretch may want to target multiple in one tick (e.g. concurrent FIX of nozzle + cleaning); the loop can apply the actions sequentially without breaking the contract.
- **Per-component step signature.** Current proposal `step(prev_self, coupling, drivers, dt) → next_self`. If a step needs to read another component's full state (not just a coupling factor), we either add it to `factors` or break the contract — bias toward the former.
