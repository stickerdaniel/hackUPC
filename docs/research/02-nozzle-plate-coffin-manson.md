# Nozzle Plate — Coffin-Manson Thermal Fatigue + Poisson Clog Hazard

> Failure model for the HP Metal Jet S100 thermal-inkjet **Nozzle Plate**.
> Two coupled processes: low-cycle thermal fatigue (Coffin-Manson + Miner)
> and stochastic clogging (Poisson hazard rate).
> Last updated: 2026-04-25.

---

## TL;DR

- **Thermal fatigue** uses Coffin-Manson with a **Miner's-rule** damage accumulator.
  Per cycle: `Δε_p = ε_0 · (1 + k_T · |ΔT|)`, then `N_f = (Δε_p / 2·ε_f')^(1/c)`
  with **ε_f' = 0.30**, **c = -0.55**, **ε_0 = 5e-3**, **k_T = 0.05**.
- **Clogging** is a non-homogeneous Poisson process with hazard rate
  `λ(t) = λ_0 · (1 + α·|ΔT|) · (1 + β·C) / M` where
  **λ_0 = 5e-4 /tick**, **α = 0.08 /°C**, **β = 2.5**, M = maintenance level.
  Per-tick clog increment: `Δclog% = 100 · (1 - e^(-λ·dt))`.
- **Composite health:** `H = (1 - clog%/100) · (1 - D)` where D = Miner damage.
  Status: `H ≥ 0.75 FUNCTIONAL`, `0.5–0.75 DEGRADED`, `0.2–0.5 CRITICAL`, `< 0.2 FAILED`.
- Tuned so a "nominal" 8-hour print run reaches `DEGRADED`, an "abusive" run
  (high humidity + temp drift, no maintenance) reaches `CRITICAL` inside the
  hackathon demo window (~3-5 minutes of accelerated sim time).

---

## Background

### Coffin-Manson (low-cycle thermal fatigue)

The Coffin-Manson law relates **plastic strain amplitude** to **cycles to failure** in
the low-cycle regime (N_f < 10⁴), which is exactly where thermal-inkjet nozzles live:
each firing event flashes the resistor to ~300°C in microseconds, then the plate
re-equilibrates. Standard form:

```
Δε_p / 2 = ε_f' · (2 N_f)^c        ⇒        N_f = (Δε_p / (2·ε_f'))^(1/c)
```

- **Δε_p** — plastic strain range per cycle (dimensionless).
- **ε_f'** — fatigue ductility coefficient, ≈ true fracture strain. Ductile metals ~1.0,
  strong metals ~0.5; for printhead nickel/silicon alloys we are in the brittle range.
- **c** — fatigue ductility exponent, empirically **−0.5 to −0.7**. SnAgCu solder
  (the closest electronic-packaging analog under thermal cycling) is c ≈ −0.57.
- **N_f** — cycles to failure at that strain amplitude.

For variable thermal load we use **Palmgren-Miner linear damage**:
`D = Σ n_i / N_f,i`, fail at `D = 1`. Each tick contributes `1/N_f(ΔT_tick)`.

### Poisson clog hazard

Clogs are random events caused by binder drying at the nozzle tip, powder ingestion,
and contaminant rehydration failures — all of which are **stochastic point events**,
not gradual wear. The natural model is a non-homogeneous Poisson process: the
**hazard rate λ(t)** is the instantaneous probability per unit time, and gaps between
clog events are exponentially distributed with mean 1/λ. λ rises with anything that
desiccates the binder (temp drift) or feeds particulates (contamination).

---

## Decision

### Thermal fatigue (per tick)

```python
# Δε_p grows with |ΔT| from optimal printhead temperature
delta_eps_p = eps_0 * (1 + k_T * abs(temp_stress - T_optimal))
N_f         = (delta_eps_p / (2 * eps_f_prime)) ** (1 / c)
fatigue_damage += dt_cycles / N_f          # Miner accumulator, [0,1]
```

| Param          | Value | Justification |
| -------------- | ----- | ------------- |
| `eps_f_prime`  | 0.30  | Brittle/ceramic-bonded plate, lower than ductile metal |
| `c`            | -0.55 | Mid-range LCF exponent, matches SnAgCu thermal-cycling analog |
| `eps_0`        | 5e-3  | Baseline plastic strain at nominal ΔT (5 m-strain) |
| `k_T`          | 0.05  | 5% strain growth per °C deviation |
| `T_optimal`    | 60°C  | Plate steady-state target |
| `dt_cycles`    | tick · firings/tick | Convert sim tick to firing cycles |

At nominal (ΔT=0): `Δε_p=0.005`, `N_f ≈ 1.6e4` cycles → slow drift.
At ΔT=20°C: `Δε_p=0.010`, `N_f ≈ 2.5e3` cycles → ~6× faster damage.

### Clog hazard (per tick)

