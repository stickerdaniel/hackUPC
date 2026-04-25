# 21 — Policy and Maintenance

> The *AI Maintenance Agent* bonus from Stage 2 — and the per-component reset rules that encode real industrial maintenance practice.

---

## The action vocabulary — three kinds, not binary

The brief's stage-2 doc lists "AI Maintenance Agent that autonomously decides *when* to trigger maintenance" as a Complexity & Innovation bonus. We model **three operator actions**, not just "maintain / don't":

```python
class OperatorEventKind(Enum):
    TROUBLESHOOT = "TROUBLESHOOT"   # diagnose only — no state change
    FIX = "FIX"                     # partial recovery (component-specific)
    REPLACE = "REPLACE"             # full reset (component-specific)
```

Source: `sim/src/copilot_sim/domain/enums.py`.

Why three:

- **Real operators** don't go from "do nothing" to "rip out the part". They diagnose first (TROUBLESHOOT), try a quick fix if the problem is recoverable (FIX), and only swap the part as a last resort (REPLACE).
- **The §3.4 sensor-fault story needs TROUBLESHOOT**: when a sensor reads UNKNOWN, the policy emits TROUBLESHOOT(sensor) **before** doing anything else. Acting blind on a missing sensor is what the brief's §3.4 explicitly warns against.
- **Different components support different action sets** (see §reset rules below). Blade has no field-repairable FIX; rail's REPLACE is rare and expensive; sensor's FIX is calibration-only. Three actions × six components = a richer policy space than binary.

---

## The heuristic policy

Source: `sim/src/copilot_sim/policy/heuristic.py`.

Reads **`ObservedPrinterState` only** — never the true state. Three rules in priority order:

```python
@dataclass(slots=True)
class HeuristicPolicy:
    last_action_tick: dict[str, int] = field(default_factory=dict)

    def decide(self, observed: ObservedPrinterState, tick: int) -> list[MaintenanceAction]:
        # Rule 1 — TROUBLESHOOT on any UNKNOWN observed_status.
        for cid in COMPONENT_IDS:
            oc = observed.components.get(cid)
            if oc and oc.observed_status is OperationalStatus.UNKNOWN:
                return [self._action(cid, OperatorEventKind.TROUBLESHOOT)]

        # Rule 2 — REPLACE / FIX on lowest observed health.
        candidates = [
            (oc.observed_health_index, idx, cid)
            for idx, cid in enumerate(COMPONENT_IDS)
            if (oc := observed.components.get(cid))
            and oc.observed_health_index is not None
            and oc.observed_health_index < 0.45                   # _UNHEALTHY_FIX
        ]
        if candidates:
            candidates.sort()                                     # worst-first triage
            health, _, cid = candidates[0]
            kind = REPLACE if health < 0.20 else FIX              # _UNHEALTHY_REPLACE
            return [self._action(cid, kind, tick=tick)]

        # Rule 3 — monthly preventive FIX of the longest-unmaintained.
        oldest = self._oldest_component(tick)
        if oldest and (tick - self.last_action_tick.get(oldest, 0)) >= 4:    # _PREVENTIVE_TICK_GAP
            return [self._action(oldest, OperatorEventKind.FIX, tick=tick)]

        return []
```

### Rule 1 — TROUBLESHOOT first on UNKNOWN

The §3.4 sensor-fault discipline encoded as policy. If any component's `observed_status` is `UNKNOWN`, the policy emits a TROUBLESHOOT and stops. **Never act blind on a missing sensor reading.**

### Rule 2 — Worst-first triage with deterministic tie-break

Among components with `observed_health < 0.45`, pick the **lowest-health** one (not the first one in iteration order). REPLACE if `< 0.20`, else FIX.

The "worst-first" sort is a fairness fix over a naive fixed-iteration policy. Without it, **nozzle (which decays fastest at η = 8.5 weeks) would always win the FIX queue** even when rail or heater were materially worse — because the iteration walks `COMPONENT_IDS` in registry order and picks the first match. Sorting makes the policy's event log a fair triage signal.

