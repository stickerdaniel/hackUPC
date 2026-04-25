# 04 — Aging Baselines and Normalization Layer

> Background aging (under driver-specific damage) and the metric → health → status pipeline for the three modeled components: Recoater Blade, Nozzle Plate, Heating Elements.

## TL;DR

- **Blade → Weibull, β = 2.5, η = 180 days.** Abrasive wear is a textbook wear-out process (β > 1).
- **Nozzle plate → Weibull, β = 2.0, η = 150 days.** Thermal-fatigue wear-out, classic β ≈ 2 region.
- **Heating element → Weibull, β = 1.0 (≡ exponential), η = 240 days, λ ≈ 0.0042 / day.** Resistance drift / element burnout behaves as random failure during useful life.
- **Composition rule: multiplicative.** `H_total = H_baseline(t) · H_driver(damage)`, both clipped to `[0, 1]`. Multiplicative gives the bathtub-curve composability we want and keeps the math monotone non-increasing without negative-health edge cases.
- **Metric → health: linear normalization** between `metric_new` and `metric_failed` for each component, clipped to `[0, 1]`.
- **Status thresholds (revised):** `> 0.75` FUNCTIONAL, `> 0.40` DEGRADED, `> 0.15` CRITICAL, else FAILED. Tuned slightly upward from the `> 0.10` CRITICAL boundary to give the operator a more useful warning window before terminal failure.

## Background: Weibull vs. Exponential

The reliability function `R(t) = P(T > t)` describes the probability a part has not failed by time `t`. Two standard forms:

- **Exponential decay:** `R(t) = exp(−λt)`. Single parameter (rate λ). **Constant failure rate** — memoryless. Models the flat "useful life" middle of the bathtub curve. Dominant for many electronic components and random-event failures. (NIST, Accendo Reliability)
- **Weibull:** `R(t) = exp(−(t/η)^β)`. Two parameters: scale `η` (≈ characteristic life, the time at which 63.2% have failed) and shape `β`:
  - **β < 1** — decreasing hazard rate → infant mortality.
  - **β = 1** — constant hazard rate → reduces exactly to the exponential, useful-life region.
  - **β > 1** — increasing hazard rate → wear-out. Typical mechanical wear-out values are `β ≈ 1.5–4`; rolling-element bearings sit near β = 2, mechanical seals near β = 2–3.5. (PTC, Accendo Reliability, Engineer Fix)

Because Weibull collapses to exponential at β = 1, we use Weibull as the single baseline form across all three components and just pick β.

## Decision

### Per-component baseline parameters

| Component | β | η (days) | Failure regime | Why |
| :--- | :--- | :--- | :--- | :--- |
| Recoater Blade | **2.5** | **180** | Wear-out | Abrasive contact wear. β = 2.5 sits in the documented mechanical-wear band (1.5–4); η = 180 d means ≈ 63% would have failed by 6 months under nominal drivers — i.e. without the Archard accelerator the demo's "blade replacement" event lands inside the simulated window. |
| Linear Guide / Rail | **2.0** | **220** | Wear-out (subsurface fatigue) | Rolling-contact pitting band is β ≈ 1.5–2.5 (Lundberg-Palmgren / NSK / NIST). η = 220 d puts rail's CRITICAL ~10 % later than the blade so the blade fails first under nominal drivers — the blade-fails-first cascade story holds. (doc 17) |
| Nozzle Plate | **2.0** | **150** | Wear-out (thermal-fatigue dominated) | Thermal cycling + clog accretion is a classic β ≈ 2 wear pattern (matches bearing-fatigue analogue). Slightly shorter η than blade because nozzle clogging in binder jetting is empirically aggressive in dirty environments. |
| Cleaning Interface | **1.5** | **8760 h** (≈ 365 d) | Use-driven (shelf-life only) | Dominant decay is power-law in cumulative cleanings (`H_use = 1 − a·n^p`); the Weibull term is a small calendar shelf-life floor for elastomer hardening when idle. β = 1.5 light wear-out. (doc 18) |
| Heating Elements | **1.0** | **240** | Random / useful-life | Heater wire burnout and resistance drift are dominated by random over-stress events (oxidation, hot spots) inside the useful-life envelope, not gradual wear. β = 1 ⇒ R(t) = exp(−t/240) ≈ exp(−0.00417·t). MTTF = η = 240 d. (Goodson, Ohmite, AllAboutCircuits) |
| Temperature Sensor | n/a | n/a | Arrhenius-driven bias drift | No Weibull baseline — bias accumulates as `exp(−E_a/k_B·(1/T_ref − 1/T))` (E_a = 0.7 eV, T_ref = 423 K) layered with a sub-linear noise-floor growth. Hard FAILED gate at `|bias_C| > 5 °C` regardless of HI. (doc 19) |

### Composition rule — multiplicative

```
H_total(t) = clip( H_baseline(t) · H_driver(t), 0, 1 )

where  H_baseline(t) = exp(−(t/η)^β)
       H_driver(t)   = 1 − D(t)   # D = cumulative damage from Archard / CM / Arrhenius layer
```

**Why multiplicative, not additive / min / weighted:**

- Additive can produce health > 1 or < 0 without ad-hoc clamping; multiplicative is naturally bounded in `[0, 1]`.
- `min()` collapses to a single dominating term and hides the synergy we want to demo (a part can be moderately aged *and* moderately driver-damaged and the twin should reflect both).
- Weighted sums require defending the weights; multiplicative needs no weights and matches how independent failure modes compose in series-reliability theory (`R_system = ∏ R_i`).
- Explainable in the chatbot: "blade is at 0.62 because baseline aging is 0.78 and abrasion damage is 0.79".

