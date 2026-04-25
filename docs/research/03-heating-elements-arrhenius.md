# Heating Elements — Arrhenius Aging + Resistance Drift

> Failure model for the **Heating Elements** component of the Thermal Control subsystem on the HP Metal Jet S100 digital twin. Drives the `heater_resistance_ohm` metric and the `FUNCTIONAL → DEGRADED → CRITICAL → FAILED` status enum.

---

## TL;DR

- **Aging rate** is governed by the **Arrhenius equation** `r(T) = A · exp(−E_a / (k_B · T))`.
- We pick `E_a = 0.7 eV` (the canonical "general electronics" value used in JEDEC accelerated-life testing) and a reference temperature `T_ref = 423 K (150 °C)` representing the heater's nominal duty.
- **Resistance drift** is modelled as a compounded tick-by-tick update: `R(t+dt) = R(t) · (1 + α · AF(T) · M · dt)`, where `AF(T) = exp[(E_a/k_B)·(1/T_ref − 1/T)]` is the Arrhenius acceleration factor relative to nominal.
- **State thresholds**: `<2 %` drift = FUNCTIONAL, `2–5 %` = DEGRADED, `5–10 %` = CRITICAL, `>10 %` or open-circuit = FAILED.
- **Operational Load** modulates duty cycle (more on-hours → more thermal exposure). **Maintenance Level** scales `α` (good housekeeping → cleaner oxide layer → less drift per unit exposure).
- **Feedback loop** (bonus): higher R at fixed voltage means more I²R loss concentrated locally → local T rises → AF rises → drift accelerates. Captured by adding a `ΔT_self = β · (R/R_0 − 1)` term inside the Arrhenius expression.

---

## Background — Arrhenius for electrical aging

The Arrhenius equation describes how a thermally activated process speeds up with absolute temperature:

```
r(T) = A · exp(−E_a / (k_B · T))
```

| Symbol | Meaning | Units |
| :--- | :--- | :--- |
| `r(T)` | rate of the aging mechanism (degradation per unit time) | 1/s |
| `A` | pre-exponential ("attempt frequency"); absorbed into our calibration constant | 1/s |
| `E_a` | activation energy of the dominant failure mechanism | eV |
| `k_B` | Boltzmann constant | `8.617 × 10⁻⁵ eV/K` |
| `T` | absolute temperature of the element | K |

In practice, accelerated-life testing always uses the **acceleration factor form** (NIST, JEDEC), which cancels the unknown `A`:

```
AF(T) = r(T) / r(T_ref) = exp[ (E_a / k_B) · (1/T_ref − 1/T) ]
```

**Activation-energy values are mechanism-specific.** The consumer-electronics range is **0.5–0.8 eV**, with **0.7 eV** the de-facto default for generic semiconductor/metallization aging (electromigration in Al sits at 0.5–0.7 eV). For our NiCr-style heating wire the dominant mechanism is **chromium-oxide layer thickening / progressive grain-boundary oxidation**, which gradually thins the conductive cross-section and raises the wire's effective resistance over thousands of hours at red-hot temperature. We adopt **`E_a = 0.7 eV`** as the JEDEC-canonical default — defensible, documented, and gives realistic acceleration factors (≈46× from 25 °C to 85 °C, ≈29× from 50 °C to 100 °C per industry references).

NiCr's oxide layer (Cr₂O₃) is *protective* but not static: it thickens under thermal cycling, raises emissivity, and progressively narrows the metallic core. Practical heater datasheets list this as the dominant lifetime mechanism. Activation energies for protective-oxide growth on Cr-bearing alloys reported in the literature span 0.5–1.5 eV; 0.7 eV sits comfortably inside that band.

---

## Decision — full formula + drift mapping

### State variable

`R(t)` — element resistance in Ω. Reference baseline `R_0` is the as-new resistance at 25 °C (per element, set at "install" event).

### Tick update (compounded, deterministic)

```
T_eff(t) = T_amb(t) + ΔT_duty(t) + ΔT_self(t)
AF(t)    = exp[ (E_a / k_B) · (1/T_ref − 1/T_eff(t)) ]
R(t+dt)  = R(t) · (1 + α · AF(t) · L(t) · M · dt)
```

| Symbol | Meaning | Default |
| :--- | :--- | :--- |
| `T_amb` | ambient driver (Temperature Stress, K) | from driver stream |
| `ΔT_duty` | self-heating from Operational Load (cycles → on-time → ΔT) | 0–600 K, scaled by load |
| `ΔT_self` | feedback term (see below) | `β · (R/R_0 − 1)` with `β = 50 K` |
| `T_ref` | reference temperature for AF | `423 K` (150 °C) |
| `E_a` | activation energy | `0.7 eV` |
| `k_B` | Boltzmann constant | `8.617e-5 eV/K` |
| `α` | base drift coefficient at AF=1, M=1 | `1.0e-7 /s` (≈ 0.36 %/hr at AF=1) — calibrated so that ~5,000 h at nominal yields ~5 % drift |
| `L(t)` | Operational Load multiplier (duty cycle ∈ [0,1] or hours-running indicator) | from driver |
| `M` | Maintenance Level multiplier (poor housekeeping = higher drift) | `0.5` (well-maintained) to `2.0` (neglected) |

> The `1 + α · …` linearisation is valid per tick because `α · AF · dt ≪ 1`. Across many ticks it compounds, which is what we want — a heater run hot for a long time should drift super-linearly.

### Status thresholds (drift = `R/R_0 − 1`)

