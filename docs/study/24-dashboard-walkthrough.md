# 24 — Dashboard Walkthrough

> Every panel of the Streamlit dashboard explained — what it shows, what data it pulls from, and what every "funny number" actually means. Use this as the reference open in a side window when you demo or defend the dashboard.

> Source: `sim/src/copilot_sim/dashboard/streamlit_app.py`. Launch: `cd sim && uv run streamlit run src/copilot_sim/dashboard/streamlit_app.py`.

---

## Layout (top to bottom)

The dashboard renders **8 panels** for one selected `run_id` (panel 3 was dropped in an upstream rewrite, so the numbering jumps `1 → 2 → 4 → 5 → 6 → 7 → 8`):

```
┌─ Header: "hpct.work · HP CoPilot Twin · Operator badge"
├─ Sidebar: db path · scenario picker · "Run" button · run_id picker
├─ METADATA STRIP (9 pills)
├─ Panel 1  — Component health over time     (line chart)
├─ Panel 2  — Cascade attribution            (cards w/ bar charts)
├─ Panel 4  — Maintenance load by component  (stacked bars)
├─ "Also available" row:  Panel 5 + Panel 6
└─ "Phase 3 preview" row: Panel 7 + Panel 8
```

The four panels above the "Phase 3 preview" line are the ones Phase 1 + Phase 2 of the brief actually demand. Panels 5–8 are bonuses.

The dashboard is a **read-only consumer of the historian**. Every panel is a SQL query against `data/historian.sqlite` (no engine re-runs), so anything you see is grounded in persisted simulation data — that's the brief's *Evidence Citation* requirement satisfied for free.

---

## Header + sidebar

### Header
- "hpct.work" eyebrow + "HP CoPilot Twin" title — branding.
- "Operator" pill with green dot — declares the dashboard as the operator's view, not the engine's internals (per the §3.4 split, the operator never sees `PrinterState`, only `ObservedPrinterState`).

### Sidebar (left rail)
- **historian db path** (text input, default `data/historian.sqlite`) — switch DBs without restarting Streamlit.
- **scenario to run** (dropdown listing `sim/scenarios/*.yaml`) + **Run selected scenario** button — invokes `copilot-sim run <scenario>` via `_run_scenario()` and persists output in session state.
- **run_id** (dropdown listing all `runs.run_id` values found in the historian) — picks which run the rest of the page is about.

---

## Metadata strip — the 9 pills under the title

Each pill is `LABEL value`, sometimes with a coloured dot. Source: `_render_metadata_strip()`.

| Pill | What it shows | Where it comes from |
|---|---|---|
| **Run** | full `run_id` string e.g. `barcelona-18mo-42-20260425T222533` | `runs.run_id` |
| **Scenario** | scenario family (`barcelona`, `phoenix`) | `runs.scenario` |
| **Profile** | profile (`baseline`, `18mo`, `aggressive`, `with-chaos`) | `runs.profile` |
| **Seed** | RNG seed (e.g. `42`) | `runs.seed` |
| **Horizon** | total ticks in the run (e.g. `78` for 18-month, `260` for 5-year) | `runs.horizon_ticks` |
| **dt** | simulated seconds per tick (`604800` = 1 week) | `runs.dt_seconds` |
| **OK** ⏺ | % of ticks where `print_outcome = OK` (green `#3FB37F`) | `drivers.print_outcome` |
| **Degraded** ⏺ | % `QUALITY_DEGRADED` (amber `#E8B341`) | same |
| **Halted** ⏺ | % `HALTED` (red `#D45757`) | same |

> **The OK/Degraded/Halted percentages are the single most important number on the page** for "did this run go well". They sum to 100 % and tell you whether the heuristic policy kept the printer in spec.

Pitch-time interpretation:
- High OK + low Halted → policy kept up with degradation.
- High Degraded → components spent a lot of time in CRITICAL but the policy caught them before FAILED.
- Any Halted > 0 → at least one component reached FAILED at some tick.

---

## Panel 1 — Component health over time

Section header: **PHASE 1 / COUPLED ENGINE — Component health over time**.

### The controls bar (above the chart, right-aligned)

```
[ ← ]   [ 6mo | 1y | 3y | all ]   [ → ]
```

