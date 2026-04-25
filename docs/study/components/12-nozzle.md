# Component 12 — Nozzle Plate

> Subsystem: **Printhead Array** · Failure laws: **Coffin-Manson + Palmgren-Miner + Poisson clog**
> Source: `sim/src/copilot_sim/components/nozzle.py`

> **The most complex component in the model.** Two parallel damage processes running together, multiple coupling factors consumed, the largest single contribution to pitch-time differentiation.

---

## 1. Subsystem and role

The nozzle plate is the business end of the HP Metal Jet S100's **two printbars × three printheads × 5,280 nozzles per side = 63,360 nozzles total** (HP whitepaper 4AA7-3333ENW). Each nozzle is a thin-film resistor + binder reservoir + orifice. Per the whitepaper, nozzles fire **up to 630 million droplets/second** at 1,200 dpi with **4× redundancy** (any voxel can be served by 4 different nozzles).

Failure of the nozzle plate manifests as:
- **Clogged nozzles** (binder ingress, powder migration, evaporation in idle nozzles) → missing droplets → quality defects.
- **Cracked nozzles** (thermal-fatigue spalling of the orifice plate) → permanent dead nozzles.

In the model, the nozzle is paired with the cleaning interface under the **Printhead Array** subsystem. The nozzle's `clog_pct` is reduced by maintenance FIX (a clean cycle); the cleaning interface's health modulates the nozzle's clog accumulation rate.

---

## 2. Physical mechanism in plain English

Two **independent** damage processes run in parallel — this is what makes the nozzle the most interesting component:

### Process A — Coffin-Manson thermal fatigue

Each binder firing heats the nozzle's thin-film resistor for microseconds (electrothermal pulse), then it cools to bed temperature. Repeated thermal cycling causes plastic strain at every cycle, accumulating fatigue damage per **Palmgren-Miner's linear damage rule**. Eventually the orifice cracks.

### Process B — Poisson clog hazard

Independently of fatigue, individual nozzles randomly clog from:
- **Binder evaporation** in idle nozzles (humidity-driven).
- **Powder migration** into the orifice (contamination-driven).
- **Binder degradation** at high temperatures.

Cleaning cycles (the cleaning interface wipes the plate) clear most clogs but a fraction become permanent.

The **composite health** is `(1 − clog_pct) × (1 − thermal_fatigue)` — both processes have to be near-zero for healthy.

---

## 3. The textbook laws

### Coffin-Manson + Palmgren-Miner

**Coffin-Manson** — cycles-to-failure under plastic strain:

$$ N_f = \left(\frac{\varepsilon_0}{\Delta\varepsilon_p}\right)^{1/c} $$

- $N_f$ = cycles to failure
- $\Delta\varepsilon_p$ = plastic strain per cycle (amplifies with temperature)
- $c$ ≈ 0.5 for thin-film resistors (the standard for HP-class TIJ heads)

**Palmgren-Miner** — linear damage accumulation across variable-amplitude cycling:

$$ D = \sum_i \frac{n_i}{N_{f,i}} $$

- $D$ = damage accumulator (failed at D ≥ 1)
- $n_i$ = cycles at amplitude $i$
- $N_{f,i}$ = cycles-to-failure at that amplitude

Standard reference: *Coffin (1954) + Manson (1953) + Miner (1945)*, used directly in the *Microelectronics Reliability* 2004 paper on thermal-inkjet failure modes (cited in `docs/research/02-nozzle-plate-coffin-manson.md`).

### Poisson clog hazard

Each tick, the number of new clog events is drawn from:

$$ \Delta\text{clog} \sim \text{Poisson}(\lambda \cdot dt) $$

with rate $\lambda$ amplified by humidity and degraded cleaning. Standard for "rare independent events at known average rate" — the textbook hazard model for clogging in inkjet research (Waasdorp et al., RSC Advances 2018).

---

## 4. The implementation

