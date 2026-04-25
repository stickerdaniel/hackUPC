# 22 — Realism Audit

> What's defensible without qualification, what's an honest abstraction, and what's an oversell. Read this before answering any judge question that starts with "is your simulation realistic?".

---

## Verdict in one paragraph

The model is **substantively realistic for its scope**. Six textbook failure laws, parameters cited to industry sources (NSK / THK / HP whitepaper / Kanthal / Omega RTD / ScienceDirect), status thresholds in the right ballpark for industrial alerting, maintenance semantics that match real consumable-vs-repairable practice, all four drivers wired into all six components, and a coupled engine that won't explode under any input. It is *not* a finite-element model and doesn't claim to be — it operates at the **part-level degradation layer** the brief explicitly scopes (`TRACK-CONTEXT.md §5: "we model part-level degradation, not the full machine physics"`). Within that scope, the largest realism gaps are: (1) three documented cascades are one-way only in code; (2) a 5-pp threshold drift between docs and code (now fixed, see §C.4); (3) the live-weather bonus and the AI surrogate are researched but not in the demo path; (4) one cleaning-coupling detail uses a hardcoded constant instead of reading the live `cleaning_efficiency` factor.

---

## A. What the model gets right (defensible without qualification)

### A.1 Each law is the textbook model for its mechanism

Each of the six laws is the *standard* law for its failure mechanism, not a custom invention:

| Component | Law | Why this is the right choice |
|---|---|---|
| Blade | Archard wear `V = k·F·s/H` | Universal abrasive-sliding-wear law since 1953. ScienceDirect papers on PBF recoater blades use this directly. |
| Rail | Lundberg-Palmgren cubic `L₁₀ ∝ (C/P)³` | The standard fatigue-life model used by NSK and THK in their own datasheets. Literally how rolling-element bearings are spec'd. |
| Nozzle | Coffin-Manson + Palmgren-Miner | Standard for low-cycle thermal fatigue of thin-film resistors; cited in Microelectronics Reliability 2004 paper on TIJ failure modes. The Poisson clog overlay matches Waasdorp et al. RSC 2018 hazard model. |
| Cleaning | Power-law wear-per-cycle | Industrial wiper-station maintenance literature (Digiprint, Splashjet) treats wipers as cycle-counted consumables. |
| Heater | Arrhenius AF | The textbook acceleration model for thermally activated material degradation. `Eₐ = 0.7 eV` matches Ni-Cr resistance-drift literature. |
| Sensor | Arrhenius bias drift | Same activation-energy regime applies to PT100 RTD elements. HW-group + Omega + HGS publish drift rates that anchor the chosen `0.03 °C/week` base. |

If a judge says *"why this law and not [other]?"*, the answer in every case is *"because that is the standard reliability-engineering model for that failure mechanism; we're not inventing physics, we're applying it"*.

### A.2 The η lifetime values are individually cited to industry

Per `docs/research/22-printer-lifetime-research.md`:

| Component | Code η | Cited target | Source |
|---|---:|---|---|
| Blade | 17 weeks (= 119 d) | 120 d | Inside Metal AM 2024, ScienceDirect S221384632200102X |
| Rail | 77 weeks (= 539 d) | 540 d | NSK + THK datasheets, Zenda Motion, Rollon L10 study |
| Nozzle | 8.5 weeks (= 59.5 d) | 60 d | HP whitepaper 4AA7-3333ENW + Microelectronics Reliability 2004 |
| Cleaning | 50 weeks (calendar shelf-life floor) | 75 d (use-driven) | Splashjet, Digiprint USA — power-law dominates over time |
| Heater | 38 weeks (= 266 d) | 270 d | Kanthal Super handbook + Watlow FIREROD spec |
| Sensor | n/a (no Weibull) | hard fail at \|bias\| > 5 °C | HW-group, Omega RTD capsules |

**Match accuracy is 1-day per component on five of six.** That's unusually rigorous for a hackathon.

### A.3 Maintenance reset semantics match real industrial practice

Cross-checked component-by-component against `docs/research/09-maintenance-agent.md`:

