# 02 — Engine Architecture

> The Stage 1 deliverable. One pure function, six components, six failure laws, double-buffered, deterministic.

---

## The one function that matters

```python
class Engine:
    def __init__(self, scenario_seed: int) -> None: ...

    def step(
        self,
        prev: PrinterState,
        drivers: Drivers,
        env: Environment,
        dt: float,
    ) -> tuple[PrinterState, ObservedPrinterState, CouplingContext]: ...
```

Source: `sim/src/copilot_sim/engine/engine.py:35`.

Everything in Stage 1 is in service of this signature. It is **pure** — same `(prev, drivers, env, dt, scenario_seed)` always returns the same triple, regardless of process, parallelism, or import order.

---

## What `step()` does, in order

```
1.  coupling = build_coupling_context(prev, drivers, env, dt)
        │
        │  Reads only `prev` (immutable). Produces:
        │   • 4 *_effective drivers (raw + cross-component bumps)
        │   • factors: dict of 10 named cross-component terms
        ▼

2.  for component_id in COMPONENT_IDS:                         # canonical order
        spec = REGISTRY[component_id]
        rng = derive_component_rng(scenario_seed, prev.tick + 1, component_id)
        next_components[cid] = spec.step(
            prev.components[cid],     # this component's prev state
            coupling,                 # shared coupling context (immutable)
            drivers,                  # raw drivers (rarely used)
            env,                      # static + counter context
            dt,
            rng,                      # fresh per-component, per-tick RNG
        )

    # Critical: every step() reads from the SAME prev + SAME coupling.
    # Loop order can NOT change the result. This is the double-buffered rule.

3.  print_outcome = derive_print_outcome(next_components)
        │
        │  HALTED if any FAILED · QUALITY_DEGRADED if any CRITICAL
        │  or min_health < 0.40 · else OK
        ▼

4.  next_state = PrinterState(
        tick=prev.tick + 1,
        sim_time_s=prev.sim_time_s + dt,
        components=PrinterState.freeze_components(next_components),
        print_outcome=print_outcome,
    )

5.  observed = build_observed_state(next_state, sensors_rng)
        │
        │  §3.4 sensor pass — per-component SensorModel turns true state
        │  into observed state. Heater observations flow through the
        │  temperature sensor's bias + noise.
        ▼

6.  return next_state, observed, coupling
```

---

## The double-buffered update rule

This is the most important architectural rule, and it's locked in `AGENTS.md § Simulation Modeling`:

> All components read from the same immutable previous `PrinterState`; compute cross-component influence terms from `t-1`; then produce the new `PrinterState` for `t` without letting update order affect results.

In code, this means:

- **No component step function ever writes to `prev`**. `prev` is `frozen=True`.
- **No component step function reads `next_components` directly**. Cross-component effects come through `coupling`, which was built once from `prev` before the loop started.
- **Component iteration order is fixed** (`COMPONENT_IDS = ("blade", "rail", "nozzle", "cleaning", "heater", "sensor")`) but **swapping it would not change the result**.

That's how a coupled discrete-time system can be both interconnected and update-order-independent. The trick: **read the present, compute the future, never mix the two**.

---

## The component registry

The engine never imports per-component modules directly. It iterates a registry:

```python
COMPONENT_IDS: tuple[str, ...] = (
    "blade", "rail", "nozzle", "cleaning", "heater", "sensor",
)

REGISTRY: Mapping[str, ComponentSpec] = {
    "blade": ComponentSpec(component_id="blade",
                           initial_state=blade.initial_state,
                           step=blade.step,
                           reset=blade.reset),
    ...
}
```

Source: `sim/src/copilot_sim/components/registry.py`.

Each `ComponentSpec` is a triple of callables:

- `initial_state() -> ComponentState` — fresh-from-factory state, called by `Engine.initial_state()` at `t=0` and by `reset()` for full REPLACE.
- `step(prev_self, coupling, drivers, env, dt, rng) -> ComponentState` — the one-tick update.
- `reset(prev_self, kind, payload) -> ComponentState` — apply maintenance per the action vocabulary.

Adding a new component is: write the three functions in a new file, register it in the spec map, append the id to `COMPONENT_IDS`. The engine and the historian pick it up automatically.

**Iteration order is deliberate**: blade and rail (recoating) → nozzle and cleaning (printhead) → heater and sensor (thermal). Within each subsystem, the "sensored" component is listed second so failure-analysis output reads top-down.

---

## Per-component RNG via blake2b digest

`engine/aging.py:108`:

```python
def derive_component_rng(scenario_seed: int, tick: int, component_id: str) -> np.random.Generator:
    return np.random.default_rng((
        int(scenario_seed),
        int(tick),
        _component_id_digest(component_id),     # blake2b 8-byte digest
    ))
```

Two invariants hold by construction:

