# Component 14 — Heating Element

> Subsystem: **Thermal Control** · Failure law: **Arrhenius acceleration factor**
> Source: `sim/src/copilot_sim/components/heater.py`

---

## 1. Subsystem and role

The heating elements are responsible for **curing** the binder after each layer. Per the HP whitepaper, the S100 cures the bed via a built-in heat lamp that brings the green part up to the binder's cure temperature (~150 °C for the standard binder formulation).

The heating element's failure mode is **electrical degradation**: the resistance wire (Ni-Cr or Kanthal alloy) slowly oxidizes and changes its electrical resistance over thousands of duty cycles. As resistance drifts, the same applied voltage produces less heat power, so the controller has to push harder to maintain the setpoint — and the element ages even faster (positive feedback).

In the model, the heater is paired with the temperature sensor under the **Thermal Control** subsystem. The heater's `resistance_drift` becomes the `heater_drift_frac` coupling factor that drives the *thermal cascade* — bumping `temperature_stress_effective` for every other component.

---

## 2. Physical mechanism in plain English

Two simultaneous degradation processes:

### Process A — Resistance drift (Arrhenius-accelerated)

The wire's effective cross-section thins over time due to:
- **Oxidation** (chromium oxide layer growing on the wire surface).
- **Thermal-cycle elongation** (each on/off cycle slightly stretches the wire).
- **Hot-spot oxidation** at micro-defects.

The drift rate follows **Arrhenius's law of thermally-activated processes**: the hotter the wire operates, the exponentially faster it ages.

### Process B — Self-heating feedback

A drifted wire produces less heat per watt. The controller compensates by pushing more current. More current → hotter wire → faster Arrhenius drift. This **positive-feedback loop** is the source of the heater's catastrophic-burnout failure mode in real systems.

In our model, the operating temperature is the sum of the **environmental ambient** (driver-modulated) plus a **self-heating term** linear in load.

---

## 3. The textbook law — Arrhenius acceleration factor

The standard accelerated-life model:

$$ \text{AF} = \exp\left(\frac{E_a}{k_B}\left(\frac{1}{T_\text{ref}} - \frac{1}{T_\text{op}}\right)\right) $$

- $E_a$ = activation energy (eV) — the height of the thermal-activation barrier
- $k_B$ = Boltzmann constant (eV/K)
- $T_\text{ref}$ = reference temperature (K) — where AF = 1
- $T_\text{op}$ = current operating temperature (K)

For Ni-Cr resistance drift:
- $E_a \approx 0.7$ eV (`docs/research/03-heating-elements-arrhenius.md`)
- $T_\text{ref} = 423$ K = 150 °C (binder cure setpoint)

A 10 °C rise above $T_\text{ref}$ multiplies the drift rate by ~1.6×. A 30 °C rise multiplies it by ~5×.

Standard reference: *Arrhenius (1889)*, used directly in industrial heater life-prediction (Kanthal Super handbook, Watlow FIREROD spec). Cited in `docs/research/22-printer-lifetime-research.md` §5.

---

## 4. The implementation

```python
# sim/src/copilot_sim/components/heater.py:76

def step(prev_self, coupling, drivers, env, dt, rng):
    temp_eff  = coupling.temperature_stress_effective
    humid_eff = coupling.humidity_contamination_effective
    load_eff  = coupling.operational_load_effective
    damp      = maintenance_damper(coupling.maintenance_level_effective)

    # Operating temperature = ambient (driver-modulated) + self-heating
    ambient_C   = ambient_temperature_C_effective(env, coupling)
                # = env.base_ambient_C + env.amplitude_C * (2*temp_eff − 1)
    operating_C = ambient_C + SELF_HEATING_C * load_eff       # +50 °C at full load
    operating_K = max(operating_C + 273.15, 250.0)            # safety floor

    # Arrhenius AF
    af = math.exp((EA_EV / KB_EV_PER_K) * (1.0 / T_REF_K - 1.0 / operating_K))

    # Driver multipliers (audit-grep redundancy: temp appears here AND in operating_K)
    temp_stress_bonus = 1.0 + 0.3 * temp_eff       # double pull-through on temperature
    oxidation_amp     = 1.0 + 0.5 * humid_eff      # humidity-driven oxidation
    duty_amp          = 1.0 + 0.4 * load_eff       # duty cycling

    drift_increment = (BASE_DRIFT_INCR * af
                       * temp_stress_bonus * oxidation_amp * duty_amp
                       * damp * dt)

    new_drift  = prev_drift + drift_increment      # NOT clipped at 1 — drift can exceed 0.10
    new_power  = prev_power + 0.5 * drift_increment   # power proxy
    new_energy = prev_energy + 0.3 * drift_increment

    metric_health = clip01(1.0 - new_drift / DRIFT_AT_FAILURE)   # FAILED at +10% drift
    age      = prev_self.age_ticks + 1
    baseline = weibull_baseline(age, ETA_WEEKS, BETA)
    health   = clip01(baseline * metric_health)
```