The tie-break (registry order via the `idx` field in the sort tuple) keeps the policy deterministic — same observed → same action even when two components have identical health.

### Rule 3 — Monthly preventive FIX

When nothing reactive fires, do a preventive FIX on the longest-unmaintained component. `_PREVENTIVE_TICK_GAP = 4` weeks ≈ one simulated month at `dt = 1 week`.

This satisfies the *Maintenance as Input* bonus from stage-1.md while remaining defensible: real operators run monthly preventive maintenance walks even when nothing is alerting.

### Why at most one action per tick?

The current policy returns a `list[MaintenanceAction]` but always emits 0 or 1 actions per tick. The list shape leaves room for a future LLM-as-policy that can issue concurrent actions without changing the engine contract.

---

## The maintenance reset matrix

Per-component, per-action state changes. Source: each component's `reset()` function, derived from `docs/research/09-maintenance-agent.md`.

| Component | TROUBLESHOOT | FIX (partial) | REPLACE (full) |
|---|---|---|---|
| **Blade** | no-op | routes to REPLACE (consumable, no field repair) | initial_state() |
| **Rail** | no-op | friction × 0.5; **misalignment + alignment_error untouched** (pitting permanent) | initial_state() |
| **Nozzle** | no-op | clog × 0.3 (i.e., reduce by 70 %); fatigue × 0.5; damage × 0.5 | initial_state() |
| **Cleaning** | no-op | initial_state() (wiper-blade swap = full reset of wear path) | initial_state() |
| **Heater** | no-op | drift × 0.5; partial restore of power_draw + energy_per_C | initial_state() |
| **Sensor** | no-op | bias = 0 (calibration); **noise unchanged** (connector oxidation irreversible) | initial_state() |

Two patterns deserve special attention:

### Permanent damage on rail FIX

```python
# rail.py:124
if kind is FIX:
    return ComponentState(
        ...
        metrics={
            "misalignment": prev_self.metrics["misalignment"],         # NOT reset
            "friction_level": 0.5 * prev_self.metrics["friction_level"], # halved
            "alignment_error_um": prev_self.metrics["alignment_error_um"],  # NOT reset
        },
        age_ticks=prev_self.age_ticks,
    )
```

The rail's raceway pitting is **physically permanent**. Re-greasing recovers the lubricant film (friction halved) but the pitting damage doesn't disappear. This is the kind of detail that makes the *Realism & Fidelity* pillar defensible.

### Irreversible noise on sensor FIX

```python
# sensor.py:142
if kind is FIX:
    return ComponentState(
        ...
        metrics={
            "bias_offset": 0.0,                  # ZEROED (calibration removes offset)
            "noise_sigma": prev_noise,           # PRESERVED (connector oxidation irreversible)
            "reading_accuracy": new_accuracy,
        },
        age_ticks=prev_self.age_ticks,
    )
```

PT100 calibration corrects the bias offset but **doesn't fix connector noise** — the connector pin oxidation / work-hardening is a physical change that requires replacing the RTD element. This matches HW-group + Omega RTD service practice exactly.

---

## Why the policy reads observed-only

The §3.4 contract: **the policy must be foolable by a drifting sensor, exactly like a real operator**. It reads `ObservedPrinterState`, never the true `PrinterState`.

This produces interesting demo behaviors:

1. **Heater appears to drift (observed health drops) → policy issues `FIX(heater)`**. But the *true* heater is fine; the temperature sensor's bias is making it *look* drifted. The fix has no effect on the real cause, the apparent drift returns next tick, and the policy keeps firing fixes.
2. **At some point the sensor's bias crosses 5 °C → sensor goes FAILED → heater observed view becomes `UNKNOWN`**.
3. **Policy now emits `TROUBLESHOOT(sensor)` (rule 1)**, then `REPLACE(sensor)` (rule 2 with health < 0.20).
4. **After the sensor REPLACE, the heater's apparent drift disappears** because there's no longer a biased reading.

