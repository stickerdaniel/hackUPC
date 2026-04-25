# Component 10 — Recoater Blade

> Subsystem: **Recoating** · Failure law: **Archard wear**
> Source: `sim/src/copilot_sim/components/blade.py`

---

## 1. Subsystem and role

The recoater blade spreads a thin, even layer of metal powder (316L or 17-4 PH stainless) across the build platform before each binder-jetting pass. The S100's powder bed is 430 × 309 mm; every layer (35–140 µm) requires a fresh, smooth blade pass. A worn or chipped blade produces streaking → uneven powder bed → bad binder absorption → quality defects in the final part.

In the model, the blade is paired with the linear rail under the **Recoating** subsystem; together they determine `powder_spread_quality`, the upstream factor that downstream components (especially the nozzle) react to.

---

## 2. Physical mechanism in plain English

Each pass through the powder bed slides the blade's edge against thousands of hard metal-powder grains. Most grains harmlessly skim across; a small fraction abrades a microscopic amount of the blade's edge material. Over time:

- The edge **rounds** (loses sharpness) — captured as `wear_level`.
- The leading edge **dulls** before the bulk wears through — captured as `edge_roughness` (lags wear at 0.7×).
- Total **thickness** decreases linearly with wear — captured as `thickness_mm`.

The wear is **accelerated** when:
- Powder is **contaminated** (humidity-bound powder grits act as a more aggressive abrasive).
- The bed is **hot** (thermal softening of the blade's hardened steel — Vickers hardness drops with temperature).
- The print queue is **heavy** (more passes per week → more sliding distance → more wear).

---

## 3. The textbook law — Archard wear

**Archard's law (1953)** — the universal scalar model for abrasive sliding wear:

$$ V = \frac{k \cdot F \cdot s}{H} $$

- $V$ = wear volume removed
- $k$ = wear coefficient (material-pair dependent)
- $F$ = normal force pressing blade against bed
- $s$ = sliding distance
- $H$ = hardness of the worn surface

The standard reference is *J.F. Archard, "Contact and Rubbing of Flat Surfaces", J. Appl. Phys. 24 (1953)*, used directly in PBF recoater wear papers (`docs/research/22` cites two ScienceDirect studies).

We translate this into a per-tick wear increment by mapping each Archard term to one driver, scaling each as a sub-unity multiplier so the formula remains bounded.

---

## 4. The implementation

```python
# sim/src/copilot_sim/components/blade.py:64

def step(prev_self, coupling, drivers, env, dt, rng):
    temp_eff  = coupling.temperature_stress_effective
    humid_eff = coupling.humidity_contamination_effective
    load_eff  = coupling.operational_load_effective
    damp      = maintenance_damper(coupling.maintenance_level_effective)

    hardness_factor = 1.0 + 0.10 * temp_eff      # H in denominator: hot bed → softer
    k_amplifier     = 1.0 + 0.5  * humid_eff     # k in numerator: moisture → grittier
    f_amplifier     = 1.0 + 0.6  * load_eff      # F in numerator: heavier queue
    s_scale         = max(env.weekly_runtime_hours / 60.0, 0.0)   # s normalized

    wear_increment = (BASE_WEAR_INCR
                      * hardness_factor * k_amplifier * f_amplifier
                      * s_scale * damp * dt)

    new_wear      = clip01(prev_wear + wear_increment)
    new_rough     = clip01(prev_rough + 0.7 * wear_increment)
    new_thickness = max(0.5, 1.0 - 0.5 * new_wear)

    age      = prev_self.age_ticks + 1
    baseline = weibull_baseline(age, ETA_WEEKS, BETA)
    health   = clip01(baseline * (1.0 - new_wear))
```

`BASE_WEAR_INCR = 0.04` per week. RNG is unused (Archard is deterministic — no Poisson chipping in v1).

---

## 5. Driver pull-throughs

| Brief driver | Archard term | Code factor |
|---|---|---|
| `temperature_stress` | `H` (hardness) — softens with temperature | `hardness_factor = 1 + 0.10·temp_eff` |
| `humidity_contamination` | `k` (wear coefficient) | `k_amplifier = 1 + 0.5·humid_eff` |
| `operational_load` | `F` (normal force / queue intensity) | `f_amplifier = 1 + 0.6·load_eff` |
| `maintenance_level` | global damper | `damp = 1 − 0.8·M` (clamped to [0.2, 1.0]) |
| (`Environment.weekly_runtime_hours`) | `s` (sliding distance) | `s_scale = weekly_runtime_hours / 60` |

**All four brief drivers feed the blade.** The audit-grep test (`tests/engine/test_driver_coverage.py`) verifies strict monotonicity in each.

---

## 6. Anchor numbers

Source: `docs/research/22-printer-lifetime-research.md` §1.

| Parameter | Value | Rationale |
|---|---:|---|
| η (characteristic life) | **17 weeks ≈ 120 days** | Matches *Inside Metal AM* 2024 + ScienceDirect S221384632200102X recoater-blade lifetime studies; HSS blades in PBF last 100–500 build hours under nominal contamination |
| β (Weibull shape) | **2.5** | Mechanical wear-out band (1.5–4 per Accendo Reliability) |
| Base rate | **0.04 / week** | Calibrated to match field reports of "blade replacement every 6 months under nominal drivers" |
| FAILED at | **wear ≥ 50 %** | doc 04 anchor — at 50% loss the blade can't spread powder uniformly |

---

## 7. Health composition

```python
H_total = clip01( weibull_baseline(age, η=17, β=2.5) × (1 − wear_level) )
```

This is the **doc 04 multiplicative composition rule**:

- `weibull_baseline(t) = exp(-(t/η)^β)` is the calendar-aging curve.
- `(1 − wear_level)` is the metric-derived health.
- Multiplying composes the two failure modes per series-reliability theory.

If a judge asks "why multiplicative?" — the answer: independent failure modes compose multiplicatively; additive can produce H > 1; min() collapses synergy. See `docs/research/04-aging-baselines-and-normalization.md`.

---

## 8. Maintenance reset rules

```python
def reset(prev_self, kind, payload):
    if kind in (FIX, REPLACE):
        return initial_state()       # back to wear=0, age=0, full thickness
    return prev_self                  # TROUBLESHOOT: no state change
```

Per `docs/research/09-maintenance-agent.md`: **the blade is a consumable, not field-repairable.** Real PBF blades are replaced when streaking appears — there's no "fix" in industry. The code routes both FIX and REPLACE to `initial_state()`.

This is **defensible by industrial practice**: EOS sells HSS and ceramic blades as standard spares (no repair line). `docs/research/22` cites the field rule "100–500 build-hours per HSS blade".

---

## 9. What this model abstracts away

1. **No grain-scale topology** — `wear_level` is a single scalar. Real blade wear has uneven patterns (centre vs edges) that produce different streaking signatures.
2. **`edge_roughness` is a deterministic 0.7× lag of wear**. In reality a single hard chip event can spike roughness independent of bulk wear.
3. **No Poisson chipping**. A 5 % humidity burst from chaos can't currently produce a sudden +0.1 roughness step.
4. **Sliding distance = `weekly_runtime_hours / 60`**, not actual passes-per-build × bed-length × layer-count.
5. **Wear coefficient `k` has no temperature dependency** in the formula (only `H` softens with temperature). Real Archard `k_eff` is itself temperature-dependent in Ni-Cr-coated steels.

These are honest abstractions for the part-level scope the brief sets. None invalidate the model; they bound how realistic the failure-attribution story can be.

---

## 10. Improvements queued

See [`../23-improvement-roadmap.md`](../23-improvement-roadmap.md) for the full plan. Blade-relevant items:

- **B2.3** — Bidirectional rail↔blade coupling via shared `carriage_friction` factor (3 h). Closes the rail↔blade loop the README claims.
- **Tier 3** — Poisson chipping events (1 h). Random hard-contamination hits → instant roughness step. Adds stochastic realism to a currently smooth metric.
- **Tier 3** — Build-aware sliding distance: `s ∝ builds_per_week × layers_per_build × bed_traversal` (2 h). Replaces the runtime-hour heuristic with a physically-grounded distance.

---

## Cross-references

- The blade's contribution to upstream cascades: [`../03-coupling-and-cascades.md`](../03-coupling-and-cascades.md) §Cascade 1 (powder), §Cascade 5 (rail↔blade).
- Engine-side step contract: [`../02-engine-architecture.md`](../02-engine-architecture.md).
- Driver origin: [`../01-data-contract.md`](../01-data-contract.md).
- Maintenance philosophy: [`../21-policy-and-maintenance.md`](../21-policy-and-maintenance.md).
- Research backing: `docs/research/01-recoater-blade-archard.md`, `docs/research/22-printer-lifetime-research.md` §1.