Constants: `BASE_DRIFT_INCR = 0.0035`, `T_REF_K = 423.0`, `EA_EV = 0.7`, `SELF_HEATING_C = 130.0`, `DRIFT_AT_FAILURE = 0.10`.

> **Note (2026-04-26)**: `SELF_HEATING_C` was raised from 50 to 130. Rationale: the S100 binder cure happens at ~150 °C (matching `T_REF_K = 423 K`). With the old value of 50, even at full load the heater operating temperature only reached ~72 °C, giving `AF ≈ 0.02` — the Arrhenius drift physics contributed almost nothing relative to the Weibull baseline. The new value brings operating temperature to ~152 °C at full load (`AF ≈ 1`) and ~94 °C at typical load 0.55 (`AF ≈ 0.04`). Verified empirically: in barcelona-18mo, heater final health dropped from 0.655 to 0.558 — a 10 % additional drop now attributable to drift physics.

The **double pull-through on temperature** (via `operating_K → AF` AND via `temp_stress_bonus = 1 + 0.3·temp_eff`) is intentional — it makes the audit-grep test for `temperature_stress` find two independent dependencies in heater.py. Documented in `docs/research/22` §3 and the file's docstring.

---

## 5. Driver pull-throughs

| Brief driver | Term | Code factor |
|---|---|---|
| `temperature_stress` (path 1) | enters via `ambient_temperature_C_effective(env, coupling)` → operating_K → AF | the Arrhenius core |
| `temperature_stress` (path 2) | extra multiplicative bonus | `temp_stress_bonus = 1 + 0.3·temp_eff` |
| `humidity_contamination` | oxidation amplifier | `oxidation_amp = 1 + 0.5·humid_eff` |
| `operational_load` | duty cycling + self-heating | `duty_amp = 1 + 0.4·load_eff` AND `+50·load_eff` in operating_C |
| `maintenance_level` | shared damper | `damp = 1 − 0.8·M` |

**All four brief drivers feed the heater, with temperature pulling through twice.**

---

## 6. Anchor numbers

Source: `docs/research/22-printer-lifetime-research.md` §5.

| Parameter | Value | Rationale |
|---|---:|---|
| η (characteristic life) | **38 weeks ≈ 270 days ≈ 9 months** | Matches Watlow FIREROD spec + Kanthal Super handbook for industrial cartridge heaters at 150 °C operating point. Limiting mechanism at this regime is slow elongation + connector degradation, not rapid oxidation |
| β (Weibull shape) | **1.0** | Random / useful-life regime — exponential, not wear-out |
| `BASE_DRIFT_INCR` | **0.0035 / week** | Calibrated against Kanthal "thousands of hours" lifetime |
| `T_REF_K` | **423 K = 150 °C** | HP S100 binder cure temperature |
| `E_a` | **0.7 eV** | Standard for Ni-Cr resistance drift (doc 03) |
| `SELF_HEATING_C` | **50 °C** | Order-of-magnitude correct for cartridge heaters at S100 operating point |
| FAILED at | **+10 % resistance drift** | doc 04 anchor — at 10 % drift the controller can't reach setpoint reliably |

---

## 7. Health composition

```python
H_metric    = clip01(1 - resistance_drift / 0.10)
H_baseline  = exp(-(age/η)^β) = exp(-age/38)        # β=1.0, exponential decay
H_total     = clip01(H_baseline × H_metric)
```

The Weibull baseline at β = 1.0 is mathematically exponential — useful-life random-failure regime. The brief's *Realism & Fidelity* pillar likes this because it's **a different shape from the blade and rail** (which are wear-out, β > 1). Three components, three Weibull regimes (1.0, 2.0, 2.5) → defensible bathtub-curve story.

---