```python
lam = lam_0 * (1 + alpha * abs(temp_stress - T_optimal)) \
            * (1 + beta * contamination) / max(maintenance, 0.1)
p_clog_increment = 1 - exp(-lam * dt)      # Poisson exceedance prob
clog_pct = min(100, clog_pct + 100 * p_clog_increment)
```

| Param  | Value     | Justification |
| ------ | --------- | ------------- |
| `lam_0`| 5e-4 /tick| Baseline ~1 clog event per ~2000 ticks of clean ops |
| `alpha`| 0.08 /°C  | Doubles hazard at ΔT≈12°C |
| `beta` | 2.5       | Triples hazard at contamination=0.8 |

### Composite health

```
H = (1 - clog_pct/100) · (1 - fatigue_damage)
```

Multiplicative because **either** failure mode can kill the head independently
(a 100% clogged but mechanically sound plate is just as dead as a fractured plate
with clean nozzles). Both metrics also remain individually inspectable in the UI.

### Status thresholds

| Health H        | Status      |
| --------------- | ----------- |
| `H ≥ 0.75`      | FUNCTIONAL  |
| `0.50 ≤ H < 0.75` | DEGRADED  |
| `0.20 ≤ H < 0.50` | CRITICAL  |
| `H < 0.20` or `clog_pct ≥ 95` or `D ≥ 1` | FAILED |

---

## Why this fits our case

- **Two different physics, one component.** Coffin-Manson captures the deterministic
  thermomechanical wear of the silicon/nickel plate; the Poisson model captures the
  stochastic, environment-driven clogging — these really are independent failure
  paths in published printhead failure analyses (electromigration/thermal-stress
  cracking on the heater side, drying/particulate clogging on the nozzle side).
- **All four drivers wired in.** Temp Stress feeds both `Δε_p` and `λ`. Humidity/
  Contamination feeds `λ` only (drying and powder ingress). Operational Load
  advances `dt_cycles`. Maintenance Level scales `λ` down (cleaning resets
  contamination's effect on hazard).
- **Hackathon-tunable.** `ε_0`, `λ_0`, `α`, `β` are dimensionless knobs — we can
  ship realistic-looking degradation curves in minutes.
- **Cascading-failure ready.** A worn Recoater Blade increases `contamination`,
  which raises `λ` here — exactly the cascade the brief asks for as a bonus.
- **Deterministic with a seed.** Poisson draws use a seeded RNG so reruns match.

---

## References

1. **Coffin-Manson formulation & exponent ranges** — Wikipedia, *Low-cycle fatigue*.
   <https://en.wikipedia.org/wiki/Low-cycle_fatigue>
2. **c values for solder under thermal cycling (SnAgCu c ≈ −0.57)** — *Thermal Cycling Life
   Prediction of Sn-3.0Ag-0.5Cu Solder Joint*, PMC4121147.
   <https://pmc.ncbi.nlm.nih.gov/articles/PMC4121147/>
3. **Failure mechanisms in thermal inkjet printheads** (electromigration, thermal-
   stress cracking, cavitation) — de Jong et al., *Microelectronics Reliability*.
   <https://www.sciencedirect.com/science/article/abs/pii/S0026271404005165>
4. **Nozzle clogging in binder jet 3D printers** — *A Study for Improving the Durability
   of Print Heads in Binder Jet 3D Printers*, J. Korea Safety Mgmt & Sci.
   <https://www.koreascience.kr/article/JAKO202324172302377.page>
5. **Inkjet AM clogging modes (drying, particulate, rehydration)** — ImageXpert,
   *Three Common Issues With Inkjet Additive Manufacturing*.
   <https://imagexpert.com/three-common-issues-with-inkjet-additive-manufacturing-and-how-to-address-them/>
6. **Palmgren-Miner linear damage rule** — Quadco Engineering, *Palmgren-Miner Rule*.
   <https://www.quadco.engineering/en/know-how/an-overview-of-the-palmgren-miner-rule.htm>
7. **Constant-hazard ↔ Poisson process equivalence** — NIST Engineering Statistics
   Handbook §8.1.7.1, *Homogeneous Poisson Process*.
   <https://www.itl.nist.gov/div898/handbook/apr/section1/apr171.htm>

---

## Open questions

- **Firings per tick.** Need a calibrated `dt_cycles` so an 8h job ≈ realistic
  drum count. Pick from S100 spec sheet or assume 20 kHz firing × duty cycle.
- **Maintenance event semantics.** A "purge" should reset `clog_pct` partially
  (say ×0.3) but **not** `fatigue_damage` (irreversible). Confirm with team.
- **Clog recovery vs. permanent.** Some clogs auto-clear; should `clog_pct` decay
  slightly when contamination is low? Defaulting to monotonic for simplicity.
- **T_optimal value.** 60°C is a guess for plate steady-state; verify against any
  HP-published spec or set from the simulator's thermal-control loop output.
- **Cross-coupling with Heating Elements.** If heater drift raises plate temp,
  do we feed that back into `temp_stress` for the nozzle, or treat them
  independently? Recommend coupling for the cascade-failure bonus.
