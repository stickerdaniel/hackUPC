# Linear Guide / Rail — Weibull Wear-Out with Driver-Accelerated Pitting

## TL;DR

Model the recoater carriage's **linear guide rail** as a recirculating ball-rail
whose dominant failure mode is **subsurface fatigue → raceway pitting**, with
secondary contributions from corrosion and lubricant breakdown. Use a **Weibull
baseline (β = 2.0, η = 220 days)** — slightly longer than the blade's η = 180 d
so the blade fails first under nominal drivers — composed multiplicatively with
a driver-damage term accelerated by `production_load`, `temperature_stress`,
`humidity`, and `maintenance_quality`. State metric: **`alignment_error_um`** ∈
[0, 50] µm of lateral deviation; FAILED at 50 µm. Canonical output:
`rail.alignment_error = alignment_error_um / 50`. Maintenance fully restores
lubrication damage, partially restores corrosion damage, but **raceway pitting
is permanent** — neglected rails accrue an irreducible wear floor.

## Background

Linear-bearing life is rated via the **L10 fatigue formula** from ISO 14728-1:
`L10 = (C/P)^p · 10^5 m` with load-life exponent **p = 3** for ball, 10/3 for
roller (MaximoMastery; Linear Motion Tips; PBC Linear). L10 is the travel at
which 10 % of identical bearings have failed by **subsurface rolling-contact
fatigue → raceway/element pitting** (NSK Damage Analysis; Shafttech; PMC
linear-rolling-guide diagnostics). Empirical Weibull shape parameters cluster
in **β ≈ 1.5–2.5** for contact fatigue: Lundberg-Palmgren ≈ 1.1, NSK/SKF
acceptance tests 1.5–2.0, stress-based studies near β = 2 (MDPI 10/22/8100;
NIST JRES 57/5). Secondary mechanisms: lubricant breakdown (fretting
corrosion), humidity-driven raceway corrosion, misalignment that concentrates
contact stress on a subset of balls (IMTEK; CSK Motions).

## Decision

**State metric.** `alignment_error_um ∈ [0, 50] µm` of lateral carriage
deviation. New = 0 µm; FAILED = 50 µm (high-precision-class boundary).

**Composition (per doc 04).** `H_total = H_baseline(t) · H_driver(D)`, both
clipped to `[0, 1]`.

**Baseline.** `H_baseline(t) = exp(−(t/η)^β)`, **β = 2.0, η = 220 days**.
β = 2 sits in the documented contact-fatigue band; η = 220 d puts the rail's
nominal CRITICAL crossing ~10 % later than the blade.

**Damage accumulator.**

```
dD/dt = D0 · k_load · k_temp · k_humid · k_maint
D    ← clip(D + dD/dt · dt, 0, 1)
H_driver = 1 − D
```

with `D0 = 1 / (η_drv · 24)` and **`η_drv = 260 d`** (slightly slower than
baseline so under nominal mid-drivers the two terms compose to ≈ 6 months
time-to-FAILED).

**Driver coupling table.**

| Driver | Coefficient on `dD/dt` | Range | Rationale |
|---|---|---|---|
| `production_load` L | `k_load = 0.5 + 1.5·L` | 0.5 → 2.0 | Cycles/h drives Hertzian fatigue. Linear (not cubic) because our duty-cycle varies slowly. |
| `temperature_stress` T | `k_temp = 1 + 0.6·T` | 1.0 → 1.6 | Hot lubricant thins → boundary-layer breakdown; thermal expansion adds preload. |
| `humidity` Hu | `k_humid = 1 + 0.8·Hu` | 1.0 → 1.8 | Moisture → fretting corrosion → micro-pits initiate fatigue. |
| `maintenance_quality` M | `k_maint = 1 / (1 + 1.0·M)` | 2.0 → 0.5 | Re-greasing + alignment checks halve effective wear; neglect doubles it. |
| `powder_contamination` C | (none direct) | — | Rail is sealed; coupled indirectly via the blade-rail loop. |

**Two-way blade coupling.** Each tick after both components update:
`rail.alignment_error += 0.05 · blade.loss_frac · dt` (a worn blade transmits
impulses through the carriage), and next tick
`blade.k_eff *= (1 + 0.5 · rail.alignment_error)` (a misaligned rail makes the
blade strike at uneven depth). This is the **rail ↔ blade feedback loop**.

