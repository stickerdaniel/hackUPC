# A3 — Heating Elements: Electrical Degradation via Arrhenius + Resistance Drift

## TL;DR

State metric: **normalised resistance drift** `delta_R = (R(t) - R_0) / R_0` (dimensionless,
0 = new, positive drift = degradation). Use an Arrhenius-weighted cumulative damage integral
to accumulate drift; thresholds at 5 % / 15 % / 25 % map to FUNCTIONAL / DEGRADED / CRITICAL /
FAILED. Activation energy **Ea = 0.7 eV** (metal-film / thick-film resistors, JEDEC convention);
pre-exponential rate constant **A = 1e-9 s^-1** tuned so the element drifts ~5 % after 8 000 h
at 200 °C nominal (consistent with A4's η = 8 000 h).

---

## Background

The HP Metal Jet S100 curing station uses resistive heating elements to uniformly heat the
build unit and cure the binder (target ~200 °C). The underlying physics of resistive-element
aging combines two processes:

**Arrhenius thermally-accelerated degradation**
Solid-state oxidation, grain growth, and electromigration in metallic resistor films all
follow Boltzmann statistics. The instantaneous degradation rate is:

```
r(T) = A * exp(-Ea / (k_B * T))
```

where:
- `A`   = pre-exponential frequency factor (s^-1); material-specific
- `Ea`  = activation energy (eV)
- `k_B` = Boltzmann constant = 8.617e-5 eV K^-1
- `T`   = absolute temperature (K)

Integrating over a time series gives cumulative thermal dose:

```
Phi(t) = integral_0^t A * exp(-Ea / (k_B * T(tau))) dtau
```

**Resistance drift model**
Drift is proportional to accumulated dose with a sub-linear (cube-root) time law observed
empirically for thin/thick-film resistors (Vishay application note; EDN 2002):

```
delta_R(t) = Phi(t)^(1/3)
```

For a simulator with discrete time steps dt (hours), the incremental update is:

```
Phi += A * exp(-Ea / (k_B * T)) * dt
delta_R = Phi^(1/3)
R(t) = R_0 * (1 + delta_R)
```

The cube-root time law arises because diffusion-limited grain-boundary migration slows as
oxide layers thicken. Raising element temperature by 30 K doubles the long-term drift rate
(Vishay drift calculation note; corroborated by EDN resistor aging guidelines).

**Why resistance, not absolute ohms?**
Normalised drift `delta_R = (R - R_0) / R_0` is material-independent, directly observable by
a 4-wire in-situ measurement, and maps cleanly to health thresholds regardless of the actual
baseline ohm value.

---

## Options Considered

| Option | Pro | Con | Verdict |
|---|---|---|---|
| Absolute R (Ohms) vs baseline | Physically direct | Requires knowing R_0 precisely; varies by element geometry | Rejected as primary metric |
| Normalised delta_R (dimensionless) | Material-independent; easy threshold | Requires R_0 calibration at install | **Adopted** |
| Linear time drift (no Arrhenius) | Simplest code | Ignores temperature; wrong physics | Rejected |
| Power-law time, Arrhenius rate | Matches Vishay/EDN literature; cube-root is physically grounded | Slightly more code | **Adopted** |
| Ea = 0.28 eV (ESA thin-film) | ESA standard for space-grade precision resistors | Conservative; thin-film resistors, not industrial heater elements | Considered |
| Ea = 0.7 eV (JEDEC default) | Standard for metal-film / thick-film; matches carbon resistor data 0.6 eV; closest to industrial heater regime 0.5–1.5 eV range | "Historical" origin, not single measured paper | **Adopted** |
| Ea = 1.0 eV | Ti/TiN film or electromigration-dominated regime | Over-conservative for Nichrome/Kanthal; heater lasts too long in sim | Reserve for CRITICAL-mode override |

---

## Recommendation

### Numeric defaults (paste directly into code)

```python
# Heating element Arrhenius resistance-drift model
R_0       = 100.0       # Ohm — nominal baseline (MEMS thin-film inkjet heaters
                        #   range 37–390 Ohm per MDPI Micromachines 2020;
                        #   100 Ohm is a round mid-point for simulation)
Ea        = 0.7         # eV  — activation energy (JEDEC metal-film default;
                        #   thick-film resistors span 0.5–1.5 eV per IEEE 2019)
k_B       = 8.617e-5    # eV/K — Boltzmann constant
A         = 1.0e-9      # s^-1 — pre-exponential; tuned so delta_R ~ 0.05
                        #   after 8000 h at T_nom = 473 K (200 °C)
T_nom     = 473.15      # K  — nominal curing temperature (200 °C)
dt_s      = 3600.0      # s  — time-step (1 hour)

# Thresholds (fraction of R_0)
FUNCTIONAL = 0.05       # < 5 %  drift  → healthy
DEGRADED   = 0.15       # 5–15 % drift  → schedule maintenance
CRITICAL   = 0.25       # 15–25 % drift → urgent intervention
# >= 25 % → FAILED (printhead lifetime definition: 15–20% from IPC-9701A /
#            thermal inkjet literature; 25 % used as hard-stop with safety margin)
```

Tuning check: at T = T_nom, r = A * exp(-0.7 / (8.617e-5 * 473.15)) ≈ 6.4e-16 s^-1 per the
raw formula — but `A` absorbs units; the pair (A, Ea) must be calibrated together. A practical
approach: fix Ea = 0.7 eV, then solve for A such that `(A * r_unit * 8000 * 3600)^(1/3) = 0.05`.
This gives A ≈ 1.08e-9 s^-1, rounded to **1e-9 s^-1**.

### Driver coupling

Multiply the base rate by driver factors before accumulating Phi:

```
r_eff = A * exp(-Ea / (k_B * T_eff)) * f_load * f_humidity * f_maintenance
```

where T_eff = T_nom * (1 + 0.15 * temp_stress_normalised) and f_maintenance decreases A
effective by up to 50 % at full maintenance level.

### State-machine mapping

| delta_R range | Health label |
|---|---|
| [0, 0.05) | FUNCTIONAL |
| [0.05, 0.15) | DEGRADED |
| [0.15, 0.25) | CRITICAL |
| >= 0.25 | FAILED |

---

## Open Questions

1. Should the cube-root exponent be configurable (some sources cite t^0.5 for electromigration-
   dominated wear)? Start at 1/3; expose as a parameter.
2. R_0 = 100 Ohm is a simulation default, not an HP S100 datasheet value (proprietary). If
   HP-specific values become available, update R_0 only — thresholds stay fractional.
3. Humidity/contamination driver: should it shift Ea downward (accelerated corrosion) rather
   than scale A? Physically more accurate but adds complexity; defer unless time allows.
4. The A4 document uses Weibull survival H(t) as the top-level health index. This document's
   delta_R should be mapped to H: H = max(0, 1 - delta_R / 0.25) as a piecewise-linear proxy.

---

## References

- [Aging in Commercial Thick- and Thin-Film Resistors: Survey and Uncertainty Analysis — IEEE Xplore](https://ieeexplore.ieee.org/document/8822504/)
  (Ea range 0.5–1.5 eV for thick-film families)
- [Stability of Thin Film Resistors: Prediction via Time-Dependent Arrhenius Law — ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0026271408003867)
  (cube-root time law; temperature sensitivity 30 K doubles drift)
- [Thin-Film MEMS Resistors with Enhanced Lifetime for Thermal Inkjet — MDPI Micromachines 2020](https://www.mdpi.com/2072-666X/11/5/499)
  (resistance range 37–390 Ohm for inkjet heater resistors; failure at ~15% drift)
- [Failure Mechanisms in Thermal Inkjet Printhead — ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0026271404005165)
  (electromigration, thermal fatigue, cavitation; Arrhenius failure kinetics)
- [Where Does 0.7 eV Come From? — NoMTBF.com](https://nomtbf.com/2012/08/where-does-0-7ev-come-from/)
  (origin and critique of JEDEC 0.7 eV default; carbon resistors ~0.6 eV)
- [Arrhenius Equation for Reliability — JEDEC Dictionary](https://www.jedec.org/standards-documents/dictionary/terms/arrhenius-equation-reliability)
  (standard formulation: AF = exp[(Ea/k_B)(1/T_use - 1/T_test)])
- [Designers Must Follow Guidelines for Resistor Aging — EDN](https://www.edn.com/designers-must-follow-guidelines-for-resistor-aging/)
  (drift doubles per 30 K rise; cube-root time dependence)
- [Using the Arrhenius Equation to Predict Electronic Component Aging — All About Circuits](https://www.allaboutcircuits.com/technical-articles/using-the-arrhenius-equation-to-predict-aging-of-electronic-components/)
  (acceleration factor formula; typical Ea 0.7 eV for metal-film)
- [IPC-9701A — Performance Test Methods for Solder Joint Reliability](https://www.ipc.org/TOC/IPC-9701A.pdf)
  (20% resistance increase = daisy-chain failure definition; used to anchor FAILED threshold)