- **`6mo / 1y / 3y / all`** — segmented control picks the time window in weekly ticks. `dt = 1 week`, so 6mo = 26 ticks, 1y = 52, 3y = 156, "all" = full run.
- **`← / →` arrows** — pan by half a window (e.g. ±26 ticks at 1y view). Auto-disable at edges so you can't scroll past the data.
- All three controls use Streamlit's `width="stretch"` parameter so they fill their columns — the layout is geometrically symmetric by construction.
- Default window is `1y` if `horizon_ticks ≥ 52`, else `6mo` if `≥ 26`, else `all`.
- State persists in `st.session_state` via `panel1_window_label` and `panel1_start_tick`.

### The chart

- **Y axis**: `health_index ∈ [0.0, 1.0]` (0 = dead, 1 = new). **Always** fixed scale, never auto-rescales.
- **X axis**: `tick` number, locked to `[start_tick, end_tick - 1]` of the chosen window so panning feels stable instead of jittering.
- **Six lines**, one per component, in canonical registry order (blade, rail, nozzle, cleaning, heater, sensor). Colors come from Altair's default palette (no team override). The legend at the top of the chart is the key.
- **Grey dashed vertical rules**: environmental events from the `environmental_events` historian table — only fire if the scenario has `chaos.enabled: true` or named `events:` in the YAML. Examples: `temp_spike`, `contamination_burst`, `hvac_failure`, `holiday`. Hover a rule to see the event name.
- **Tooltip on hover**: `component_id`, `tick`, `health` (3 decimals), `status`.
- **Caption below the chart**: `showing ticks X–Y of Z total` so you always know where you are.

### The "funny numbers" you'll see in the lines

| What you see | What it means |
|---|---|
| Sawtooth peaks reach **~1.0** | Component just got `REPLACE`'d (full reset to `initial_state()`, `age_ticks` zero, `health_index = 1.0`). |
| Sawtooth lows reach **~0.20** | The policy's `_UNHEALTHY_REPLACE = 0.20` threshold (`policy/heuristic.py:37`). When `observed_health < 0.20`, the policy fires REPLACE. |
| Smaller upward bumps (not all the way to 1.0) | `FIX` events — partial recovery (e.g. heater FIX halves drift, nozzle FIX clears 70 % of clog). |
| Slow downward drift on heater (dark green) without sawtooth | The Weibull baseline `exp(-tick/38)` decay — calendar aging at β=1.0, η=38 weeks. The line is mostly being driven by *aging*, not *driver damage*. |
| Sensor (light green) staying flat near 1.0 in Barcelona | Sensor's Arrhenius AF is small at room temperature; bias drift is realistic for a PT100 RTD. The §3.4 story only fires under hot conditions (Phoenix scenario). |

---

## Panel 2 — Cascade attribution

Section header: **PHASE 1 / FAILURE EXPLANATION — Cascade attribution**.

One **card per component that ever crossed CRITICAL or FAILED**, sorted FAILED-first then by lowest health. Top 3 cards visible; the rest behind an `Other transitions (N)` expander.

Each card has three pieces:

### a) Status stepper (pills connected by `→`)

```
FUNCTIONAL t=0  →  DEGRADED t=11  →  CRITICAL t=40  →  FAILED t=49
```

The tick on each pill is the **first tick** that status was observed (computed by `reader.fetch_status_transitions`, which scans the `component_state` table for status changes per component). Pill colours come from the `STATUS_COLOURS` constant:

| Status | Hex | Meaning |
|---|---|---|
| FUNCTIONAL | `#E8E8E8` (light grey) | Within normal envelope |
| DEGRADED | `#9E9E9E` (mid grey) | Watch; schedule maintenance window |
| CRITICAL | `#5683FF` (light blue) | Act now; remaining useful life days, not weeks |
| FAILED | `#1846F5` (HP brand electric blue) | Replacement required before next print |

These thresholds are set in `engine/aging.py`: `HEALTH_FUNCTIONAL = 0.75`, `HEALTH_DEGRADED = 0.40`, `HEALTH_CRITICAL = 0.15`, `< 0.15 = FAILED`.

### b) Top-3 coupling factors at the worst tick

Horizontal bar chart of the **3 coupling factors with largest absolute value** at `worst_tick`. Source: `drivers.coupling_factors_json` — every tick's full 10-factor dict is persisted, so failure analysis runs as a pure SQL query, no engine re-run.

- **Bar width** = `|factor value|` (always in [0, 1])
- **Number label** at the bar's right edge = signed value to 3 decimals
- **Bar colour** = `ACCENT_BLUE = #1846F5`

The 10 named factors that can appear here (full set explained in [`03-coupling-and-cascades.md`](03-coupling-and-cascades.md)):
- `powder_spread_quality`, `blade_loss_frac`, `rail_alignment_error`
- `heater_drift_frac`, `heater_thermal_stress_bonus`
- `sensor_bias_c`, `sensor_noise_sigma_c`, `control_temp_error_c`
- `cleaning_efficiency`, `nozzle_clog_pct`