| Component | Industrial practice | Code implementation | Verdict |
|---|---|---|---|
| **Blade** | Consumable. Streaking → swap. No field repair. | FIX routes to REPLACE (full reset) | ✓ Correct |
| **Rail** | Re-greasing recovers lubricant + corrosion film; raceway pitting is permanent. | FIX zeros friction halve, **leaves alignment_error untouched**; REPLACE full reset | ✓ Correct |
| **Nozzle** | Plate cleaning recovers most clog; thermal-fatigue damage is partly residual. | FIX reduces clog by 70 %, halves fatigue and damage; REPLACE full reset | ✓ Mostly correct (one quibble in §C.2) |
| **Cleaning** | Wiper blade is a consumable; full station replaced annually. | Both FIX and REPLACE return initial_state | ✓ Correct |
| **Heater** | Recalibration / de-rating partially recovers drift; element swap is the only true reset. | FIX halves drift, partial restore of power_draw + energy_per_C; REPLACE full reset | ✓ Correct |
| **Sensor** | Calibration zeros bias offset; connector noise is irreversible without replacement. | FIX zeros bias_offset, **leaves noise_sigma**; REPLACE full reset | ✓ Correct |

**Five of six are perfectly aligned with industry practice; the sixth (nozzle) has the hardcoded `cleaning_proxy = 0.7` issue documented in §C.2.**

### A.4 The deterministic-RNG invariants

Per-component, per-tick generators keyed by a `blake2b` digest (`engine/aging.py:108`) — independent of `PYTHONHASHSEED`, robust against parallelism. Chaos arrivals pre-rolled at scenario load with a separate RNG tag (`drivers_src/chaos.py:46`). OU humidity owns its state on the generator (`drivers_src/generators.py:73`). Same seed = byte-identical historian. Tests enforce both invariants (`tests/engine/test_rng_determinism.py`). This is *much* more rigorous than typical hackathon code.

### A.5 The §3.4 sensor-fault layer is a real differentiator

The brief specifically opens this twist; the team built it end-to-end:

- True/observed split lives in the type system (`domain/state.py`).
- Heater observations actually flow through the temperature sensor (`SensorMediatedHeaterModel` in `sensors/factories.py:97`) — when the sensor degrades, the heater's observed picture diverges from its true state.
- The heuristic policy reads observed state only (`policy/heuristic.py:48`), so it can be fooled by a drifting sensor exactly like a real operator. The §3.4 sensor-fault story is a closed loop in code.

This is the single strongest "Realism & Fidelity" pillar argument you have.

> **Update (2026-04-26)**: the §3.4 story originally only fired at very long horizons because both heater and sensor used `operating_K = ambient_only` for their Arrhenius math, so AF stayed near zero. Two fixes applied (see [`23-improvement-roadmap.md`](23-improvement-roadmap.md) §B1.7–B1.8): heater `SELF_HEATING_C` raised from 50 to 130 °C (matches S100 binder cure ~150 °C); sensor's `operating_K` calculation now mirrors the heater's self-heating term. Empirical verification: phoenix-18mo (78 ticks) now produces sensor DEGRADED at tick 77 with `sensor_bias_c = 0.77 °C`, and the bias appears as a top-3 cascade factor at the nozzle's FAILED transition. Barcelona conditions still show stable sensor behaviour, which is the right what-if story (different climate → different failure modes).

---

## B. Honest abstractions (defensible with one sentence of context)

### B.1 Single-scalar component metrics

We collapse "63,360 nozzles" to one `clog_pct` ∈ [0,1]. We collapse "300+ rolling elements in the rail bearing" to one `misalignment` ∈ [0,1]. The brief explicitly sets the scope at "part-level degradation, not the full machine physics" (`TRACK-CONTEXT.md §5`). The single-scalar abstraction is faithful to that scope.

### B.2 Single Eₐ for Arrhenius components

Real Ni-Cr resistance drift has multiple oxide species, each with its own activation energy (typically 0.5 / 0.7 / 1.0 eV). We use Eₐ = 0.7 eV (the literature consensus midpoint) for both heater and sensor. A 2-Arrhenius mixture model is in [`23-improvement-roadmap.md`](23-improvement-roadmap.md) Tier 3 but doesn't change the demo story.

### B.3 Single-sign sensor bias

Real PT100 RTDs can drift either direction. We force `+1` (sensor reads consistently low). This is *what makes the heater overshoot* in the §3.4 story — flipping the sign would change the failure dynamics. A randomized sign at `initial_state()` is in B2.4 of the roadmap.

### B.4 Sliding distance from runtime hours

Blade Archard wear uses `weekly_runtime_hours / 60` as a proxy for sliding distance. Real sliding distance depends on `builds_per_week × layers × bed_traversal`. The runtime-hour proxy is monotone in the right direction but doesn't capture build-size effects.

### B.5 Polynomial fit on rail load-life

`load_amplifier = 1 + 4·load_eff³` is a polynomial fit, not literal `(C/P)³ × hours`. The cubic shape is preserved (audit-grep tests verify monotonicity in load), but the exact L₁₀ formula would be more rigorous. Polynomial fit avoids the calibration question of "what is C for our virtual rail?".

