# 01 — Data Contract

> Every shape that crosses an engine boundary. The brief's "data contract" + the §3.4 split, made explicit.

---

## The four `Drivers`

The HP brief lists exactly four environmental/operational inputs. Every tick of `Engine.step` consumes a `Drivers` instance carrying scalars in `[0, 1]`:

```python
@dataclass(frozen=True, slots=True)
class Drivers:
    temperature_stress: float          # 0..1 — deviation from optimal °C, normalized
    humidity_contamination: float      # 0..1 — air moisture + powder purity
    operational_load: float            # 0..1 — print hours / cycle intensity
    maintenance_level: float           # 0..1 — 0 neglect, 1 perfect care
```

Source: `sim/src/copilot_sim/domain/drivers.py`.

**The clip-to-[0,1] convention is contractual**, enforced by the loop in `drivers_src/assembly.py` and by pydantic validators in `simulation/scenarios.py`. Components rely on this to keep formulas bounded.

Note: components **don't read raw `Drivers` directly**. They read `coupling.*_effective` versions instead (see [`03-coupling-and-cascades.md`](03-coupling-and-cascades.md)). The raw `Drivers` is passed for symmetry and future use.

---

## The `Environment` (per-scenario static context)

The brief lists four drivers; everything else the simulator needs lives on `Environment`. Each `Engine.step` call receives an immutable snapshot.

```python
@dataclass(frozen=True, slots=True)
class Environment:
    base_ambient_C: float           # e.g. 22 Barcelona, 32 Phoenix
    amplitude_C: float              # ± seasonal swing in °C
    weekly_runtime_hours: float     # printer activity per simulated week
    vibration_level: float          # constant vibration baseline 0..1
    cumulative_cleanings: int       # running counter (loop-managed)
    hours_since_maintenance: float  # running counter (loop-managed)
    start_stop_cycles: int          # running counter (loop-managed)
```

Source: `sim/src/copilot_sim/drivers_src/environment.py`.

The `base_ambient_C + amplitude_C · (2·temp_stress_eff − 1)` formula in `engine/coupling.py:111` is what folds the brief's `temperature_stress` driver into a Kelvin temperature for the Arrhenius components.

---

## `ComponentState` — the per-component output shape

```python
@dataclass(frozen=True, slots=True)
class ComponentState:
    component_id: str                       # "blade", "rail", ...
    health_index: float                     # 0.0 dead .. 1.0 new
    status: OperationalStatus               # FUNCTIONAL/DEGRADED/CRITICAL/FAILED
    metrics: Mapping[str, float]            # physical quantities, e.g. {"wear_level": 0.35}
    age_ticks: int                          # counts ticks since last REPLACE
```

Source: `sim/src/copilot_sim/domain/state.py`.

The `metrics` dict is component-specific:

| Component | Metrics keys |
|---|---|
| blade | `wear_level`, `edge_roughness`, `thickness_mm` |
| rail | `misalignment`, `friction_level`, `alignment_error_um` |
| nozzle | `clog_pct`, `thermal_fatigue`, `fatigue_damage` |
| cleaning | `wiper_wear`, `residue_saturation`, `cleaning_effectiveness` |
| heater | `resistance_drift`, `power_draw`, `energy_per_C` |
| sensor | `bias_offset`, `noise_sigma`, `reading_accuracy` |

`age_ticks` is the number of ticks since the component's last full reset (REPLACE). It feeds the Weibull baseline `R(t) = exp(-(t/η)^β)` in every component's `step()`.

---

## `OperationalStatus` and the four-step ladder

```python
class OperationalStatus(Enum):
    FUNCTIONAL = "FUNCTIONAL"   # within normal envelope
    DEGRADED = "DEGRADED"       # watch; schedule maintenance window
    CRITICAL = "CRITICAL"       # act now; remaining useful life days
    FAILED = "FAILED"           # replacement required before next print
    UNKNOWN = "UNKNOWN"         # observed only — sensor reading missing
```

`UNKNOWN` is the §3.4 escape hatch. It **never** appears in true state — only in observed views when no sensor reading is recoverable.

Status thresholds (`engine/aging.py:26-28`):

| Health range | Status |
|---|---|
| `>= 0.75` | FUNCTIONAL |
| `>= 0.45` | DEGRADED |
| `>= 0.20` | CRITICAL |
| `< 0.20` | FAILED |

> **Note**: `docs/research/04-aging-baselines-and-normalization.md` and the README quote `>0.40 / >0.15` — the code is 5 pp more aggressive than the docs. See [`22-realism-audit.md`](22-realism-audit.md) §C.4 for the reconciliation.

The sensor adds a **hard fail** at `|bias| > 5 °C` regardless of HI composition (`components/sensor.py:108`).

---

## `PrinterState` — the system-level snapshot