1. **Same `(scenario_seed, tick, component_id)` ⇒ identical Generator state**, regardless of iteration order, parallelism, or process restart. Python's built-in `hash(str)` is salted by `PYTHONHASHSEED` so it would give different streams across processes — `blake2b` is bit-stable.
2. **Different components at the same tick get statistically independent streams**. The 64-bit `blake2b` digest is the third entropy axis.

Tested in `sim/tests/engine/test_rng_determinism.py`.

---

## How `apply_maintenance` differs

```python
def apply_maintenance(
    self,
    state: PrinterState,
    action: MaintenanceAction,
) -> tuple[PrinterState, OperatorEvent]:
```

Source: `sim/src/copilot_sim/engine/engine.py:63`.

Three rules baked in:

1. **TROUBLESHOOT never mutates state**. It only writes an event row.
2. **FIX and REPLACE dispatch to the targeted component's `reset()` function**. Each component encodes its own reset semantics (see [`21-policy-and-maintenance.md`](21-policy-and-maintenance.md)).
3. **The print outcome is recomputed** because a successful FIX on the bottleneck component might lift the printer out of QUALITY_DEGRADED.

`apply_maintenance` is **out-of-band** — the simulation loop calls it *between* `step()` calls, never inside one (`docs/research/20-engine-architecture.md` §maintenance ordering). This keeps the engine signature pure: `step()` deals with physics, `apply_maintenance` deals with operator interventions.

---

## How `derive_print_outcome` works

`engine/assembly.py:28`:

```python
def derive_print_outcome(components: Mapping[str, ComponentState]) -> PrintOutcome:
    if any(c.status is OperationalStatus.FAILED for c in components.values()):
        return PrintOutcome.HALTED

    any_critical = any(c.status is OperationalStatus.CRITICAL for c in components.values())
    min_health = min((c.health_index for c in components.values()), default=1.0)
    if any_critical or min_health < _QUALITY_DEGRADED_HEALTH:    # 0.40
        return PrintOutcome.QUALITY_DEGRADED

    return PrintOutcome.OK
```

`PrintOutcome` is a top-level field on `PrinterState`. It's persisted on the historian's `drivers` table per tick, so a Phase 3 chatbot can answer "did the print halt at week 47?" with a single-row lookup.

---

## How `build_observed_state` works (§3.4)

`engine/assembly.py:43`:

```python
def build_observed_state(state: PrinterState, rng: np.random.Generator) -> ObservedPrinterState:
    observed = {}
    for cid, component in state.components.items():
        model = make_sensor_model(cid)
        observed[cid] = model.observe(component, state, rng)
    return ObservedPrinterState(...)
```

`make_sensor_model` (`sensors/factories.py:174`) returns one of three:

| Component | SensorModel | Behavior |
|---|---|---|
| blade, rail, nozzle, cleaning | `GaussianSensorModel(noise_sigma)` | Direct readout + small additive noise |
| heater | `SensorMediatedHeaterModel` | Each metric `+= sensor.bias + N(0, sensor.noise_sigma)`. Drops to None when sensor is FAILED. |
| sensor | `SelfSensorModel` | Reports its own true bias |

The same `rng` is shared across components so observation noise is deterministic w.r.t. `(seed, tick, "_sensors")`.

---

## `Engine.initial_state()`

```python
def initial_state() -> PrinterState:
    return PrinterState(
        tick=0,
        sim_time_s=0.0,
        components=PrinterState.freeze_components(registry.initial_components()),
        print_outcome=PrintOutcome.OK,
    )
```

Lives on the engine module instead of `simulation/bootstrap.py` because every engine test wants this convenience without dragging in the simulation loop.

---

## Sub-modules under `engine/`

| File | Role |
|---|---|
| `engine.py` | The `Engine` class, `step` + `apply_maintenance` + `initial_state` |
| `coupling.py` | `build_coupling_context` (the cascade entry point) and `ambient_temperature_C_effective` |
| `aging.py` | Weibull baseline, status thresholds, `clip01`, maintenance damper, RNG plumbing |
| `assembly.py` | `derive_print_outcome`, `build_observed_state` |

Aging is shared across every component. Status thresholds live there as module constants so tests can import the same numbers.

---

## Tests that lock the contract

| Test | What it verifies |
|---|---|
| `tests/engine/test_engine_step.py` | `step()` returns six components, the 10 named factors, and is deterministic across two engines with the same seed |
| `tests/engine/test_rng_determinism.py` | Per-component RNG invariants (same key → same stream, different components → independent streams) |
| `tests/engine/test_driver_coverage.py` | Each component's metrics are strictly monotone in their respective drivers (the audit-grep that proves all 4 drivers feed each component) |
| `tests/engine/test_apply_maintenance.py` | TROUBLESHOOT / FIX / REPLACE dispatch and per-component reset semantics |
| `tests/engine/test_sensor_pass.py` | The §3.4 true→observed transformation, including UNKNOWN propagation when sensor is FAILED |

Run with `cd sim && uv run pytest`.
