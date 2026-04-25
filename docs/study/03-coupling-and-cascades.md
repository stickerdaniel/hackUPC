# 03 — Coupling and Cascades

> The single most important file for understanding *why this is a digital twin and not six independent decay curves*.

---

## The architectural rule

> **Cross-component effects flow through one place: `engine/coupling.py`. No component reads another component's state directly.**

This rule is what makes the simulator `coupled` instead of `parallel`. The mechanism is a single `CouplingContext` object, built once per tick from the immutable `t-1` `PrinterState`, and passed by reference to every component step function. Each component reads `coupling.*_effective` and `coupling.factors[…]` — never `prev_state.components[other_id].metrics[…]`.

Two design dividends:

1. **Update-order independence** by construction. Reordering the component step calls cannot change the result.
2. **Single attribution channel**. The 10 named factors are persisted as `coupling_factors_json` on the historian's `drivers` table per tick, so any failure analysis can walk back through the cascade chain without re-running the engine.

The function: `engine/coupling.py:36 build_coupling_context(prev, drivers, env, dt) -> CouplingContext`.

---

## The CouplingContext shape

```python
@dataclass(frozen=True, slots=True)
class CouplingContext:
    temperature_stress_effective: float       # raw temp + cross-component bumps
    humidity_contamination_effective: float   # raw humid + cross-component bumps
    operational_load_effective: float         # raw load + cross-component bumps
    maintenance_level_effective: float        # raw maint, just clipped
    factors: Mapping[str, float]              # 10 named cross-component terms
```

The four `*_effective` drivers are what every component step actually consumes. The `factors` dict is the audit trail — every named term that fed the bumps.

---

## The 10 named factors

Locked by the test `test_engine_step_produces_six_components_and_observed_shape` (asserts these names are a subset of `coupling.factors.keys()`):

| Factor | Formula | Source component | Consumer |
|---|---|---|---|
| `powder_spread_quality` | `clip01(1 − 0.6·blade_wear − 0.3·rail_misalignment)` | blade + rail | feeds `humidity_contamination_effective` |
| `blade_loss_frac` | `clip01(blade.wear_level)` | blade | dashboard / cascade attribution |
| `rail_alignment_error` | `clip01(rail.misalignment)` | rail | dashboard / cascade attribution |
| `heater_drift_frac` | `clip01(heater.resistance_drift / 0.15)` | heater | feeds `heater_thermal_stress_bonus` |
| `heater_thermal_stress_bonus` | `0.10 · heater_drift_frac` | derived | bumps `temperature_stress_effective` |
| `sensor_bias_c` | `sensor.bias_offset` (signed) | sensor | feeds `control_temp_error_c` |
| `sensor_noise_sigma_c` | `sensor.noise_sigma` | sensor | observed-state noise generation |
| `control_temp_error_c` | `= sensor_bias_c` | derived | bumps `temperature_stress_effective` |
| `cleaning_efficiency` | `clip01(cleaning.cleaning_effectiveness)` | cleaning | divides nozzle Poisson rate |
| `nozzle_clog_pct` | `clip01(nozzle.clog_pct)` | nozzle | bumps `operational_load_effective` |

The naming is **stable**. Components depend on exact spelling, and the historian schema's `coupling_factors_json` column is keyed by these strings. Test `test_engine_step.py:44` will fail if any of these names disappears.

---

## How the four effective drivers are built

```python
# engine/coupling.py:77 (ish)

heater_drift_frac      = clip01(heater_drift / 0.15)
powder_spread_quality  = clip01(1 - 0.6*blade_wear - 0.3*rail_misalignment)
heater_thermal_stress_bonus = 0.10 * heater_drift_frac
control_temp_error_c   = sensor_bias

temperature_stress_effective = clip01(
    drivers.temperature_stress
    + heater_thermal_stress_bonus
    + 0.05 * abs(control_temp_error_c)
)

humidity_contamination_effective = clip01(
    drivers.humidity_contamination
    + 0.20 * blade_wear
    + 0.10 * (1.0 - powder_spread_quality)
)

operational_load_effective = clip01(
    drivers.operational_load
    + 0.15 * nozzle_clog_pct
)

maintenance_level_effective = clip01(drivers.maintenance_level)
```

**Sub-unity bumps everywhere** — every coefficient is `< 1` so the system can't explode. Even at full degradation (every component at total failure), the maximum effective driver is `clip01(raw + bumps) ≤ 1` by construction. This bounded-by-design property is what makes the model defensible under chaos overlay (Poisson temperature spikes etc.) without runaway feedback.