### c) Cascade chain text (when factor names match a template)

If at least one of the top-3 factor names matches a registered template in `CASCADE_CHAINS`, the card prints a human-readable arrow chain. Example templates from `streamlit_app.py:67`:

| Component | Required factor keys | Chain text appended with status |
|---|---|---|
| heater | `sensor_bias_c, control_temp_error_c, heater_drift_frac` | `sensor_bias ↑ → control_temp_error ↑ → heater_drift ↑ → HEATER` |
| nozzle | `humidity_contamination_effective, powder_spread_quality, nozzle_clog_pct` | `humidity ↑ + powder_spread_quality ↓ → nozzle_clog ↑ → NOZZLE` |
| blade | `rail_alignment_error, blade_loss_frac` | `rail_alignment ↑ → blade.k_eff ↑ → blade_loss ↑ → BLADE` |
| rail | `blade_loss_frac, rail_alignment_error` | `vibration ↑ + blade_loss ↑ → rail_alignment ↑ → RAIL` |
| cleaning | `nozzle_clog_pct, cleaning_efficiency` | `nozzle_clog ↑ → cleaning_wear ↑ → cleaning_efficiency ↓ → CLEANING` |
| sensor | `temperature_stress_effective, heater_drift_frac, sensor_bias_c` | `temperature_stress ↑ + heater_drift ↑ → sensor_bias ↑ → SENSOR` |

If the top-3 doesn't match any template, the chain text is omitted. The chain is the *story* the dashboard tells about *why* a component failed — exactly what the brief's "every failure traceable to root input drivers" requirement asks for.

---

## Panel 4 — Maintenance load by component

Section header: **PHASE 2 / OPERATOR RESPONSE — Maintenance load by component**.

### Top-line summary

```
FIX 47  ·  REPLACE 28  ·  TROUBLESHOOT 0  ·  TOTAL 75
```

Counts come from the `events` historian table grouped by `kind`.

### Stacked horizontal bar chart

- **Y axis**: `component_id` (canonical order: blade, rail, nozzle, cleaning, heater, sensor)
- **X axis**: count of events, stacked by event kind
- **Bar colours** by `OperatorEventKind`:

| Kind | Hex | Meaning |
|---|---|---|
| FIX | `#111111` (black) | Partial recovery — component-specific, see [`21-policy-and-maintenance.md`](21-policy-and-maintenance.md) reset matrix |
| REPLACE | `#1846F5` (HP blue) | Full reset to `initial_state()` |
| TROUBLESHOOT | `#9E9E9E` (grey) | No state change; only writes an event row (only fires when `observed_status = UNKNOWN`) |

Total count labelled at the right end of each component's bar.

### Event log expander

Below the chart, an expander `Event log (last 50 of N)` shows raw event rows from the `events` table (sorted by tick descending).

> **Why TROUBLESHOOT is usually 0**: the policy only emits TROUBLESHOOT when `observed_status = UNKNOWN`, which requires the temperature sensor to actually fail. That only happens in hot scenarios like phoenix-18mo. In Barcelona conditions the sensor stays trustworthy and the policy never goes blind, so the count stays at 0.

---

## Panel 5 — Driver streams (sparklines)

Section header: **PHASE 2 / BRIEF INPUTS — Driver streams**.

Four mini line charts vertically stacked, one per brief-mandated input:

| Driver | What it represents | Generator that produces it (`drivers_src/generators.py`) |
|---|---|---|
| **Temperature stress** | ambient °C deviation from optimal, normalized to [0,1] | `SinusoidalSeasonalTemp` (annual cosine + weekly wobble + AR(1) noise) |
| **Humidity contamination** | air moisture + powder purity [0,1] | `OUHumidity` (Ornstein-Uhlenbeck mean-reverting around `mean`) |
| **Operational load** | print hours / cycle intensity [0,1] | `SmoothSyntheticOperationalLoad` (OU + idle/overload weeks) or `MonotonicDutyLoad` (linear drift + 3-week wobble) |
| **Maintenance level** | how well the operator cares for the machine [0,1] | `StepMaintenance` (piecewise constant from YAML schedule) |

Each sparkline shows:
- **Black line** of the value over all ticks (entire run, no windowing).
- **Blue label at the right edge** = latest value, formatted as a percent (e.g. `30%` for `temperature_stress = 0.30`).
- No axes — these are pure sparklines, optimised for reading the latest value at a glance.

