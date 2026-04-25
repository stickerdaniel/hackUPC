# Component 13 — Cleaning Interface

> Subsystem: **Printhead Array** · Failure law: **Power-law wear-per-cycle**
> Source: `sim/src/copilot_sim/components/cleaning.py`

---

## 1. Subsystem and role

The cleaning interface (also called wiper + capping station) is the printhead's life-support system. Between print cycles it:

- **Wipes** the nozzle plate to remove binder residue and prevent clog accretion.
- **Caps** the nozzles when idle to prevent binder evaporation.
- **Recovers** clogged nozzles via a focused purge cycle.

HP's S100 service station does optical drop detection + nozzle recovery on every print job — the wiper sees **dozens of cleaning cycles per build day**, far heavier duty than a textile-printer wiper.

In the model, the cleaning interface is paired with the nozzle plate under the **Printhead Array** subsystem. Its derived `cleaning_effectiveness` is exported as the `cleaning_efficiency` coupling factor that modulates the nozzle's Poisson clog rate.

---

## 2. Physical mechanism in plain English

Two parallel decay paths:

### Path A — Wiper wear (use-driven, power-law)

Each cleaning cycle scrapes the wiper blade against the nozzle plate. Over thousands of cycles, the wiper's elastomer (or polymer) edge:
- Wears down (`wiper_wear` ↑).
- Becomes saturated with binder residue (`residue_saturation` ↑).
- Loses its squeegee profile (effectiveness drops).

This is a **power-law in cumulative cycles**, not in calendar time. A wiper that does 100 cleanings/day for a week is far more worn than one idle for the same week.

### Path B — Calendar shelf-life (Weibull baseline)

Even an idle wiper degrades from elastomer hardening, UV exposure, binder solvent contamination — slow but non-zero. Captured by the standard Weibull baseline at η = 50 weeks.

The composite **`cleaning_effectiveness = 1 − 0.7·wiper_wear − 0.3·residue_saturation`** is what feeds the rest of the system.

---

## 3. The textbook law — Power-law wear-per-cycle

From `docs/research/18-cleaning-interface.md`:

$$ H_\text{use}(n) = 1 - a \cdot n^p $$

- $n$ = cumulative cleaning cycles
- $a, p$ = material constants (rubber wipers vs polymer differ)
- The decay is **monotonic and accelerating** in $n^p$ (power-law, not exponential)

The reference standard is industrial inkjet maintenance literature — Digiprint USA, Splashjet, InPlant Impressions all describe wiper-blade replacement on a cycle-count basis (every 2–3 months under normal volume, monthly in high-volume production).

---

## 4. The implementation

```python
# sim/src/copilot_sim/components/cleaning.py:62

def step(prev_self, coupling, drivers, env, dt, rng):
    temp_eff  = coupling.temperature_stress_effective
    humid_eff = coupling.humidity_contamination_effective
    load_eff  = coupling.operational_load_effective
    damp      = maintenance_damper(coupling.maintenance_level_effective)

    cleanings_this_week = max(env.weekly_runtime_hours / 4.0, 0.0)
    binder_drying       = 1.0 + 0.20 * temp_eff      # dries binder onto wiper
    residue_amp         = 1.0 + 0.60 * humid_eff     # saturates residue pad
    load_amp            = 1.0 + 0.40 * load_eff      # throughput pressure

    wiper_increment = (WEAR_PER_CLEANING * cleanings_this_week
                       * binder_drying * load_amp * residue_amp * damp * dt)
    residue_increment = RESIDUE_BASE_INCR * residue_amp * binder_drying * damp * dt

    new_wear          = clip01(prev_wear + wiper_increment)
    new_residue       = clip01(prev_residue + residue_increment)
    new_effectiveness = clip01(1.0 - 0.7 * new_wear - 0.3 * new_residue)

    age      = prev_self.age_ticks + 1
    baseline = weibull_baseline(age, ETA_WEEKS, BETA)
    health   = clip01(baseline * new_effectiveness)
```

`WEAR_PER_CLEANING = 0.003` per cycle, `RESIDUE_BASE_INCR = 0.012` per week.

The 0.7/0.3 weighting on `cleaning_effectiveness` says: **wiper wear matters more than residue saturation** for the cleaning station's overall ability to recover clogs. Residue is reversible (purge); wiper wear is not (until replacement).

---

## 5. Driver pull-throughs

| Brief driver | Affects | Code factor |
|---|---|---|
| `temperature_stress` | dries binder onto wiper edge | `binder_drying = 1 + 0.20·temp_eff` |
| `humidity_contamination` | saturates residue pad | `residue_amp = 1 + 0.60·humid_eff` |
| `operational_load` | throughput pressure → more cleanings per week | `load_amp = 1 + 0.40·load_eff` |
| `maintenance_level` | shared damper | `damp = 1 − 0.8·M` |
| (`Environment.weekly_runtime_hours`) | cleanings count | `cleanings_this_week ≈ runtime / 4` |