---

## The five cascade arrows

Cascades are the **emergent stories** the model tells. Below: the chain in plain English, the math chain in code, and the verdict on whether the implementation matches what the README claims.

### Cascade 1 — Powder cascade (Recoating → Printhead)

> **In English**: a worn blade or misaligned rail spreads bad powder; bad powder traps moisture and dirt; that contamination raises the nozzle's clog rate.

**Forward chain**:
```
blade_wear ↑ + rail_misalignment ↑
    → powder_spread_quality ↓                        (engine/coupling.py)
    → humidity_contamination_effective ↑             (engine/coupling.py)
    → nozzle Poisson clog rate ↑ via λ ∝ humid_eff   (components/nozzle.py:100)
```

**Reverse arrow**: none by design. The powder spread is one-directional from upstream parts to downstream parts. ✓ Fully implemented.

### Cascade 2 — Thermal cascade (Thermal → all)

> **In English**: a drifted heater overshoots its setpoint, raising the effective temperature stress for everything else; that accelerates blade wear, nozzle thermal fatigue, and the sensor's own drift.

**Forward chain**:
```
heater_drift ↑ → heater_drift_frac ↑
    → heater_thermal_stress_bonus ↑                  (= 0.10 × heater_drift_frac)
    → temperature_stress_effective ↑                 (engine/coupling.py:77)
    → blade hardness ↓                               (components/blade.py — temp_eff term)
      AND nozzle Coffin-Manson Δε_p ↑                (components/nozzle.py — cm_temp_factor)
      AND sensor Arrhenius AF ↑                      (components/sensor.py — operating_K)
```

**Reverse arrow**: none by design. Heater drift drives thermal stress, not the other way. ✓ Fully implemented.

### Cascade 3 — Sensor ↔ Heater (Thermal pair, **closed loop**)

> **In English**: the temperature sensor lies → the heater controller defends a wrong setpoint → the heater overshoots → it ages faster → the drifted heater raises thermal stress → which accelerates the sensor's own drift. *This is the feedback loop the §3.4 story rides on.*

**Forward chain (sensor → heater)**:
```
sensor.bias_offset ↑ → sensor_bias_c ↑
    → control_temp_error_c = sensor_bias_c           (engine/coupling.py)
    → temperature_stress_effective += 0.05·|error|   (engine/coupling.py)
    → heater operating_C ↑                           (components/heater.py)
    → heater Arrhenius AF ↑                          (components/heater.py)
    → heater drift_increment ↑                       (components/heater.py)
```

**Reverse chain (heater → sensor)** — claimed in README, status in code:
- The README says: `dbias/dt *= 1 + 0.5 · heater_drift_frac` (explicit term in sensor.py).
- **The code does NOT have this explicit term**. The reverse arrow closes only indirectly through `temperature_stress_effective` (which already includes `heater_thermal_stress_bonus`).

Verdict: ⚠ **One-way explicit, two-way implicit**. The loop closes mathematically (sensor sees heater drift via the shared `temp_stress_eff`), but the README oversells it. See [`23-improvement-roadmap.md`](23-improvement-roadmap.md) §B1.3 for the 5-minute fix that makes it explicitly two-way.

### Cascade 4 — Cleaning ↔ Nozzle (Printhead pair)

> **In English**: clogged nozzles need more cleaning, and a degraded cleaning interface leaves more residual clogs.

**Forward chain (cleaning → nozzle)**:
```
cleaning.cleaning_effectiveness ↓ → cleaning_efficiency factor ↓
    → nozzle Poisson clog rate λ ∝ (2 − cleaning_efficiency)    (components/nozzle.py:100)
```

**Reverse chain (nozzle → cleaning)** — claimed in README, status in code:
- The README says: `nozzle.clog_pct → cleaning.wear_factor += 0.4 × clog_pct/100`.
- **The code does NOT have this term in cleaning.py**. The cleaning step doesn't read `coupling.factors["nozzle_clog_pct"]`.

Verdict: ⚠ **Forward only**. See [`23-improvement-roadmap.md`](23-improvement-roadmap.md) §B1.6 for the 15-minute fix.

