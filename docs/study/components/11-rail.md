# Component 11 — Linear Rail

> Subsystem: **Recoating** · Failure law: **Lundberg-Palmgren cubic load-life**
> Source: `sim/src/copilot_sim/components/rail.py`

---

## 1. Subsystem and role

The linear rail (rolling-element bearing assembly) carries the recoater carriage — and on some mechanical layouts the printhead carriage too — across the build platform with sub-100 µm precision. NSK and THK manufacture this class of bearing for industrial AM, CNC, and pick-and-place machines. The rail's job is to keep the blade's height consistent across the bed; misalignment of more than 50 µm causes uneven powder layers.

In the model, the rail is paired with the blade under the **Recoating** subsystem. The rail's `misalignment` metric feeds `powder_spread_quality` alongside the blade's wear.

---

## 2. Physical mechanism in plain English

Rolling-element bearings fail by **subsurface fatigue**:
- Each pass loads the raceway (the surface the balls/rollers run on) with a Hertzian contact stress.
- Stress cycles eventually nucleate micro-cracks below the surface.
- Micro-cracks coalesce into spalls (raceway pitting) — once visible, the damage is **permanent**: re-greasing won't recover it.
- Pitting causes vibration and increases play → carriage misaligns.

The rail also degrades from:
- **Lubricant breakdown** (hot ambient → thinner film → metal-on-metal contact zones).
- **Corrosion** (humidity-driven raceway oxidation).
- **External vibration** (from the carriage motor, building, or paired-carriage interactions).

---

## 3. The textbook law — Lundberg-Palmgren cubic

**The L₁₀ life formula** (NSK and THK datasheets use this directly):

$$ L_{10} = \left(\frac{C}{P}\right)^3 \cdot \text{rated travel} $$

- $L_{10}$ = travel distance at which 10 % of identical bearings have failed
- $C$ = basic dynamic load rating (manufacturer constant)
- $P$ = equivalent dynamic load applied
- Cubic exponent because the contact-stress-to-fatigue-life relationship is cube-root in the Hertzian model

A bearing run at half its rated load lasts **8×** as long. Run at 2× its rated load → **1/8th** the life. This cubic dependence is what makes operational_load matter so much for the rail (and not so much for, say, the blade).

The standard reference is *Lundberg & Palmgren (1947, 1952)*, formalized in ISO 281.

---

## 4. The implementation

```python
# sim/src/copilot_sim/components/rail.py:63

def step(prev_self, coupling, drivers, env, dt, rng):
    temp_eff  = coupling.temperature_stress_effective
    humid_eff = coupling.humidity_contamination_effective
    load_eff  = coupling.operational_load_effective
    damp      = maintenance_damper(coupling.maintenance_level_effective)

    load_amplifier   = 1.0 + 4.0 * (load_eff ** 3)        # the cubic exponent — visible
    visc_factor      = 1.0 + 0.10 * temp_eff              # lubricant viscosity
    corrosion_factor = 1.0 + 0.40 * humid_eff             # raceway corrosion
    vib_factor       = 1.0 + 0.5 * env.vibration_level    # external vibration

    damage_increment = (BASE_DAMAGE_INCR
                        * load_amplifier * visc_factor * corrosion_factor
                        * vib_factor * damp * dt)

    new_misalign    = clip01(prev_misalign + damage_increment)
    new_friction    = clip01(prev_friction + 0.6 * damage_increment)
    new_alignment_um = prev_alignment_um + ALIGNMENT_UM_AT_FAILURE * damage_increment

    age      = prev_self.age_ticks + 1
    baseline = weibull_baseline(age, ETA_WEEKS, BETA)
    health   = clip01(baseline * (1.0 - new_misalign))
```

`BASE_DAMAGE_INCR = 0.012` per week. The cubic exponent `(load_eff ** 3)` is **literally visible** in the formula — that's the whole point of the modeling choice.

---

## 5. Driver pull-throughs

| Brief driver | Lundberg-Palmgren term | Code factor |
|---|---|---|
| `operational_load` | `(C/P)³` — dominant cubic | `load_amplifier = 1 + 4·load_eff³` |
| `temperature_stress` | lubricant viscosity | `visc_factor = 1 + 0.10·temp_eff` |
| `humidity_contamination` | raceway corrosion | `corrosion_factor = 1 + 0.40·humid_eff` |
| `maintenance_level` | global damper | shared `(1 − 0.8·M)` |
| (`Environment.vibration_level`) | external vibration | `vib_factor = 1 + 0.5·vib_level` |

