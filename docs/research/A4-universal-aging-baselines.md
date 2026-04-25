# A4 — Universal Aging Baselines

## TL;DR

Use **Weibull** for all three components (exponential is the β=1 degenerate case and is too weak
for wear-out regimes). Compose with driver stressors **multiplicatively on the hazard rate**
(proportional hazards model). Blade: β=2.5, η=2000 h; Nozzle Plate: β=2.0, η=5000 h;
Heating Elements: β=3.0, η=8000 h.

---

## Background

Two standard reliability baselines are in scope:

**Exponential decay** H(t) = e^(-λt)
Constant failure rate (β=1 Weibull special case). Implies failures are random and memoryless —
no accelerating wear-out. Appropriate only when the hazard rate does not increase with age.

**Weibull reliability** R(t) = exp(-(t/η)^β)
Generalises exponential. The shape parameter β controls the failure-rate slope:
- β < 1: infant mortality (decreasing hazard)
- β = 1: pure random (reduces to exponential, λ=1/η)
- β > 1: wear-out / degradation (increasing hazard — the industrially relevant regime)
- β > 4: rapid end-of-life wear-out

The Weibull is also the only distribution simultaneously consistent with both the
proportional-hazards (PH) and accelerated-failure-time (AFT) frameworks, making it the
natural host for stressor covariates.

---

## Options Considered

| Option | Pro | Con |
|---|---|---|
| Exponential (β=1) | One parameter, trivial to tune | Cannot model accelerating wear; wrong for all three components | 
| Weibull (β>1) | Captures increasing hazard; grounded beta values in literature | Two parameters to calibrate |
| Lognormal | Good for fatigue scatter | Cannot be expressed as PH model; harder to compose |

**Decision:** Weibull for all three. Exponential is retired as a named alternative — it reappears
automatically if β is ever clamped to 1 during calibration.

---

## Recommendation

### Composition rule: multiplicative on hazard (Proportional Hazards)

The PH model multiplies the Weibull baseline hazard by a stressor factor:

```
h(t; X) = h0(t) * exp(sum_i(gamma_i * X_i))
```

where h0(t) = (β/η)(t/η)^(β-1) is the Weibull baseline hazard and X_i are
normalised driver values (temperature stress, contamination, load, maintenance).
The combined survival / health function is:

```
H(t; X) = exp(-((t/η)^β) * exp(sum_i(gamma_i * X_i)))
```

This keeps the health index in [0, 1], is differentiable, and lets each driver
independently accelerate or decelerate the effective age without ad-hoc clamping.

### Component table

| Component | Failure mode | Baseline | β | η (hours) | Why |
|---|---|---|---|---|---|
| Recoater Blade | Abrasive wear | Weibull | **2.5** | 2000 | Mechanical abrasion β 2.0-2.5 (fatigue cracks / corrosion-driven); short life due to continuous powder contact |
| Nozzle Plate | Clogging + thermal fatigue | Weibull | **2.0** | 5000 | Thermal fatigue β 2.0-3.0; lower β chosen because clog onset has a more Poisson-like early component mixed with wearout |
| Heating Elements | Electrical degradation (resistance drift) | Weibull | **3.0** | 8000 | Electrical insulation / dielectric breakdown β 2.0-4.0; resistance drift is a clear wear-out mechanism trending toward the upper range |

**η rationale:** values represent the characteristic life (63.2% failure probability) under
nominal operating conditions. Scale linearly with the `maintenance_level` driver (high
maintenance effectively extends η).

---

## Open Questions

1. Should η be expressed in print-hours, calendar hours, or layer-cycles? Layer-cycles
   may be more physical for the blade and nozzle.
2. Driver weights (gamma_i) need plausible defaults — candidate starting point: temperature
   stress 0.8, contamination 1.2 (blade), load 0.5, maintenance -1.0 (protective).
3. If an AI regression is trained on synthetic data, β and η can be recovered via MLE and
   used to validate the hand-picked defaults.
4. Blade health reset on maintenance event: should η reset partially or should t be
   shifted (virtual age model, Kijima Type I/II)?

---

## References

- [What the Weibull Shape Parameter Tells You About Failure — Engineer Fix](https://engineerfix.com/what-the-weibull-shape-parameter-tells-you-about-failure/)
- [How the Weibull Distribution Is Used in Reliability Engineering — All About Circuits](https://www.allaboutcircuits.com/technical-articles/how-the-Weibull-distribution-is-used-in-reliability-engineering/)
- [Weibull Distribution — Minitab Support](https://support.minitab.com/en-us/minitab/help-and-how-to/statistical-modeling/reliability/supporting-topics/distribution-models/weibull-distribution/)
- [Proportional Hazards Model — Wikipedia](https://en.wikipedia.org/wiki/Proportional_hazards_model)
- [Weibull Regression Model as an Example — PMC / Annals of Translational Medicine](https://pmc.ncbi.nlm.nih.gov/articles/PMC5233524/)
- [Failure mechanisms in thermal inkjet printhead — ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0026271404005165)
- [Lifetime Assessment of Electrical Insulation — IntechOpen](https://www.intechopen.com/chapters/58128)
- [How Weibull Analysis Helps You Identify Early and Late Failures — ReliaMag](https://reliamag.com/articles/weibull-analysis/)
- [Unlocking Weibull Analysis — Machine Design](https://www.machinedesign.com/automation-iiot/article/21831580/unlocking-weibull-analysis)