---

## C. Things to know (oversells, drifts, and gaps)

### C.1 Three of the five documented cascades are one-way only

`README.md` and `docs/research/05` claim **"three two-way loops + two cross-subsystem cascades"** (rail↔blade, cleaning↔nozzle, sensor↔heater). Cross-checking against component step functions:

| Loop | Forward arrow | Reverse arrow | Verdict |
|---|---|---|---|
| **Sensor ↔ Heater** | sensor_bias → control_temp_error_c → bumps temp_stress_eff → heater AF ↑ ✓ | hotter heater → faster sensor element aging via `dbias/dt *= 1 + 0.5·heater_drift_frac` | ⚠ Reverse arrow NOT in `sensor.py` — bias_increment doesn't read `heater_drift_frac`. The sensor *indirectly* sees heater drift through `temperature_stress_effective` (which does include `heater_thermal_stress_bonus`), but the explicit term the docs promise is missing. |
| **Cleaning ↔ Nozzle** | cleaning_efficiency → nozzle Poisson `λ × (2 − cleaning_eff)` ✓ | nozzle.clog_pct → cleaning.wear_factor `+= 0.4 × clog_pct/100` | ⚠ Reverse arrow NOT in `cleaning.py` — cleaning step doesn't read nozzle metrics. |
| **Rail ↔ Blade** | (the README claims two arrows) | (the same) | ⚠ Both arrows missing — they only meet through `powder_spread_quality`, which is a *shared output sink*, not a direct two-way coupling. |
| **Powder cascade (A → B)** | blade_wear + rail → powder_spread_quality ↓ → humidity_contamination_eff ↑ → nozzle Poisson rate ↑ ✓ | (one-way by design) | ✓ Fully implemented |
| **Thermal cascade (C → all)** | heater_drift → heater_thermal_stress_bonus → temp_stress_eff ↑ → blade hardness ↓, nozzle CM Δε_p ↑, sensor AF ↑ ✓ | (one-way by design) | ✓ Fully implemented |

**What this means for the pitch**: defensible to claim *"the dominant loop is the sensor-heater pair; the others are forward cascades that meet in shared output sinks"*. Don't claim "three two-way loops" verbatim — that oversells.

### C.2 Nozzle FIX uses a hardcoded cleaning proxy

`docs/research/09` specifies nozzle FIX as `clog_pct ← clog_pct · (1 − cleaning.efficiency)` — i.e. a clean cycle whose effectiveness depends on **the live cleaning interface health at the time of FIX**. The code (`components/nozzle.py:147`) hardcodes `cleaning_proxy = 0.7`, so the cleaning↔nozzle reset coupling is **constant, not adaptive**. A FIX with a brand-new cleaner produces the same recovery as a FIX with a 90 %-worn cleaner. This is a real gap in the cleaning-pair feedback story.

### C.3 The "live weather" bonus is documented but not wired

`README.md` and `docs/research/07` describe Open-Meteo Archive integration with cached Barcelona + Phoenix JSONs. But:

- The scenario YAMLs (`barcelona-baseline.yaml`, `phoenix-aggressive.yaml`) use `kind: sinusoidal_seasonal` with hand-tuned `base` and `amplitude` parameters, not actual weather data.
- There is no `OpenMeteoDriver` adapter in `drivers_src/`.

What's actually happening: the sin generator is *calibrated* to look like Barcelona (base=0.30, amp=0.10) vs Phoenix (base=0.65, amp=0.20). This is a defensible scientific calibration, not live data. **In the pitch, say "weather-shaped scenarios", not "live weather"**, unless the OpenMeteoDriver adapter ships.

### C.4 Status threshold drift (now fixed)

| Source | FUNCTIONAL | DEGRADED | CRITICAL | FAILED |
|---|---:|---:|---:|---:|
| `docs/research/04` (and README) | `> 0.75` | `> 0.40` | `> 0.15` | `≤ 0.15` |
| Code as of 2026-04-25 (pre-fix) | `≥ 0.75` | `≥ 0.45` | `≥ 0.20` | `< 0.20` |
| Code post-fix (B1.1 in roadmap) | `≥ 0.75` | `≥ 0.40` | `≥ 0.15` | `< 0.15` |

Code was **5 pp more aggressive** on both DEGRADED and CRITICAL than docs. The print-outcome boundary in `engine/assembly.py:25` is `0.40` (matching docs). Reconciliation is item B1.1 in [`23-improvement-roadmap.md`](23-improvement-roadmap.md) — already addressed in this session.

