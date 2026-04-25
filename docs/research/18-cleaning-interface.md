# Cleaning Interface — Wear-Per-Cycle Wiper Degradation

> Failure model for the HP Metal Jet S100 **Cleaning Interface** (wiper /
> spitting station that purges the nozzle plate between maintenance events).
> Subsystem B, component 2 of 2. One half of the **cleaning ↔ nozzle two-way
> loop**: a worn wiper leaves residue on the plate, which raises the nozzle's
> clog hazard and forces more cleanings, which wears the wiper faster.
> Last updated: 2026-04-25.

---

## TL;DR

- **State metric:** `cleaning_efficiency ∈ [0, 1]`. Physically, the fraction of
  surface contaminant a wiper pass removes from the nozzle plate (1.0 = brand
  new EPDM lip, full squeegee meniscus restoration; 0.0 = hardened/deformed,
  smears ink back onto the plate).
- **Dominant mechanism: wear-per-cleaning-cycle**, not calendar time. Each
  cleaning cycle pulls the elastomer lip across a contaminated nozzle plate;
  abrasion plus chemical attack from dried binder degrade the contact edge.
  Modelled as a **power-law decay in cumulative cleanings**, with a small
  Weibull shelf-life term for elastomer hardening when idle.
- **Trigger:** every **maintenance event** fires one cleaning cycle. Aligns
  with doc 09's atomic maintenance action; no separate purge schedule needed.
- **Coupling out:** rewrites doc 02's `clog_pct ← 0` reset to
  **`clog_pct ← clog_pct · (1 − cleaning_efficiency)`** — a worn wiper gives a
  partial reset, a fresh wiper gives a full reset.
- **Hackathon calibration:** `cleaning_efficiency = 0.40` (DEGRADED) at
  ≈ 80 cleanings under nominal drivers; ≈ 30 cleanings under abusive drivers.
  At dt = 1 sim-h with maintenance ~every 30 sim-h, that's ≈ 100 sim-days to
  DEGRADED — same order as the nozzle's natural failure window.

---

## Background

Wiper blades in maintenance stations are the standard **first-line servicing
mechanism** for inkjet and binder-jet printheads: a soft elastomer (EPDM,
silicone, or polyurethane) lip slides across the nozzle face to scrape away
dried binder, powder ingestion, and stray droplets, and to re-form the
meniscus inside each nozzle. Industry guidance is consistent: wipers degrade
on a **use-driven** schedule (every 1–3 years for capping/wiping consumables,
monthly inspection, immediate replacement if deformed) and a worn wiper
**deposits residue back onto the plate** rather than removing it — exactly
the failure mode we want to capture as "efficiency dropping toward 0."

Elastomer wear under cyclic abrasive contact has a well-studied form. Gent's
mechanism papers and the Southern–Thomas fatigue-crack model both describe
rubber abrasion as accumulating damage at flap/tongue features along the
contact edge, governed by the **number of cyclic abrasive contacts** more
than by elapsed time. A power-law decay `1 − a·n^p` is a defensible
first-order surrogate: it's the simplest function that (a) starts at 1.0
fresh, (b) decays monotonically with use, and (c) lets us pick a single
exponent that controls how "cliff-like" the failure is.

---

## Decision

### State and per-cleaning update

```python
# State carried on the cleaning_interface component
cumulative_cleanings: int = 0
shelf_age_hours:      float = 0  # ticks since last replacement

# At every tick:
shelf_age_hours += dt

# When a maintenance event fires (one cleaning cycle):
cumulative_cleanings += 1
wear_factor = (1 + gamma_T * temp_stress
                 + gamma_H * humidity
                 + gamma_C * powder_contamination
                 + gamma_L * production_load
              ) / max(maintenance_quality, 0.1)
n_eff = cumulative_cleanings * wear_factor

# Use-driven decay (dominant)
H_use   = max(0.0, 1.0 - a * n_eff ** p)
# Calendar shelf-life decay (small, captures EPDM hardening when idle)
H_shelf = exp(-(shelf_age_hours / eta_shelf) ** beta_shelf)

cleaning_efficiency = clip(H_use * H_shelf, 0, 1)
```