**All four drivers feed cleaning.** The audit-grep test verifies monotonicity.

---

## 6. Anchor numbers

Source: `docs/research/22-printer-lifetime-research.md` §4 + `docs/research/04` cleaning row.

| Parameter | Value | Rationale |
|---|---:|---|
| η (Weibull shelf-life) | **50 weeks ≈ 350 days** | Calendar shelf-life floor; industrial inkjet wipers are 2–3 months in high-volume production but the calendar floor is up to a year on lightly-used systems. **Note**: doc 22 anchors the use-driven life at 75 days, but the Weibull here is the *shelf-life backstop*, not the use-driven decay (which is dominant) |
| β (Weibull shape) | **1.5** | Light wear-out (cleaner is replaceable, not catastrophic) |
| `WEAR_PER_CLEANING` | **0.003** | Calibrated for ~5 % wiper wear after 16 weeks at 60 cleanings/week |
| `RESIDUE_BASE_INCR` | **0.012 / week** | Slow residue build-up under nominal humidity |
| FAILED at | **`cleaning_effectiveness < 0.15`** | doc 04 anchor |

The cleaning interface is **calendar-fast but use-driven** — the dominant decay is the power-law cycle-wear, with the Weibull as backstop.

---

## 7. Health composition

```python
H_metric    = 1 - 0.7·wiper_wear - 0.3·residue_saturation
H_baseline  = exp(-(age/η)^β)
H_total     = clip01(H_baseline × H_metric)
```

`cleaning_effectiveness` IS `H_metric` (the metric is already in [0,1]). The dashboard exposes `cleaning_effectiveness` directly — no separate health column needed.

---

## 8. Maintenance reset rules

```python
def reset(prev_self, kind, payload):
    if kind in (FIX, REPLACE):
        return initial_state()
    return prev_self
```

Per `docs/research/09-maintenance-agent.md`:

- **`FIX`** = wiper-blade swap (the ONLY field-repairable action). Returns initial state.
- **`REPLACE`** = full station swap. Also returns initial state.
- **`TROUBLESHOOT`** = no change.

The cleaning interface is a **consumable**, so FIX and REPLACE both reset to initial state. Doc 09 explicitly notes "no field-repairable FIX (already a full reset of the wear path)". This matches industrial practice: Digiprint USA + Splashjet treat wiper-blade replacement as a single SKU swap.

---

## 9. What this model abstracts away

1. **`cleanings_this_week ≈ weekly_runtime_hours / 4`** is a heuristic. The actual cumulative cleaning count lives in `Environment.cumulative_cleanings` but **cleaning.py doesn't read it** — the field is unused. Real cycle-count tracking would tie wiper wear to the loop's `start_stop_cycles` counter.
2. **No reverse arrow from nozzle clog**. README claims `nozzle.clog_pct → cleaning.wear_factor += 0.4 × clog_pct/100` — *not in code*. Clogged nozzles should accelerate wiper wear because the wiper does more work per cycle.
3. **Power-law exponent `p` is implicit** in `WEAR_PER_CLEANING × cleanings × ...` — not exposed as a tunable parameter for material-mode comparison.
4. **Wiper material modes**: rubber wipers wear differently from polymer ones. Single curve in code.
5. **No purge-cycle refinement**. Real cleaning stations distinguish "wipe" from "purge" — purge is more aggressive but used only on flagged nozzles. Single mode here.

---

## 10. Improvements queued

See [`../23-improvement-roadmap.md`](../23-improvement-roadmap.md):

- **B1.4** — Use `Environment.cumulative_cleanings` in the cleaning step (10 min). Plumbs the unused field. Power-law wear-per-cycle becomes driven by *real cycles*, matching doc 18's intent.
- **B1.6** — Add nozzle→cleaning reverse arrow (15 min). Closes the printhead-pair feedback loop.
- **Tier 3** — Material-mode selector (rubber vs polymer) on a per-scenario basis. Different curves expose more variability for what-if scenarios.

---

## Cross-references

- Cleaning's role in the cascade map: [`../03-coupling-and-cascades.md`](../03-coupling-and-cascades.md) §Cascade 4 (cleaning ↔ nozzle pair).
- The forward arrow into nozzle: [`12-nozzle.md`](12-nozzle.md) §4 (consumed via `coupling.factors["cleaning_efficiency"]`).
- Maintenance philosophy: [`../21-policy-and-maintenance.md`](../21-policy-and-maintenance.md).
- Research backing: `docs/research/18-cleaning-interface.md`, `docs/research/22-printer-lifetime-research.md` §4.