Caption: *"Four engine inputs every tick. Right-edge value is the latest reading; all four are wired into the coupled engine on every step."*

---

## Panel 6 — Status timeline (Gantt)

Section header: **PHASE 1 / STATUS DECAY — Status timeline**.

Same data as panel 1's line chart, **rendered as continuous status periods** instead of a continuous health line. Built by `_status_segments()` which collapses per-tick rows into `(start_tick, end_tick, status)` segments — one row per contiguous run of the same status.

- **Y axis**: component_id (canonical order)
- **X axis**: tick range
- Each coloured bar is a contiguous run of the same status; bars are separated by white strokes for clarity.
- **Colour coding**: identical to panel 2 pills (FUNCTIONAL `#E8E8E8` → DEGRADED `#9E9E9E` → CRITICAL `#5683FF` → FAILED `#1846F5`).
- **Tooltip**: `component_id`, `status`, `from` tick, `to` tick.

Caption: *"Same data as the line chart above, painted as continuous status periods. Look for the moment each row turns blue — that's a CRITICAL crossing."*

This panel is the easiest way to see which component is **alarming most often** — visually scan for blue stripes.

---

## Panel 7 — Recommendation cards (Phase 3 / Intelligence preview)

Section header: **PHASE 3 / HEURISTIC PREVIEW — Recommendation cards**.

One card per CRITICAL/FAILED component (up to 6, no overflow). Each card has:

- **Status dot** coloured by severity (`#E8B341 / #5683FF / #1846F5`)
- **Header line**: `BLADE @ t=49 · health 0.18 · status FAILED`
- **"Why" line**: top driver factor with signed value, plus the cascade chain text from panel 2 if available
- **"Suggested next step" pill**: maps status → recommended action via `_PHASE3_RULES`:

| Status | Pill label | Recommendation text |
|---|---|---|
| DEGRADED | `WATCH` | "Watch closely" |
| CRITICAL | `SCHEDULE FIX` | "Schedule a FIX in the next maintenance window" |
| FAILED | `REPLACE NOW` | "Replace immediately — print outcomes are degrading" |

This panel is a **rule-based stand-in** for what an LLM-as-policy agent would generate. The team's pitch is: "in Phase 3, replace this lookup table with a generated rationale." Caption above the panel says exactly this:

> "Read-only insight cards — rule-based today (status → suggested action lookup); the LLM agent in Phase 3 will replace the rule with a generated rationale."

---

## Panel 8 — Proactive alerts feed (Phase 3 / Autonomy preview)

Section header: **PHASE 3 / AUTONOMY PREVIEW — Proactive alerts feed**.

A scrollable feed (max-height 360 px) of every status transition that ever fired during the run, sorted by tick.

Each row:

```
●   TICK 49    BLADE → FAILED    · top driver  blade_loss_frac = 0.803
```

**Glyph** (left edge) by status:

| Status | Glyph | Dot colour |
|---|---|---|
| FUNCTIONAL | `○` | `#9E9E9E` |
| DEGRADED | `◐` | `#E8B341` |
| CRITICAL | `◑` | `#5683FF` |
| FAILED | `●` | `#1846F5` |