```python
# sim/src/copilot_sim/components/nozzle.py:64

def step(prev_self, coupling, drivers, env, dt, rng):
    temp_eff      = coupling.temperature_stress_effective
    humid_eff     = coupling.humidity_contamination_effective
    load_eff      = coupling.operational_load_effective
    damp          = maintenance_damper(coupling.maintenance_level_effective)
    cleaning_eff  = float(coupling.factors.get("cleaning_efficiency", 1.0))
    heater_bonus  = float(coupling.factors.get("heater_thermal_stress_bonus", 0.0))

    # Process A: Coffin-Manson — Δε_p amplifiers
    cm_temp_factor  = 1.0 + 1.0 * temp_eff + heater_bonus     # drifted heater → bigger Δε_p
    cm_load_factor  = 1.0 + 0.5 * load_eff
    cm_humid_factor = 1.0 + 0.20 * humid_eff
    cycles_scale    = max(env.weekly_runtime_hours / 60.0, 0.0)

    fatigue_increment = (BASE_FATIGUE_INCR
                         * cm_temp_factor * cm_load_factor * cm_humid_factor
                         * cycles_scale * damp * dt)

    # Process B: Poisson clog hazard
    clog_lambda = (CLOG_LAMBDA_BASE
                   * (1.0 + 4.0 * humid_eff)            # humidity dominates
                   * (2.0 - cleaning_eff)               # bad cleaning ~doubles rate
                   * damp)
    clog_count     = int(rng.poisson(max(clog_lambda * dt, 0.0)))
    clog_increment = CLOG_PER_EVENT * clog_count

    # Compose
    new_fatigue = clip01(prev_fatigue + fatigue_increment)
    new_clog    = clip01(prev_clog + clog_increment)
    new_damage  = clip01(prev_damage + fatigue_increment + 0.3 * clog_increment)

    age      = prev_self.age_ticks + 1
    baseline = weibull_baseline(age, ETA_WEEKS, BETA)
    composite = (1.0 - new_clog) * (1.0 - new_fatigue)
    health    = clip01(baseline * composite)
```

`BASE_FATIGUE_INCR = 0.04`, `CLOG_LAMBDA_BASE = 0.05` per week, `CLOG_PER_EVENT = 0.04`. **The Poisson `rng.poisson(...)` draw is the only stochastic element in the standard run** (the rest of the engine is deterministic given a seed).

---

## 5. Driver pull-throughs

| Brief driver | Coffin-Manson term | Poisson clog term |
|---|---|---|
| `temperature_stress` | `cm_temp_factor = 1 + 1.0·temp_eff + heater_bonus` | (indirectly via heater_bonus) |
| `humidity_contamination` | `cm_humid_factor = 1 + 0.20·humid_eff` | `(1 + 4·humid_eff)` — dominant |
| `operational_load` | `cm_load_factor = 1 + 0.5·load_eff` | (indirectly via cycles) |
| `maintenance_level` | shared damper | shared damper |
| `coupling.heater_thermal_stress_bonus` | adds to `cm_temp_factor` | (none) |
| `coupling.cleaning_efficiency` | (none) | `(2 − cleaning_eff)` — pair feedback |

**All four brief drivers feed both processes.** Plus two coupling factors. The audit-grep test verifies monotonicity in each.

---

## 6. Anchor numbers

Source: `docs/research/22-printer-lifetime-research.md` §3.

| Parameter | Value | Rationale |
|---|---:|---|
| η (characteristic life) | **8.5 weeks ≈ 60 days** | The fastest-decaying component. HP whitepaper explicitly markets printheads as "operator-replaceable consumables, not lifetime parts" |
| β (Weibull shape) | **2.0** | Thermal-fatigue wear-out band (matches bearing-fatigue analogue) |
| Base fatigue rate | **0.04 / week** | Calibrated against TIJ literature: 10⁸–10⁹ drops/nozzle warranty |
| Base clog rate | **0.05 events/week** | Small but non-negligible at default |
| Per-event clog increment | **0.04** | One Poisson event ≈ 4 % clog increase |
| FAILED at | **clog ≥ 1.0 OR D ≥ 1** | composite health drops to 0 if either process saturates |

---

## 7. Health composition — the composite story

The nozzle is the only component with **two damage metrics multiplied** before the Weibull baseline:

```
H_metric    = (1 − clog_pct) × (1 − thermal_fatigue)
H_baseline  = exp(-(age/η)^β)
H_total     = clip01(H_baseline × H_metric)
```