**Canonical output.**

```
alignment_error_um   = 50 · (1 − H_total)
rail.alignment_error = clip(alignment_error_um / 50, 0, 1)
```

**Status thresholds** (doc 04): H > 0.75 FUNCTIONAL, > 0.40 DEGRADED, > 0.15
CRITICAL, else FAILED (alignment 12.5 / 30 / 42.5 µm).

**Maintenance reset.** Split D into `D_lube + D_corr + D_pit` (default 0.4 /
0.2 / 0.4 of `dD/dt`). On service:

- Re-greasing zeros `D_lube` (fully recoverable).
- Cleaning + dehumidify removes `0.5 · D_corr` (surface rust only).
- `D_pit` is **permanent** — once pitting accumulates, no maintenance restores it.

Once `D_pit > 0.5`, no service can return the rail to FUNCTIONAL.

## Why this fits our case

The rail is the textbook **β ≈ 2 contact-fatigue wear-out component**, distinct
from the blade's β = 2.5 abrasion regime — same Weibull machinery, different
physics narrative. The permanent-pitting rule produces the exact demo arc we
want: skipped maintenance accrues irreversible damage, perfect maintenance
buys time but can't reset the clock. The two-way blade coupling makes Subsystem
A's trajectory emergent — neither component's life is predictable from its own
drivers alone — which is the cascading-failure story the brief rewards.
Nominal calibration: blade FAILED at ~5–6 months, rail at ~6 months, blade
first. Crank `production_load` + `humidity` and zero `maintenance_quality`
and the rail flips ahead, triggering the cascade.

## References

- L10 Life — Bearing Rating Life. *MaximoMastery*. <https://maximomastery.com/terms/l10-life/>
- What is L10 life and why does it matter? *Linear Motion Tips*. <https://www.linearmotiontips.com/what-is-l10-life-and-why-does-it-matter/>
- Life Calculation for Linear Guide Roller Bearings. *PBC Linear*. <https://pbclinear.com/blogs/blog/calculating-the-life-of-linear-roller-bearings>
- Damage Analysis for Linear Guides. *NSK Europe*. <https://www.nskeurope.com/en/news-media/news-search/2012-press/damage-analysis-for-linear.html>
- Method of Failure Diagnostics to Linear Rolling Guides in Handling Machines. *Sensors / PMC* (2023). <https://pmc.ncbi.nlm.nih.gov/articles/PMC10099071/>
- Stress-Based Weibull Method to Select a Ball Bearing and Determine Its Actual Reliability. *MDPI Applied Sciences* 10/22/8100. <https://www.mdpi.com/2076-3417/10/22/8100>
- Statistical investigation of the fatigue life of deep-groove ball bearings. *NIST JRES* 57/5. <https://nvlpubs.nist.gov/nistpubs/jres/057/jresv57n5p273_A1b.pdf>
- Linear Axis Guide Rail Misalignment Detection. *MDPI Applied Sciences* 14/6/2593. <https://www.mdpi.com/2076-3417/14/6/2593>
- Top Five Errors in using Linear Guides. *Shafttech*. <https://blog.shafttech.com/article/top-five-errors-that-people-make-in-using-linear-guides/>
- Things to Note When Lubricating Linear Guides. *CSK Motions*. <https://www.cskmotions.com/blogs/news/things-to-note-when-lubricating-linear-guides>

## Open questions

- **η = 220 d calibration.** Tuned to land just past the blade. Swap in a real
  HP S100 carriage-rail MTBF if we find one.
- **Pitting fraction 0.4.** Sets the irreversibility floor. Sensitivity sweep
  recommended.
- **Direct contamination coupling.** Rail treated as sealed; if powder ingress
  matters, add `k_contam = 1 + 0.4·C` gated on a "wiper-seal-degraded" sub-state.
- **Vibration observable.** PMC 10099071 shows pitting raises vibration RMS;
  expose `vibration_rms = f(D_pit)` as a secondary observable in Phase 2.
- **Load-life exponent p = 3.** Linearised; switch `k_load` to
  `(0.5 + 1.5·L)^3` if doc 06 introduces sharp load spikes.