### C.5 The double-counting in `humidity_contamination_effective`

In `engine/coupling.py:82`:

```python
humidity_contamination_effective = clip01(
    drivers.humidity_contamination
    + 0.20 * blade_wear
    + 0.10 * (1.0 - powder_spread_quality)
)
```

But `(1 − powder_spread_quality) = 0.6·blade_wear + 0.3·rail_misalignment`. So total blade contribution to humidity is `0.20·blade_wear + 0.10·0.6·blade_wear = 0.26·blade_wear`. **Blade wear contributes through two factor names** — directly *and* via `powder_spread_quality`. Defensible as "two physical pathways: direct shedding + degraded spread quality", but a tight reading is that the blade pathway is double-counted.

If a judge asks: *"those are two distinct physical mechanisms — powder degradation from shedding and powder degradation from poor spreading; we model them additively because they enter the contamination signal independently"*.

### C.6 `control_temp_error_c` is sign-symmetrized

`engine/coupling.py:74,78`:

```python
control_temp_error_c = sensor_bias
temperature_stress_effective = clip01(
    drivers.temperature_stress
    + heater_thermal_stress_bonus
    + 0.05 * abs(control_temp_error_c)
)
```

The `abs()` means a sensor reading high *or* low both add thermal stress. Physically, only *one* sign should add stress (the sign for which the controller commands more heat). This is a **simplification, not an error** — both biases are stressful in different ways (overheat vs incomplete cure) — but a controls engineer in the audience would notice.

---

## D. Per-component realism scorecard

| Component | Physics | Anchors | Maintenance | Coupling | Verdict |
|---|---|---|---|---|---|
| Blade | ✓ Archard textbook | ✓ 17 wks cited | ✓ consumable | ✓ feeds powder cascade | Solid |
| Rail | ✓ Lundberg-Palmgren cubic | ✓ 77 wks cited | ✓ permanent pitting modeled | ⚠ one-way only via powder_spread_quality | Best on Realism axis |
| Nozzle | ✓ Coffin-Manson + Poisson | ✓ 8.5 wks cited | ⚠ hardcoded cleaning_proxy on FIX | ✓ dual coupling factors consumed | Most complex; one quibble |
| Cleaning | ✓ Power-law cycle wear | ✓ 50 wks shelf-life | ✓ consumable | ⚠ no nozzle reverse arrow + cumulative_cleanings unused | Two real gaps |
| Heater | ✓ Arrhenius textbook | ✓ 38 wks cited | ✓ recalibrate vs replace | ✓ thermal cascade upstream | Solid |
| Sensor | ✓ Arrhenius bias drift | ✓ HW-group cited | ✓ bias-only calibration | ⚠ explicit reverse arm to heater missing | The §3.4 differentiator |

---

## E. The pitch-time stance — what to say

If a judge walks up after the pitch and asks **one question**, it will most likely be: *"how do you know your model is realistic?"*

Best answer (memorize this):

> *"Three layers. One: every failure law is the textbook model for its mechanism — Archard for sliding wear, Lundberg-Palmgren for bearing fatigue, Coffin-Manson for thermal-fatigue, Arrhenius for thermal degradation. We're not inventing physics. Two: every η lifetime value is cited to industry — NSK and THK for the rail, HP's own whitepaper for the printhead, Kanthal for the heater, HW-group for the PT100. Doc 22 in the repo has the references. Three: the maintenance reset rules match real industrial practice — blade is consumable so FIX equals REPLACE, rail pitting is permanent so FIX leaves alignment untouched, sensor noise is connector oxidation so calibration only zeros bias. We deliberately built the simulation at the part-level the brief asks for, with the textbook law and the cited number for each part."*

That's a 30-second answer that hits *Rigor* and *Realism & Fidelity* simultaneously and gives them three places in the repo to verify.

If they push on cascades: *"the dominant loop is the sensor-heater pair, where a drifting sensor lies to the controller, the heater overshoots, and the resulting thermal stress accelerates the sensor's own drift. The other component pairs interact through shared output sinks — like powder spread quality from the blade-rail pair feeding into the nozzle's clog rate."*

---

## Cross-references

- The improvement roadmap that closes these gaps: [`23-improvement-roadmap.md`](23-improvement-roadmap.md).
- The cascade detail this audit references: [`03-coupling-and-cascades.md`](03-coupling-and-cascades.md).
- Per-component realism notes: each file in [`components/`](components/).
- Research backing every parameter: `docs/research/22-printer-lifetime-research.md`, plus the per-component decision docs `docs/research/{01,02,03,17,18,19}-*.md`.