### Metric → health normalization

Linear interpolation between a "new" anchor and a "failed" anchor, clipped:

| Component | Metric `m` | `m_new` | `m_failed` | Health from metric |
| :--- | :--- | :--- | :--- | :--- |
| Recoater Blade | thickness (mm) | 1.00 | 0.50 (50 % loss) | `clip((m − 0.5) / 0.5, 0, 1)` |
| Linear Guide / Rail | alignment_error (µm) | 0 | 50 | `clip(1 − m/50, 0, 1)` |
| Nozzle Plate | composite `(1−clog%/100)·(1−D)` | 1.0 | 0.20 | direct (already in [0,1]); hard fail if `clog%≥95` or `D≥1` |
| Cleaning Interface | cleaning_efficiency (already [0,1]) | 1.0 | 0.0 | direct |
| Heating Elements | resistance drift (% from nominal) | 0 | +10 | `clip(1 − m/10, 0, 1)` |
| Temperature Sensor | composite `0.7·(1−|bias|/5) + 0.3·(1−σ/0.5)` | 1.0 | 0.0 | direct; **hard FAILED if `|bias_C| > 5 °C`** regardless of HI |

Clipped to `[0, 1]`. The simulator stores both: the physical metric (for the operator) and the derived health (for the agent and the status enum).

In our flow, `H_total` is computed first from the math model; the metric is then driven *back out* of `H_total` so health and metric stay consistent: e.g. `thickness_mm = H_total · 0.50`.

### Status enum thresholds

| Health range | Status | Operator meaning |
| :--- | :--- | :--- |
| `> 0.75` | FUNCTIONAL | Within normal envelope |
| `(0.40, 0.75]` | DEGRADED | Watch; schedule maintenance window |
| `(0.15, 0.40]` | CRITICAL | Act now; remaining useful life days, not weeks |
| `≤ 0.15` | FAILED | Replacement required before next print |

Revised the suggested CRITICAL boundary from `> 0.10` to `> 0.15`. Reason: at health 0.10 the blade is already at 0.05 mm of remaining thickness — too late to be a useful warning. 0.15 keeps a one-step buffer between CRITICAL and FAILED that the proactive-alert agent can fire on.

## Why this fits our case

- **Demo timescale:** all three η values land within the 6-month simulated horizon, so a single batch run produces visible progression *and* terminal failure for at least one component.
- **Driver layer is independent:** the math team picks Archard / Coffin-Manson / Arrhenius and outputs `D(t) ∈ [0, 1]`. Our multiplicative rule means they can iterate without us re-tuning baselines.
- **Bathtub-curve story for judges:** β values 2.5 / 2.0 / 1.0 across the three components is itself a narrative — different physics, different failure regimes, the same Weibull machinery.
- **Agent-friendly:** the chatbot can decompose any health drop into (baseline, driver) and quote both, satisfying the grounding protocol.

## References

1. NIST/SEMATECH e-Handbook of Statistical Methods — *Exponential Distribution*. https://www.itl.nist.gov/div898/handbook/apr/section1/apr161.htm
2. PTC Windchill Risk and Reliability — *Understanding Weibull Analysis*. https://support.ptc.com/help/wrr/r12.0.2.0/en/wrr/PractitionersGuide/UnderstandingWeibullAnalysis.html
3. Accendo Reliability — *Using the Exponential Distribution Reliability Function*. https://accendoreliability.com/using-the-exponential-distribution-reliability-function/
4. Accendo Reliability — *With Weibull, What Shape Value Should your Product Have?* https://accendoreliability.com/with-weibull-what-shape-value-should-your-product-have-for-better-reliability/
5. Engineer Fix — *What the Weibull Shape Parameter Tells You About Failure*. https://engineerfix.com/what-the-weibull-shape-parameter-tells-you-about-failure/
6. AllAboutCircuits — *How the Weibull Distribution Is Used in Reliability Engineering*. https://www.allaboutcircuits.com/technical-articles/how-the-Weibull-distribution-is-used-in-reliability-engineering/
7. Goodson Engineering — *Loss Investigations Involving Heating Element Failures*. https://goodsonengineering.com/wp-content/uploads/2017/10/ISFI-Abstract_Heating-Element-Failures.pdf
8. Ohmite — *Resistor Stability and Calculating Drift*. https://www.ohmite.com/blog/2023/03/09/resistor-stability-and-calculating-drift

## Open questions

- **Stochastic noise on top of `H_total`?** Phase-2 brief mentions optional stochastic shocks. Decision needed: layer Gaussian sensor noise on the *metric* (not on health) so the underlying state stays deterministic and seedable.
- **Maintenance reset semantics:** does maintenance reset baseline `t → 0`, reset only `D(t) → 0`, or partially scale both by a maintenance-quality coefficient? Current bias: full reset for blade (replacement), partial for nozzle (cleaning), driver-only reset for heater (no realistic field repair short of replacement).
- **Cascading effect on η:** if the blade contaminates powder, should the nozzle's effective η shrink? Cleanest implementation: keep η constant, push the cascade through `D_nozzle(t)` instead of mutating baseline parameters.
- **Calibration source:** η values are demo-tuned, not literature-anchored. If a real S100 MTBF figure surfaces during the hack, recalibrate η; β values should stay (they're regime, not scale).