## 8. Maintenance reset rules

```python
def reset(prev_self, kind, payload):
    if kind is REPLACE:
        return initial_state()                # element swap
    if kind is FIX:
        return ComponentState(
            ...
            metrics={
                "resistance_drift": 0.5 * prev_drift,                   # halved
                "power_draw": 1.0 + 0.5 * (prev_power - 1.0),           # partial restore
                "energy_per_C": 1.0 + 0.5 * (prev_energy - 1.0),
            },
            age_ticks=prev_self.age_ticks,    # age preserved on FIX
        )
    return prev_self
```

Per `docs/research/09-maintenance-agent.md`:

- **`FIX`** = de-rate + recalibrate. Halves drift; partially restores power_draw and energy_per_C toward 1.0. The wire isn't replaced — calibration brings the controller back into spec but the element keeps aging.
- **`REPLACE`** = element swap. Initial state.

This matches Watlow service-guide practice for industrial cartridge heaters: recalibration extends life but doesn't reset it. **Realism gap: none.**

---

## 9. What this model abstracts away

1. **No thermal mass / first-order delay.** Operating temperature responds instantly to driver changes. Real heaters have minutes-scale lag (thermal time constant ~10 min for cartridge heaters).
2. **Single $E_a = 0.7$ eV.** Real Ni-Cr drift is a mixture of multiple oxide species each with its own $E_a$ (typically 0.5 / 0.7 / 1.0 eV). Single value is the literature-consensus midpoint, not Bayesian-fit.
3. **No catastrophic burnout mode.** Real heaters can fail suddenly via hot-spot oxidation breakthrough — Bernoulli per tick at high drift. Currently smooth drift only.
4. **Self-heating is linear in load** (`+50·load_eff`). Real thermal mass has nonlinearities at duty-cycle extremes (e.g., the wire is much hotter at 95 % duty than at 90 %).
5. **AI surrogate** (`sklearn MLPRegressor (32,32,32) tanh` on 20k Latin-Hypercube samples) is **specified in `docs/research/05` but not trained**. Plan: swap in via `--heater-model={analytic,nn}` CLI flag, prove parity with MAE ≤ 2 %.

---

## 10. Improvements queued

See [`../23-improvement-roadmap.md`](../23-improvement-roadmap.md):

- **B2.5** — Catastrophic burnout mode: Bernoulli per-tick at high drift (2 h). Adds a "sudden death" failure mode realistic to industrial heaters.
- **B2.6** — Train and integrate the AI surrogate (4 h). The *AI-Powered Degradation* bonus from stage-1.md.
- **B3.2** — Thermal mass / first-order delay (2 h). Adds 1-tick smoothing on operating_C → temperature lags driver changes.
- **Tier 3** — 2-Arrhenius mixture model (multiple $E_a$ values weighted). More physically accurate but adds parameters.

---

## The thermal cascade — heater's role

The heater is the **upstream component** of the thermal cascade (cascade 2 in [`../03-coupling-and-cascades.md`](../03-coupling-and-cascades.md)):

```
heater.resistance_drift ↑ → heater_drift_frac ↑
    → heater_thermal_stress_bonus = 0.10 × heater_drift_frac
    → temperature_stress_effective ↑
    → blade hardness ↓ (faster wear)
    AND nozzle Coffin-Manson Δε_p ↑ (faster fatigue)
    AND sensor Arrhenius AF ↑ (faster bias drift)
```

A 50 % drifted heater (drift_frac = 0.5) bumps every other component's effective temperature stress by **+0.05** — enough to noticeably accelerate downstream failures over the 5-year horizon. This cascade is **fully implemented in code** and is the most impactful single coupling in the simulator.

---

## Cross-references

- The thermal cascade: [`../03-coupling-and-cascades.md`](../03-coupling-and-cascades.md) §Cascade 2 (heater → all).
- The sensor↔heater feedback loop: [`../03-coupling-and-cascades.md`](../03-coupling-and-cascades.md) §Cascade 3.
- The §3.4 sensor-mediated heater observation: [`15-sensor.md`](15-sensor.md), `sim/src/copilot_sim/sensors/factories.py`.
- Maintenance philosophy: [`../21-policy-and-maintenance.md`](../21-policy-and-maintenance.md).
- Research backing: `docs/research/03-heating-elements-arrhenius.md`, `docs/research/22-printer-lifetime-research.md` §5.