(FUNCTIONAL transitions are filtered out — every component starts there, so they're not interesting alerts.)

The "top driver" code chip is the single coupling factor with largest absolute value at the transition tick — pulled from `drivers.coupling_factors_json`.

Caption: *"N alerts. Each row is what the proactive agent would have raised the moment a component crossed a status threshold."*

---

## All the magic constants in one place

| Constant | Value | Where used |
|---|---|---|
| `STATUS_COLOURS["FUNCTIONAL"]` | `#E8E8E8` light grey | panel 2 pills, panel 6 segments, panel 8 dots |
| `STATUS_COLOURS["DEGRADED"]` | `#9E9E9E` mid grey | same |
| `STATUS_COLOURS["CRITICAL"]` | `#5683FF` light blue | same |
| `STATUS_COLOURS["FAILED"]` | `#1846F5` HP brand electric blue | same |
| `EVENT_COLOURS["FIX"]` | `#111111` black | panel 4 bars |
| `EVENT_COLOURS["REPLACE"]` | `#1846F5` HP blue | panel 4 bars |
| `EVENT_COLOURS["TROUBLESHOOT"]` | `#9E9E9E` grey | panel 4 bars |
| `EVENT_SHAPES` (`triangle-up`, `triangle-down`, `diamond`) | — | defined but unused in current panels (held for future timeline panel) |
| `ACCENT_BLUE` | `#1846F5` | brand colour — bars in panel 2, label in panel 5, recommend pill in panel 7 |
| `RULE_GREY` | `#5A5A5A` | env-event dashed rules in panel 1 |
| metadata OK dot | `#3FB37F` (green) | top strip |
| metadata Degraded dot | `#E8B341` (amber) | top strip |
| metadata Halted dot | `#D45757` (red) | top strip |
| `_QUALITY_DEGRADED_HEALTH` (in `engine/assembly.py:25`) | `0.40` | print outcome boundary — any component below this triggers QUALITY_DEGRADED |
| `HEALTH_FUNCTIONAL` (in `engine/aging.py`) | `0.75` | status threshold |
| `HEALTH_DEGRADED` | `0.40` | status threshold (was 0.45 before this hackathon's fix) |
| `HEALTH_CRITICAL` | `0.15` | status threshold (was 0.20 before this hackathon's fix) |
| `_UNHEALTHY_REPLACE` (in `policy/heuristic.py`) | `0.20` | policy threshold for emitting REPLACE |
| `_UNHEALTHY_FIX` | `0.45` | policy threshold for emitting FIX |
| `_PREVENTIVE_TICK_GAP` | `4` weeks | monthly preventive FIX cadence |
| Window options in panel 1 | 26 / 52 / 156 ticks | 6mo / 1y / 3y |

### The 0.20 vs 0.15 gap — why nothing actually fails on the chart

The most likely "funny number" question:

> *"Why does the chart never show a line hitting 0?"*

Two thresholds are 5 percentage points apart on purpose:
- **Engine**: `HEALTH_CRITICAL = 0.15` is when `status_from_health` flips to FAILED.
- **Policy**: `_UNHEALTHY_REPLACE = 0.20` is when the heuristic fires REPLACE.

So the policy replaces components **just before** their status would flip to FAILED. The line's sawtooth low is at ~0.20, not at 0. **That's the heuristic policy doing its job.** If you want to *see* lines hit 0, run a scenario with `policy.kind: none` (which doesn't exist as a YAML option today; you'd need a no-op policy) — or wait for chaos to outpace the policy.

---

## How to read the dashboard during a 90-second pitch

1. **Top strip first** — quote the OK / Degraded / Halted % — that's your "did the policy work" headline.
2. **Panel 1** — point at the sawtooth on nozzle (red, fastest), say *"policy is firing REPLACE every ~10 ticks because Coffin-Manson + Poisson clog hits the 0.20 threshold fast"*.
3. **Panel 2** — pick the worst card, walk down its top-3 coupling factors, read the cascade chain text aloud. That's literally the brief's *"every failure event traceable to its root input drivers"* requirement satisfied in one card.
4. **Panel 4** — quote the FIX vs REPLACE split per component. *"Blade only ever gets REPLACE because it's a consumable. Heater gets FIX more often than REPLACE because recalibration recovers drift partially."*
5. (If asked about the §3.4 sensor story) **Panel 8** — scroll to find a `SENSOR → DEGRADED` or `→ FAILED` row. Show its top driver = `sensor_bias_c`. That's the operator getting fooled by a drifting sensor in real time.

---

## What the dashboard does NOT show (yet)

| Thing | Why it's not there | Where it would land |
|---|---|---|
| True vs observed health | Panel 3 was dropped in the upstream rewrite. The §3.4 split is now visible only via panel 8's transitions and panel 2's `sensor_bias_c` factor. | Future panel 3 reinstatement |
| RUL forecasts | Not implemented; specified in the improvement roadmap. | New panel + new historian table per `23-improvement-roadmap.md` §B3.3 |
| Live LLM rationale text | Phase 3 deferred. | Replace panel 7's rule-table with generated text |
| AI surrogate parity chart | Surrogate not trained. | Future panel showing two overlapping heater drift lines |
| Voice / hands-free interaction | Phase 3 deferred. | n/a in this dashboard |

---

## Cross-references

- The historian schema feeding every panel: [`20-stage2-clock-historian.md`](20-stage2-clock-historian.md) §The historian schema.
- The 10 coupling factors that panel 2 ranks: [`03-coupling-and-cascades.md`](03-coupling-and-cascades.md) §The 10 named factors.
- Policy decisions that produce the events panel 4 visualises: [`21-policy-and-maintenance.md`](21-policy-and-maintenance.md).
- Status thresholds the colours encode: [`01-data-contract.md`](01-data-contract.md) §`OperationalStatus` and the four-step ladder.
- §3.4 story panel 8 is set up to tell: [`components/15-sensor.md`](components/15-sensor.md).