**All four drivers feed the rail.** The audit-grep test verifies strict monotonicity in load (which is the dominant term).

---

## 6. Anchor numbers

Source: `docs/research/22-printer-lifetime-research.md` §2.

| Parameter | Value | Rationale |
|---|---:|---|
| η (characteristic life) | **77 weeks ≈ 540 days ≈ 18 months** | Matches NSK + THK datasheet L₁₀ at typical AM duty (~10 % of C). Industry roll-up: 10,000–30,000 operating hours under normal CNC/AM duty |
| β (Weibull shape) | **2.0** | Rolling-contact pitting band (1.5–2.5 per NSK + NIST) |
| Base damage rate | **0.012 / week** | Slowest-decaying component; should outlive 3–5 blade swaps |
| FAILED at | **50 µm alignment error** | Industrial CNC tolerance for AM-grade rails |

The rail is **deliberately the slowest component** in the model so the demo's narrative arc has a "long-lifetime backstop" against the faster blade and nozzle drama.

---

## 7. Health composition

```python
H_total = clip01( weibull_baseline(age, η=77, β=2.0) × (1 − misalignment) )
```

`misalignment` is the [0,1] normalized version; `alignment_error_um` is the operator-friendly physical reading. The dashboard shows µm; the math uses [0,1].

---

## 8. Maintenance reset rules

```python
def reset(prev_self, kind, payload):
    if kind is REPLACE:
        return initial_state()
    if kind is FIX:
        return ComponentState(
            ...
            metrics={
                "misalignment": prev.misalignment,             # NOT reset (pitting permanent)
                "friction_level": 0.5 * prev.friction_level,   # halved (lubricant restored)
                "alignment_error_um": prev.alignment_error_um, # NOT reset
            },
            age_ticks=prev_self.age_ticks,                     # age preserved on FIX
        )
    return prev_self
```

This is the **most rigorous maintenance model** in the simulator. Per `docs/research/09-maintenance-agent.md`:

- **`FIX`** = re-grease + corrosion clean. Recovers the **lubricant film** (friction_level halved) but not the **raceway pitting** (alignment_error_um and misalignment preserved).
- **`REPLACE`** = full bearing swap. Initial state.

This matches NSK technical-support guidance: *contaminated bearings can be re-greased but raceway micro-pitting from prior contamination is irreversible*. Doc 09's rule `D_corr ← 0.5·D_corr` is honored (we halve `friction_level`).

If a judge says "is your maintenance realistic?" — the rail is your strongest answer. **Permanent damage is permanent**, exactly as in industry.

---

## 9. What this model abstracts away

1. **`vibration_level` is a static `Environment` field**, not a function of carriage acceleration or paired-carriage coupling. Real vibration scales with motor torque and carriage mass.
2. **No discrete pitting event model**. In real bearings, raceway pitting starts as a single Hertzian sub-surface crack that suddenly accelerates above a stress threshold. Currently misalignment grows smoothly via the polynomial `(1 + 4·load³)`.
3. **Lubricant degradation is conflated with friction**. Real rails have a separate lubricant-film-thickness state that re-greasing recovers but pitting damage doesn't. We collapse both into `friction_level`.
4. **`load_amplifier = 1 + 4·load³` is a polynomial fit**, not literal `P³ × dt`. Audit-grep tests verify monotonicity in load, but the exact L₁₀ formula `(C/P)³ × hours` would be more rigorous.

---

## 10. Improvements queued

See [`../23-improvement-roadmap.md`](../23-improvement-roadmap.md):

- **B2.3** — Bidirectional rail↔blade coupling via `carriage_friction` factor (3 h). Both blade and rail step functions read the new factor; explicit two-way loop.
- **Tier 3** — Discrete pitting event model. Bernoulli per-tick at high load with a stress-threshold gate. Above threshold, `damage_increment` doubles instantaneously.
- **Tier 3** — Separate `lubricant_thickness` metric (re-greasable) from `pitting_damage` (permanent). Already implicit; making it explicit improves dashboard readability.

---

## Cross-references

- Rail's contribution to upstream cascades: [`../03-coupling-and-cascades.md`](../03-coupling-and-cascades.md) §Cascade 1 (powder), §Cascade 5 (rail↔blade).
- Engine-side step contract: [`../02-engine-architecture.md`](../02-engine-architecture.md).
- Maintenance philosophy: [`../21-policy-and-maintenance.md`](../21-policy-and-maintenance.md).
- Research backing: `docs/research/17-linear-rail.md`, `docs/research/22-printer-lifetime-research.md` §2.
