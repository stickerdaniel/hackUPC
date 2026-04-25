# A1 — Recoater Blade: Abrasive Wear via Archard's Law

## TL;DR

Model the recoater blade's remaining thickness (mm) using a discretised Archard
wear law: each print cycle removes a small but cumulative slice of material.
Humidity/contamination scales the wear coefficient k linearly between a dry
baseline and a wet ceiling, giving a 2–5× amplification at high humidity based
on empirical tribology data.

---

## Background

### Archard's wear law

```
V = k · F · s / H
```

| Symbol | Meaning | Units |
|--------|---------|-------|
| V | volume of material removed | mm³ |
| k | dimensionless wear coefficient (probability of debris formation per asperity contact) | — |
| F | normal contact force of blade on powder bed | N |
| s | total sliding distance per cycle (≈ build-box stroke) | mm |
| H | hardness of the softer surface (blade, if softer than powder particles) | N/mm² = MPa |

The equation was originally derived for adhesive wear but is widely applied to
abrasive and powder-sliding contacts. For mild wear k ≈ 10⁻⁸; for severe wear
k ≈ 10⁻² (Archard 1953 / tribonet.org summary). Hardened HSS recoater blades
(HRC 62–66, H ≈ 7 500 MPa) operate firmly in the mild-wear regime when
spreading fine metal powder (10–45 µm particles).

### HP Metal Jet S100 geometry (confirmed specs)

- Build volume: 430 × 309 × 140 mm  
- Layer thickness: 35–140 µm (nominal 50 µm at 1 990 cc/hr)  
- Recoater stroke per layer s ≈ 430 mm (X-axis traverse)  
- Blade material: HSS (standard for non-magnetic metal powders in LPBF/BJ
  systems; ceramic used only for magnetisable alloys)

### Humidity and contamination effects on k

Literature on steel-on-abrasive and rail-steel sliding shows wear rate is
strongly non-linear with relative humidity (RH):

- At low RH (<30%) → fatigue-dominated, relatively low wear  
- Transition to severe wear at ~45–52% RH for carbon steels  
- Above 60–80% RH abrasive oxide debris forms and acts as a third-body
  abrasive, accelerating wear; one study (100Cr6 self-mated) recorded a
  ~44× difference between 28% and 80% RH  
- For the binder-jet environment (dry-room target ~30–40% RH) the practical
  operating range spans roughly 1.0× (clean/dry) to ~3× (contaminated/humid)

Abrasive mass with moisture content drives corrosive-abrasive synergy
(tribocorrosion), further raising the effective k. A practical engineering
approximation: treat contamination level C ∈ [0, 1] as a linear multiplier on k
between k_min (dry) and k_max (wet/contaminated).

---

## Options Considered

| Option | State metric | Pro | Con |
|--------|-------------|-----|-----|
| A | Remaining thickness (mm) | Directly interpretable, maps to failure threshold | Needs contact-area assumption to convert V → depth |
| B | Cumulative wear volume (mm³) | Archard-native | Less intuitive for health-index |
| C | Wear depth fraction (0→1) | Normalised | Hides absolute scale |

**Option A chosen.** Thickness loss per cycle:

```
Δt = V / A_contact = (k · F · s) / (H · A_contact)   [mm per cycle]
```

where A_contact is the blade edge area in contact with powder (blade width ×
contact depth, order ~1–2 mm²).

---

## Recommendation — Numeric Defaults for Code