```python
@dataclass(frozen=True, slots=True)
class PrinterState:
    tick: int
    sim_time_s: float
    components: Mapping[str, ComponentState]   # registry-ordered
    print_outcome: PrintOutcome                # OK / QUALITY_DEGRADED / HALTED
```

`PrintOutcome` (`domain/enums.py`):

- **OK** — every component above 0.40 health and no CRITICAL status.
- **QUALITY_DEGRADED** — any component CRITICAL or `min_health < 0.40`.
- **HALTED** — any component FAILED.

Derived in `engine/assembly.py:28` (`derive_print_outcome`).

This is the brief's first-class observable: real binder-jet operators *notice* a halted print or visibly poor parts long before they look at telemetry. The print outcome is what closes the operator loop *notice → stop → diagnose → fix → resume*.

---

## `ObservedComponentState` — the §3.4 mirror

```python
@dataclass(frozen=True, slots=True)
class ObservedComponentState:
    component_id: str
    observed_metrics: Mapping[str, float | None]    # None = sensor absent / stuck
    sensor_health: Mapping[str, float | None]
    sensor_note: str                                # "ok" | "noisy" | "drift" | "stuck" | "absent"
    observed_health_index: float | None             # None when sensors can't recover an estimate
    observed_status: OperationalStatus | None       # may be UNKNOWN
```

Source: `sim/src/copilot_sim/domain/state.py:44`.

- **`observed_metrics`** — the per-metric values an operator sees. `None` means the sensor is absent or stuck-at-None.
- **`sensor_health`** — per-metric trust level. Lets the policy quote a confidence.
- **`sensor_note`** — categorical tag for the dashboard / co-pilot. The five values map to the underlying sensor's status.
- **`observed_health_index` / `observed_status`** — the "best estimate" the sensor pass produced. `None` / `UNKNOWN` when too many sensors are missing.

`ObservedPrinterState` is the system-level wrapper, identical shape to `PrinterState` but with `ObservedComponentState` per component.

The maintenance policy reads `ObservedPrinterState` only, **never** the true `PrinterState`. That's what makes the simulator a fair test of operator decisions — the operator can be fooled by a drifting sensor exactly like a real one.

---

## `MaintenanceAction` and `OperatorEvent`

The action vocabulary (`domain/enums.py`):

```python
class OperatorEventKind(Enum):
    TROUBLESHOOT = "TROUBLESHOOT"   # diagnose only — no state change
    FIX = "FIX"                     # partial recovery (component-specific)
    REPLACE = "REPLACE"             # full reset (component-specific)
```

The action carrying intent into the engine:

```python
@dataclass(frozen=True, slots=True)
class MaintenanceAction:
    component_id: str                       # "blade", "sensor", ...
    kind: OperatorEventKind
    payload: Mapping[str, float]            # action-specific knobs
```

The historian event row written by `Engine.apply_maintenance`:

```python
@dataclass(frozen=True, slots=True)
class OperatorEvent:
    tick: int
    sim_time_s: float
    kind: OperatorEventKind
    component_id: str | None                # None = global event
    payload: Mapping[str, float | str]
```

Source: `sim/src/copilot_sim/domain/events.py`.

`apply_maintenance` is **out-of-band** — the simulation loop calls it *between* `step()` calls, never inside one (doc 20 §maintenance ordering). Per-component reset rules are encoded in each component's `reset()` function. See [`21-policy-and-maintenance.md`](21-policy-and-maintenance.md) for the full reset matrix.

---

## `CouplingContext` — the cross-component channel

```python
@dataclass(frozen=True, slots=True)
class CouplingContext:
    temperature_stress_effective: float     # 0..1 — raw + cross-component bumps
    humidity_contamination_effective: float
    operational_load_effective: float
    maintenance_level_effective: float
    factors: Mapping[str, float]            # 10 named coupling terms
```

Source: `sim/src/copilot_sim/domain/coupling.py`.

This is the **only** object that carries cross-component effects into a component step. See [`03-coupling-and-cascades.md`](03-coupling-and-cascades.md) for the 10 factors and the cascade chain map.

---

## Why frozen+slots dataclasses everywhere

Every domain object is `@dataclass(frozen=True, slots=True)` and wraps maps via `MappingProxyType` (the `freeze_*` helpers). Three engineering reasons:

1. **Immutability** — `Engine.step` is a pure function. A frozen state can't be mutated by accident, so the double-buffered rule (read from same `prev` everywhere) is enforced by the type system.
2. **Single allocation** — slots mean each instance is a tuple-like layout in memory, not a dict-of-attributes. ~2× speedup at the per-tick scale we run at.
3. **Type-checker friendly** — `ty` (uv-managed, see `sim/pyproject.toml`) can verify the contract statically. No runtime field mismatches.

The `freeze_components`, `freeze_metrics`, `freeze_sensor_health`, `freeze_payload`, and `freeze_factors` static methods on the dataclasses wrap mutable input mappings into `MappingProxyType` so callers can't poke holes in the immutability after construction.
