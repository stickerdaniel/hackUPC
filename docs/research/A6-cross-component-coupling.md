# A6 — Cross-Component Coupling

## TL;DR

One coupling to defend: **recoater blade health below 0.3 raises the
`contamination` driver in the nozzle-plate NHPP clog model, increasing
nozzle clog rate by up to ~2x**.  The mechanism is physical, the math
is simple, and it slots directly into the existing A2 model via one
line of code.

---

## Background

The HP Metal Jet S100 printhead travels 1–3 mm above the powder bed.
Binder droplets impact at high velocity and eject metal powder particles
upward (confirmed by synchrotron X-ray imaging; Chen et al., *Sci.
Reports* 2019).  The higher the bed surface roughness, the more chaotic
the impact, and the more particles are launched toward the nozzle plate.

The A2 nozzle-plate model already accepts a `contamination` driver
(normalized 0–1) with sensitivity `BETA_CONTAM = 1.5` in the NHPP clog
hazard:

```
lambda(t) = lambda_0 * exp(alpha * |temp_stress - T_opt| + beta_c * contamination)
```

The coupling question reduces to: what makes `contamination` go up?

---

## Options Considered

| Candidate coupling | Physical mechanism | Defensibility |
|---|---|---|
| **Blade health -> contamination driver -> nozzle clog rate** | Worn blade leaves rougher powder bed; rough bed amplifies droplet-ejection splash; more airborne particles reach nozzle plate 1–3 mm above | Strong: three well-documented sub-steps, each independently cited |
| Heater degradation -> binder temperature rise -> clog rate | Weakened heater fires hotter; higher temperature flashes binder at nozzle; viscosity excursion clogs nozzle | Moderate: thermal fatigue already modeled in A2; added coupling doubles a mechanism already captured |
| Blade wear -> powder layer non-uniformity -> binder saturation error -> green-part porosity | Rough bed alters packing density; binder spreads unevenly; sintered part has higher porosity | Weak for demo: no cascade to printhead; affects downstream part quality, not a sensor-visible failure in real time |

**Decision:** blade-health -> contamination -> nozzle clog rate.

---

## Recommendation

### The one link

```
contamination(t) = contamination_base + C_scale * max(0, 0.3 - blade_health(t))
```

- `contamination_base` = 0.05 (ambient, always-on powder aerosol)
- `C_scale` = 3.0 (dimensionless scale factor)
- Trigger threshold: **blade_health < 0.3**
- At blade_health = 0.3:  contamination = 0.05 (no coupling effect)
- At blade_health = 0.0 (fully failed blade): contamination = 0.05 + 3.0 * 0.3 = **0.95**

### Effect on clog hazard

Substitute into the A2 NHPP with `alpha * |temp_stress| = 0` for
baseline clarity:

| blade_health | contamination | lambda multiplier exp(1.5 * c) |
|---|---|---|
| 1.0 (new) | 0.05 | exp(0.075) = **1.08x** |
| 0.3 (threshold) | 0.05 | exp(0.075) = **1.08x** |
| 0.15 | 0.50 | exp(0.75) = **2.12x** |
| 0.0 (failed) | 0.95 | exp(1.425) = **4.16x** |

The clog rate roughly doubles at mid-degradation (blade_health ~0.15)
and quadruples at full failure — a large but not implausible range for
a contamination-sensitive inkjet nozzle operating over metal powder.

### Implementation (one line in the simulator tick)

```python
contamination = CONTAM_BASE + C_SCALE * max(0.0, BLADE_THRESHOLD - blade_health)
# then feed contamination into A2 lambda(t) as before
```

### Why this is defensible to skeptical judges

1. **Physical sub-steps are each cited:** (a) worn blade -> rougher bed
   (EOS GmbH recoater study; ScienceDirect powder-bed roughness
   literature); (b) rough bed -> higher droplet-ejection splash (Chen
   et al. X-ray imaging, 2019; Argonne NAISE powder-ejection study);
   (c) airborne metal particles at 1–3 mm gap -> nozzle contamination
   (ImageXpert inkjet AM contamination guide; Wikipedia binder-jetting).

2. **It is already plumbed in.** The A2 model has `contamination` as an
   explicit input; the coupling is one assignment, not a new model.

3. **Direction of effect is monotone and physically bounded.** More wear
   -> more roughness -> more splash -> more contamination. Capping
   `contamination` at 1.0 prevents runaway.

4. **No circular dependency.** Blade degrades independently (A1 abrasive
   wear model); contamination is derived from blade_health; nozzle model
   consumes contamination. One-way data flow.

---

## Open Questions

1. The C_scale = 3.0 is estimated from physical reasoning, not empirical
   data.  A sensitivity sweep in the demo (show how fast nozzles clog at
   C_scale = 1 vs 3 vs 5) is the honest way to present uncertainty.

2. Splash ejection height in X-ray studies reaches hundreds of microns,
   but the fraction of particles crossing the full 1–3 mm gap to the
   nozzle plate is not directly quantified.  The coupling magnitude is
   plausible but unvalidated.

3. If the simulator runs stochastic mode (B6), draw clog events from
   `Poisson(lambda_t * remaining_nozzles)` where lambda_t already
   incorporates the contamination bump from blade state.

4. Should a maintenance purge that recovers nozzle clogs also partially
   reset contamination?  Likely yes; tie to `maintenance_level` driver.

---

## References

- [Real-time observation of binder jetting using high-speed X-ray imaging — Chen et al., *Sci. Reports* 2019](https://www.nature.com/articles/s41598-019-38862-7)
- [Powder ejection in binder jetting — Argonne NAISE 2018](https://wordpress.cels.anl.gov/naise-students/2018/09/16/powder-ejection-in-binder-jetting-additive-manufacturing/)
- [Three common issues with inkjet additive manufacturing — ImageXpert](https://imagexpert.com/three-common-issues-with-inkjet-additive-manufacturing-and-how-to-address-them/)
- [How Metal AM recoater blades impact build quality — EOS GmbH](https://www.eos.info/content/blog/recoater-material-metal-additive-manufacturing)
- [Laser powder bed fusion recoater selection guide — ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0032591023011403)
- [Powder bed and inkjet head 3D printing — Wikipedia](https://en.wikipedia.org/wiki/Powder_bed_and_inkjet_head_3D_printing)
- [High-speed X-ray imaging of droplet-powder interaction in binder jet AM — ScienceDirect 2024](https://www.sciencedirect.com/science/article/abs/pii/S2214860424003154)
- [A2 nozzle-plate model (this repo)](./A2-nozzle-plate-clogging-thermal-fatigue.md)