So a nozzle at 30 % clog AND 30 % fatigue has metric health `0.7 × 0.7 = 0.49`. A nozzle at 50 % clog OR 50 % fatigue has metric health `0.5`. The composite punishes co-occurrence of both processes — physically correct: a clogged AND fatigued plate is worse than either alone.

---

## 8. Maintenance reset rules

```python
def reset(prev_self, kind, payload):
    if kind is REPLACE:
        return initial_state()                          # full plate swap
    if kind is FIX:
        cleaning_proxy = 0.7                            # ⚠ hardcoded — see below
        new_clog    = clip01(prev_clog * (1 - cleaning_proxy))
        new_fatigue = clip01(prev_fatigue * 0.5)
        new_damage  = clip01(prev_damage * 0.5)
        return ComponentState(
            ...
            metrics={"clog_pct": new_clog,
                     "thermal_fatigue": new_fatigue,
                     "fatigue_damage": new_damage},
            age_ticks=prev_self.age_ticks,              # age preserved on FIX
        )
    return prev_self
```

Per `docs/research/09-maintenance-agent.md`:

- **`FIX`** = clean cycle. Reduces clog by ~70 %, halves thermal fatigue and the Miner accumulator. Age preserved (the plate isn't replaced).
- **`REPLACE`** = full plate swap. Initial state.

> **⚠ The hardcoded `cleaning_proxy = 0.7`** is the **only known realism gap in the maintenance code**. Doc 09 specifies `clog_pct ← clog_pct · (1 − cleaning.efficiency)` — the FIX effectiveness should depend on the **live cleaning interface health at the time of FIX**. Currently it's a constant, so the cleaning↔nozzle adaptive coupling is broken at maintenance time. See [`../23-improvement-roadmap.md`](../23-improvement-roadmap.md) §B1.2 for the 10-min fix.

---

## 9. What this model abstracts away

1. **63,360 nozzles → one composite metric**. HP has 4× redundancy + an optical drop detector that flags failed nozzles. Real failure is "X % of nozzles dead" (typically replacement at 1–5 %). Currently we collapse all of this to a single `clog_pct` ∈ [0,1].
2. **Single Poisson process for clogs**. Real binder-jet clogging has at least three independent mechanisms: binder ingress (humidity-driven), powder migration (contamination-driven), binder evaporation (idle-driven). One Poisson distribution stands in for all three.
3. **Hardcoded `cleaning_proxy = 0.7` in FIX** — see §8.
4. **Thermal cycles use `weekly_runtime_hours/60`** instead of `Environment.start_stop_cycles`. Coffin-Manson's true input is *thermal cycles*, not runtime hours. Real demo is hundreds of on/off duty cycles per build, thousands per week.
5. **No `nozzles_failed_pct` observable** for HP's optical drop detection — that signal isn't exposed in the simulator's observed view.

---

## 10. Improvements queued

See [`../23-improvement-roadmap.md`](../23-improvement-roadmap.md):

- **B1.2** — Wire `cleaning_efficiency` into nozzle FIX (10 min). Highest-priority quick win for the printhead pair.
- **B1.6** — Add nozzle→cleaning reverse arrow: clog raises wiper wear (15 min).
- **B2.1** — Multi-mechanism clog model: split the single Poisson into three independent processes (binder ingress, powder migration, evaporation), each with its own driver dependency (3 h). Matches the *Microelectronics Reliability 2004* literature.
- **B2.2** — Add `nozzles_failed_pct` metric + `OpticalDropDetector` sensor model (4 h). HP's actual service-station signal becomes a first-class observable.

---

## Cross-references

- Nozzle's role in the cascade map: [`../03-coupling-and-cascades.md`](../03-coupling-and-cascades.md) §Cascade 1 (powder destination), §Cascade 4 (cleaning ↔ nozzle pair), §Cascade 2 (heater thermal stress).
- The §3.4 sensor view: [`15-sensor.md`](15-sensor.md).
- Maintenance philosophy: [`../21-policy-and-maintenance.md`](../21-policy-and-maintenance.md).
- Research backing: `docs/research/02-nozzle-plate-coffin-manson.md`, `docs/research/22-printer-lifetime-research.md` §3.