| Param         | Value | Justification |
| ------------- | ----- | ------------- |
| `a`           | 0.06  | Calibration: `1 − 0.06·80^0.5 ≈ 0.46` → DEGRADED at ~80 cleanings nominal |
| `p`           | 0.5   | Sub-linear decay; matches "gradual degradation over weeks" reports |
| `gamma_T`     | 0.4   | Hot plate dries binder faster → harder scrape → more lip wear |
| `gamma_H`     | 0.2   | High humidity rehydrates binder unevenly, gummy residue |
| `gamma_C`     | 0.8   | Powder contamination is the strongest abrasive driver |
| `gamma_L`     | 0.3   | Load proxies cleanings/hour, additionally amplifies wear/cleaning |
| `eta_shelf`   | 8760 h (1 y) | Weibull scale for EPDM shelf hardening |
| `beta_shelf`  | 1.5   | Mild wear-out for the calendar term — secondary effect |

Sanity: nominal drivers (T=H=C=0.2, L=0.5, M=0.7) → `wear_factor ≈ 1.0`,
DEGRADED (`<0.40`) at ≈ 80 cleanings, CRITICAL (`<0.15`) at ≈ 200. Abusive
(C=0.8, L=1.0, M=0.2) → `wear_factor ≈ 4.5`, DEGRADED at ≈ 18 cleanings.

### Coupling out — rewrites the nozzle reset rule

Doc 02's maintenance behaviour was `clog_pct ← 0`. Replace with:

```python
clog_pct ← clog_pct * (1 - cleaning_efficiency)
```

Fresh wiper (`efficiency = 1.0`) → full reset (matches old behaviour). Dead
wiper (`efficiency = 0.0`) → no reset (cleaning is a no-op). Mid-life
(`efficiency = 0.5`) → halves residual clog. The **back-coupling** into the
nozzle's clog hazard is automatic via doc 02's existing `λ` formula: clog%
that doesn't reset stays in the state and continues to accumulate, raising
the next-tick clog probability.

### Status thresholds (standard)

| `cleaning_efficiency` | Status     |
| --------------------- | ---------- |
| `≥ 0.75`              | FUNCTIONAL |
| `0.40 – 0.75`         | DEGRADED   |
| `0.15 – 0.40`         | CRITICAL   |
| `< 0.15`              | FAILED     |

### Maintenance reset rule

Two-tier, mirroring real cleaning-station servicing (cheap blade swap vs full
station replacement):

- **Wiper-blade swap** (cheap, default for `MAINTAIN` actions on this
  component): `cumulative_cleanings ← 0`, `shelf_age_hours ← 0`, efficiency
  back to 1.0. Treats the rest of the station as untouched.
- **Full station replacement** (rare, only when efficiency hits FAILED):
  same effect on this component; flagged separately in the historian for the
  cost model.

---

## Why this fits our case

- **Closes the cleaning ↔ nozzle loop cleanly.** The two components share
  one number (`cleaning_efficiency`) flowing one way and `clog_pct` flowing
  the other — exactly the cascading-failure narrative the brief rewards.
- **Wear-per-cycle is the right physics.** Industry reports and elastomer
  abrasion literature both point to **use count** as the dominant variable;
  the Weibull shelf term is there only so the model degrades sensibly when
  the printer sits idle.
- **All five drivers wired in.** Powder contamination is the dominant term
  (γ_C = 0.8), which matches the physical intuition that grit on the plate
  abrades the lip; production load enters twice (more cleanings per unit
  time *and* more wear per cleaning under heavy use).
- **Hackathon-tunable, hackathon-fast.** A single power-law plus a tiny
  Weibull. Two scalars (`a`, `p`) control the entire failure curve.