```python
# Recoater Blade — Archard wear defaults
BLADE_THICKNESS_INITIAL_MM    = 3.0      # HSS blade, nominal new thickness
BLADE_THICKNESS_FAILURE_MM    = 1.5      # 50% worn → replace; below this,
                                         # layer uniformity degrades
BLADE_CONTACT_FORCE_N         = 2.0      # estimated light preload on powder bed
BLADE_STROKE_MM               = 430.0   # HP Metal Jet S100 X-axis build length
BLADE_HARDNESS_MPA            = 7_500.0 # HSS HRC 62-66 ≈ 750 HV ≈ 7 500 MPa
BLADE_CONTACT_AREA_MM2        = 1.5     # edge width × contact depth estimate

K_DRY_CLEAN                   = 3e-7   # mild abrasive wear, hardened steel on fine powder
K_WET_CONTAMINATED            = 1.5e-6 # ~5× dry; high humidity + powder contamination

def k_effective(humidity_norm: float) -> float:
    """humidity_norm in [0, 1] where 0=dry/clean, 1=max contamination."""
    return K_DRY_CLEAN + (K_WET_CONTAMINATED - K_DRY_CLEAN) * humidity_norm

def wear_per_cycle(k: float) -> float:
    """Returns blade thickness loss in mm for one print layer."""
    volume_mm3 = k * BLADE_CONTACT_FORCE_N * BLADE_STROKE_MM / BLADE_HARDNESS_MPA
    return volume_mm3 / BLADE_CONTACT_AREA_MM2

# Example: at 0% contamination → ~0.000 057 mm/cycle
# At 100% contamination → ~0.000 287 mm/cycle
# Blade life: ~5 200 cycles (dry) → ~1 040 cycles (wet/contaminated)
```

The simulator tick = 1 print cycle (1 layer). After each tick:

```python
blade_thickness -= wear_per_cycle(k_effective(humidity_contamination_driver))
```

---

## Open Questions

1. **Actual contact force F**: HP does not publish blade preload. The 2 N
   estimate is engineering judgment — if we can find EOS/Voxeljet service
   manuals, refine this.
2. **Contact area**: Blade edge geometry (chamfered vs square) changes A_contact
   significantly; may want to expose as a tunable parameter.
3. **Abrasive hardness vs blade hardness**: If 316L powder particles (HV ~200
   annealed) are far softer than the HSS blade (HV ~750), the blade effectively
   wears the powder not itself — k could be order of magnitude lower. Confirm
   which surface is "softer" in this abrasive contact.
4. **Operational load driver**: Should increased number of print jobs per day
   increase F (more aggressive recoat speed) or only s (more cycles)?

---

## References

Sources actually visited or confirmed reachable during research:

- Archard wear equation overview (2025): https://www.tribonet.org/wiki/archard-wear-equation/
- Archard equation — Wikipedia: https://en.wikipedia.org/wiki/Archard_equation
- Wear coefficient — Wikipedia: https://en.wikipedia.org/wiki/Wear_coefficient
- HP Metal Jet S100 specifications confirmed via search snippets: https://www.hp.com/us-en/printers/3d-printers/products/metal-jet.html
- HP Metal Jet S100 tech brochure (search snippet): https://3dprintingindustry.com/news/hp-launches-new-metal-jet-s100-3d-printer-at-imts-technical-specifications-and-pricing-214678/
- Humidity effects on wear of steel (100Cr6, ~44× variation 28%→80% RH): https://www.sciencedirect.com/science/article/abs/pii/S0043164819317387
- Atmospheric humidity and abrasive wear (2-body): https://www.sciencedirect.com/science/article/abs/pii/0043164875902008
- Atmospheric humidity and abrasive wear (3-body): https://www.sciencedirect.com/science/article/abs/pii/0043164875901702
- Effect of relative humidity on unlubricated wear of metals: https://www.sciencedirect.com/science/article/abs/pii/S0043164805002863
- ASME Contemporary review of Archard-type wear laws: https://asmedigitalcollection.asme.org/appliedmechanicsreviews/article/77/2/022101/1214387/A-Contemporary-Review-and-Data-Driven-Evaluation
- EOS HSS recoater blade product (HRC 62–66 confirmed): https://store.eos.info/collections/recoater-blades
- HSS blade material grades for SLM: https://winking3d.com/types-and-materials-of-recoater-blades-for-slm/
- Recoater blade selection framework (Springer, 2025): https://link.springer.com/article/10.1007/s44245-025-00118-2
- Binder jet process overview (layer 35–140 µm confirmed): https://www.additivemanufacturing.media/articles/am-101-binder-jetting