There's also a **maintenance-time arrow** the README describes: nozzle FIX should clean clog by `(1 − cleaning_efficiency)`. The code uses a hardcoded `cleaning_proxy = 0.7` instead. See [`23-improvement-roadmap.md`](23-improvement-roadmap.md) §B1.2.

### Cascade 5 — Rail ↔ Blade (Recoating pair)

> **In English**: a misaligned rail makes the blade scrape unevenly; a worn blade produces vibration and contamination that wears the rail bearings faster.

**Forward + reverse**: the README claims `rail.alignment_error → blade.k_eff *= (1 + 0.5·alignment)` and `blade.loss_frac → rail accumulator += 0.05 µm/h`.
- **Neither term is in the code**. The blade and rail step functions don't read each other's coupling factors.
- They meet only through the **shared output sink** `powder_spread_quality = 1 − 0.6·blade_wear − 0.3·rail_misalignment`. This is a one-way contribution, not a bidirectional coupling.

Verdict: ⚠ **No direct coupling**. See [`23-improvement-roadmap.md`](23-improvement-roadmap.md) §B2.3 for the 3-hour fix that adds an explicit `carriage_friction` factor.

---

## Summary table — what's actually in code today

| Cascade | Forward arrow | Reverse arrow |
|---|---|---|
| Powder (A → B) | ✓ blade+rail → powder → humid_eff → nozzle | (one-way by design) |
| Thermal (C → all) | ✓ heater → temp_stress_eff → all | (one-way by design) |
| Sensor ↔ Heater | ✓ sensor → control_err → heater AF | ⚠ implicit only via temp_stress_eff (no explicit `heater_drift_frac` term in sensor.py) |
| Cleaning ↔ Nozzle | ✓ cleaning_eff → nozzle Poisson rate | ⚠ missing |
| Rail ↔ Blade | (only via powder_spread_quality output sink) | ⚠ missing |

**For the pitch**: defensible to claim "one closed feedback loop (sensor↔heater) and four cascades that propagate damage between subsystems". Don't claim "three two-way loops" verbatim — that oversells.

---

## A worked example: nozzle CRITICAL at tick 47

Suppose the dashboard's panel 2 shows nozzle hits CRITICAL at tick 47. Here's how to walk back through the historian's `coupling_factors_json`:

```sql
SELECT coupling_factors_json
FROM drivers
WHERE run_id = 'barcelona-baseline-20260425-1' AND tick = 47;
```

Returns something like:
```json
{
  "powder_spread_quality": 0.71,
  "blade_loss_frac": 0.42,
  "rail_alignment_error": 0.18,
  "heater_drift_frac": 0.05,
  "heater_thermal_stress_bonus": 0.005,
  "sensor_bias_c": 0.34,
  "sensor_noise_sigma_c": 0.08,
  "control_temp_error_c": 0.34,
  "cleaning_efficiency": 0.62,
  "nozzle_clog_pct": 0.81
}
```

The story:
1. `nozzle_clog_pct = 0.81` — nozzle is past CRITICAL (0.20).
2. The Poisson rate at this tick was `λ ∝ humid_eff × (2 − cleaning_eff)`.
3. `cleaning_efficiency = 0.62` — the cleaner is mid-life, so `(2 − 0.62) = 1.38` (38 % above baseline).
4. `humidity_contamination_effective` (queryable as a separate column) was high because:
5. `powder_spread_quality = 0.71` — degraded, contributing `0.10 × 0.29 = 0.029` to humid_eff.
6. `blade_loss_frac = 0.42` — at 42 % wear; that's the bigger contribution: `0.20 × 0.42 = 0.084`.

So the chain is `blade_wear (0.42) → powder degradation → humidity_contamination_effective ↑ → cleaning_efficiency degraded → Poisson clog rate doubled → nozzle CRITICAL`.

The dashboard's panel 2 ranks the top-3 factors by absolute magnitude and renders this chain as a small graph. The CLI version is `copilot-sim inspect <run_id> --failure-analysis`.

---

## Why this matters more than it looks

The brief's *Realism & Fidelity* (Stage 2 bonus pillar) explicitly says: "every failure event traceable to its root input drivers". The `coupling_factors_json` column is **purpose-built** for that requirement. Without it, root-cause analysis would require re-running the simulation. With it, a Phase 3 chatbot can answer "why did the nozzle fail in week 47?" with a single SQL row + an attribution chain.

The 10-factor design is the project's **strongest Stage 2 talking point** for the *Systemic Integration* and *Realism & Fidelity* pillars combined.