| Drift | Status |
| :--- | :--- |
| `< 2 %` | `FUNCTIONAL` |
| `2 % – 5 %` | `DEGRADED` |
| `5 % – 10 %` | `CRITICAL` |
| `≥ 10 %` or open-circuit event | `FAILED` |

`Health Index = clamp(1 − drift / 0.10, 0, 1)` — linear from new to failure threshold, fits the `[0.0, 1.0]` contract.

### Driver mapping (the four required inputs)

| Driver | Enters via | Effect |
| :--- | :--- | :--- |
| Temperature Stress | `T_amb` | exponential AF — dominant lever |
| Humidity / Contamination | small additive bump to `α` (moisture accelerates oxide growth) | secondary |
| Operational Load | `L(t)` and `ΔT_duty` | linear in time, plus self-heating |
| Maintenance Level | `M` | scales `α` directly; a "service" event also resets `ΔT_self`'s memory |

### Feedback loop (the "fun" coupling)

At fixed driver voltage `V`, dissipated power is `P = V²/R`. As the *whole* heater drifts up, average power drops — but the drift is **non-uniform**: thin spots heat hotter, oxidise faster, drift more. We approximate that with a self-heating term proportional to the drift itself:

```
ΔT_self(t) = β · (R(t)/R_0 − 1)        [ K ]
```

With `β = 50 K`, a 5 % drift adds 2.5 K to `T_eff`, which raises `AF` by ~5 % at nominal — a slow positive feedback that turns into a runaway near the CRITICAL/FAILED boundary. This is exactly the "heating element draws more energy → ages faster" story, and it produces the visually convincing "knee" in the time-series the demo wants.

---

## Why this fits our case

1. **Two failure-model requirement** — Arrhenius (this doc) + Archard wear (recoater blade) + Coffin-Manson fatigue (nozzle plate) overshoots the ≥2 minimum and gives each subsystem a textbook-distinct law.
2. **All four drivers wired in** — Temperature Stress (dominant via AF), Humidity (α bump), Operational Load (duty), Maintenance (M scaler and service reset). Ticks every box of the Phase 1 contract.
3. **Deterministic** — fully closed-form, no RNG required. Stochastic shocks can be sprinkled on top in Phase 2 without touching this layer.
4. **Storytelling for Phase 3** — the feedback loop produces a non-linear "knee" the chatbot can diagnose: *"resistance crossed 5 % at t=14:32 and the slope doubled in the following hour, indicating self-heating runaway. Recommend de-rate or replace within 48 h."* That is exactly the surprise-the-judges moment we are betting on.
5. **Physically motivated** — NiCr oxide growth is a real, citable mechanism; we are not inventing physics.

---

## References

1. **Wikipedia — Arrhenius equation.** Canonical formulation, units, derivation. https://en.wikipedia.org/wiki/Arrhenius_equation
2. **NIST/SEMATECH e-Handbook of Statistical Methods — §8.1.5.1 Arrhenius.** Reference for accelerated-life-test form and acceleration factor. https://www.itl.nist.gov/div898/handbook/apr/section1/apr151.htm
3. **JEDEC — "Arrhenius equation (for reliability)".** Industry-standard definition used across semiconductor reliability work. https://www.jedec.org/standards-documents/dictionary/terms/arrhenius-equation-reliability
4. **All About Circuits — "Using the Arrhenius Equation to Predict Electronic Component Aging".** Worked numerical examples, typical `E_a` ranges, applied to resistor/op-amp drift. https://www.allaboutcircuits.com/technical-articles/using-the-arrhenius-equation-to-predict-aging-of-electronic-components/
5. **Delserro Engineering Solutions — "Constant Temperature Accelerated Life Testing using the Arrhenius Relationship".** `E_a = 0.7 eV` default justification; concrete acceleration-factor numbers. https://www.desolutions.com/blog/2013/08/constant-temperature-accelerated-life-testing-using-the-arrhenius-relationship/
6. **All About Circuits — "Electronic Component Aging — Aging Effects of Resistors and Op-amps".** Long-term resistor drift in ppm/year, the R-over-time framing we use. https://www.allaboutcircuits.com/technical-articles/electronic-component-aging-aging-effects-of-resistors-and-operational-amps/
7. **Wikipedia — Nichrome.** Cr₂O₃ protective-oxide mechanism that grounds our choice of `E_a` for the heater. https://en.wikipedia.org/wiki/Nichrome

---

## Open questions

- **Calibration of `α`** — currently set so 5,000 h at nominal yields ~5 % drift. We may want to tune so a "stress demo run" reaches FAILED inside a 5-minute on-stage simulation; this is a `dt`/scaling tradeoff we should fix in Phase 2.
- **`T_ref` choice** — 150 °C is a placeholder for "nominal heater duty"; the S100 curing/heating subsystem's actual setpoint is not in the brief. If we get a real number from HP's docs, swap it in; the AF formula is otherwise unchanged.
- **Multi-element redundancy** — real heater banks have N elements in parallel; one failing raises load on the others. Out of scope for v1, easy bonus if we model two elements with shared driver.
- **Maintenance "reset" semantics** — does a service event reset `R` to `R_0` (replacement) or only reset `M` (cleaning)? Suggest two distinct event types: `replace_heater` (R := R_0) and `service_heater` (M := 0.5).
- **Humidity coupling magnitude** — qualitative direction is clear (moisture accelerates oxide growth), but we have no number. Pick a small linear bump `α' = α · (1 + 0.5 · humidity_norm)` and document it as a tuning knob.