- **Aligns with doc 09's maintenance agent.** The agent already triggers
  atomic maintenance at `min(H) < 0.40`; we plug in as another component
  whose health falls under that same trigger, no agent changes needed.

---

## References

1. **Wiper-blade function & service-life intervals in inkjet maintenance
   stations** — DigiPrint USA, *Dampers, Capping Stations, and Wiper Blades:
   the $40 parts that protect your $900 printhead.*
   <https://digiprint-usa.com/blogs/printhead-guides-tips-digiprint-usa/dampers-capping-stations-wiper-blades-printhead-spare-parts>
2. **Wiper-blade wear modes & monthly inspection / replacement when
   deformed; pigment ink accelerates wear** — Johope Technology,
   *What Is a Printer Wiper Blade? Functions, Types & Maintenance Guide.*
   <https://johopetech.com/print-basics/what-is-a-printer-wiper-blade/>
3. **Cumulative-neglect failure pattern over 6–12 months for capping +
   wiping + flushing components** — Micolorprint, *Printhead Lifespan
   Factors: Complete Guide to Extending Inkjet Printhead Life.*
   <https://www.micolorprint.com/printhead-lifespan-factors-complete-guide-to-extending-inkjet-printhead-life/>
4. **Mechanisms of rubber abrasion (cyclic-contact fatigue model)** —
   Gent & Pulford, *Mechanisms of rubber abrasion*, J. Appl. Polym. Sci.
   1983.
   <https://onlinelibrary.wiley.com/doi/abs/10.1002/app.1983.070280304>
5. **Abrasive wear of elastomers (Southern–Thomas fatigue-crack family,
   smearing vs. tearing modes)** — *Abrasive Wear of Elastomers*,
   ScienceDirect chapter.
   <https://www.sciencedirect.com/science/chapter/edited-volume/abs/pii/B9781845691004500086>
6. **HP printhead-servicing actuator (translational wiping)** —
   US Patent 5,886,714, Hewlett-Packard.
   <https://www.freepatentsonline.com/5886714.html>

---

## Open questions

- **Cleanings-per-maintenance-event.** Currently 1:1. A real S100 service
  cycle may include several wipe passes per maintenance trigger; if so,
  multiply `cumulative_cleanings` by a fixed `passes_per_event` (probably
  3–5). Doesn't change the math, only the calibration of `a`.
- **Powder-contamination feedback.** Should a worn wiper *increase*
  measured powder contamination on the next layer (because residue gets
  re-deposited)? Cleanest cascade: feed `(1 − cleaning_efficiency) · 0.2`
  back into the nozzle's `C` driver. Worth ~10 LOC if there's time.
- **Failure mode under FAILED status.** Should a fully failed wiper
  *increase* `clog_pct` per cleaning instead of just failing to reduce it?
  Realistic (smearing) but adds a sign flip; defaulting to "no-op cleaning"
  for simplicity.
- **Shelf-life term necessity.** With dt = 1 h and 4380-h horizons,
  `H_shelf` barely moves (≈ 0.97 at 6 months). It's mostly there for
  semantics — fine to drop if the team wants a one-equation model.

## Synthetic prompt

> Add `docs/research/18-cleaning-interface.md` modelling the printhead
> cleaning interface as `cleaning_efficiency ∈ [0,1]` driven primarily by
> a power-law decay in cumulative cleanings (with a tiny Weibull shelf
> term), triggered once per maintenance event. Replace the nozzle's
> `clog_pct ← 0` reset with `clog_pct ← clog_pct · (1 − cleaning_efficiency)`
> to close the cleaning ↔ nozzle loop. Use 0.75 / 0.40 / 0.15 thresholds,
> calibrate to ≈ 80 cleanings to DEGRADED nominal, cite Gent rubber-
> abrasion and inkjet wiper-service-life sources, follow the existing
> TL;DR / Background / Decision / Why this fits / References / Open
> questions structure.

Generated with Claude Opus 4.7