This is the **sensor-fault-vs-component-fault story** the brief's *Reasoning Depth* and *Proactive Intelligence* pillars explicitly reward. The dashboard's panel 3 visualizes it: a "true heater health" line that stays flat next to an "observed heater health" line that drops then recovers after the sensor swap.

---

## Apply maintenance — the between-tick channel

Source: `sim/src/copilot_sim/engine/engine.py:63`.

```python
def apply_maintenance(self, state, action) -> tuple[PrinterState, OperatorEvent]:
    if action.component_id not in state.components:
        raise KeyError(...)

    new_components = dict(state.components)
    if action.kind is not OperatorEventKind.TROUBLESHOOT:
        spec = registry.REGISTRY[action.component_id]
        new_components[action.component_id] = spec.reset(
            state.components[action.component_id], action.kind, action.payload
        )

    print_outcome = derive_print_outcome(new_components)        # may shift after FIX/REPLACE
    new_state = PrinterState(...)
    event = OperatorEvent(tick=state.tick, ..., kind=action.kind, ...)
    return new_state, event
```

Three rules:

1. **TROUBLESHOOT never mutates state**. It only writes an event row.
2. **FIX and REPLACE dispatch to the targeted component's `reset()` function**. Each component encodes its own per-action semantics.
3. **Print outcome is recomputed**. If the targeted component was the one holding everything in QUALITY_DEGRADED or HALTED, the print may now lift back to OK.

`apply_maintenance` is **out-of-band** — the simulation loop calls it *between* `step()` calls, never inside one. This keeps the engine signature pure: `step()` deals with physics, `apply_maintenance` deals with operator interventions. See `docs/research/20-engine-architecture.md` §maintenance-ordering.

---

## Why this scores on the bonus pillars

The *Complexity & Innovation* bonus from stage-2.md asks for "advanced behaviors such as an AI Maintenance Agent that autonomously schedules maintenance — surprise us!". The heuristic policy hits:

- **Three-action vocabulary** (not binary) — richer than the brief's expectation.
- **Reads observed only** — exposes the §3.4 sensor-fault story.
- **Worst-first triage with deterministic tie-break** — fairer than naive iteration.
- **Per-component reset semantics** — every action's effect matches real industrial practice.

The *Realism & Fidelity* bonus rewards "every failure event traceable to its root input drivers". Maintenance events are stored in the `events` historian table with `kind`, `component_id`, and `payload_json`. A Phase 3 chatbot can answer "why did the operator replace the sensor in week 79?" by joining `events` with `coupling_factors_json` from the `drivers` table at the same tick.

---

## What's documented but not implemented

### LLM-as-policy (stretch)

`docs/research/09-maintenance-agent.md` specifies a stretch path: same `decide()` signature, but the body calls an OpenRouter model via `httpx`. Each tick produces `(action, rationale)`, with rationale stored in the event payload. Default model `google/gemma-4-31b-it`, A/B against `anthropic/claude-sonnet-4.6`.

Status: **specified, not built**. The heuristic is the primary; LLM-as-policy is the documented stretch.

### RL maintenance agent

Doc 09 specifies a `MetalJetMaintEnv(gym.Env)` with `Box([0,0,0,0,0], [1,1,1,1e6,1e5])` observation, `Discrete(2)` action, and a reward of `+1 alive / -100 fail / -2 maintenance`.

Status: **specified, explicitly skipped** for the 36-h hackathon. The env spec exists so a judge asking "could you train an RL policy?" gets a precise answer ("yes — `stable-baselines3 PPO` on this env in ~2 h, but we deferred it to keep heuristic A/B clean").

---

## Cross-references

- The engine-side dispatch: [`02-engine-architecture.md`](02-engine-architecture.md) §apply_maintenance.
- The action vocabulary types: [`01-data-contract.md`](01-data-contract.md) §MaintenanceAction.
- Per-component reset rules in detail: each component file in [`components/`](components/).
- The §3.4 sensor pass that produces UNKNOWN: [`02-engine-architecture.md`](02-engine-architecture.md) §build_observed_state.
- Research backing: `docs/research/09-maintenance-agent.md`.
