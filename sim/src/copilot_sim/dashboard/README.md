# Dashboard guide — what each chart shows and how to present it

The Streamlit dashboard renders six charts from one SQLite historian (`data/historian.sqlite`). Pick the run with the sidebar `run_id` selector. All six charts share the same x-axis (simulated tick = one sim-hour).

Reference run used for the screenshots and call-outs below: `barcelona-baseline-42-…` — horizon 260 ticks, final state heater + nozzle FAILED, rail CRITICAL. Note distribution `{'ok': 224, 'noisy': 36}`.

---

## 1. Component health over time

Six lines, one per component (`blade`, `cleaning`, `heater`, `nozzle`, `rail`, `sensor`). Y axis is the composite **health index** ∈ [0, 1] from `H = H_baseline · H_driver`. Status thresholds: `>0.75` FUNCTIONAL · `>0.40` DEGRADED · `>0.15` CRITICAL · else FAILED.

**What you see**: sawtooth curves. Each downstroke is degradation under the active drivers; each vertical jump back up is the maintenance policy firing `FIX` or `REPLACE`.

**Talking points**:
- `nozzle` (pink) collapses fastest in Barcelona — humidity + powder contamination drives clog hazard up; it lives at the bottom even after FIX.
- `blade` and `rail` show the cleanest sawtooth — they're consumable / rebuildable, so REPLACE puts them back near 1.0.
- `sensor` (green, top) barely moves over 260 ticks — temperature sensors are slow Arrhenius-drift devices, this is the expected shape.
- `heater` (red) decays smoothly without a reset — once drift exceeds the +10 % cliff it stays FAILED until a REPLACE.

---

## 2. Driver streams

The four raw inputs the engine consumes every tick (before any coupling):

- `temperature_stress` — sinusoidal day+season profile (Barcelona climate).
- `humidity_contamination` — Ornstein-Uhlenbeck mean-reverting noise.
- `operational_load` — duty-cycle square wave around 0.6–0.7.
- `maintenance_level` — step function (often near zero between scheduled windows).

**Talking point**: this is the *cause* panel; everything in chart 1 is the *effect*. The temperature sinusoid in particular maps onto the heater's drift slope.

---

## 3. Print outcome distribution

Stacked bars per 10-tick window, counting the per-tick `print_outcome ∈ {OK, QUALITY_DEGRADED, HALTED}` derived at the end of every `Engine.step()`.

**What you see**: early buckets are dominated by QUALITY_DEGRADED + OK; from ~tick 50 onward HALTED takes over as the heater and nozzle hit their cliffs.

**Talking points**:
- Run totals: 50 OK / 124 QUALITY_DEGRADED / 86 HALTED.
- This is the operator-facing signal — the machine literally stops printing once a critical component fails, regardless of what any sensor says.

---

## 4. Maintenance events

Bar chart counting events per tick, coloured by `OperatorEventKind` (`FIX` / `REPLACE` / `TROUBLESHOOT`). Below it, the table shows the last 20 events with `(tick, kind, component_id)`.

**What you see**: solid blue bars at almost every tick from ~5 onward — the heuristic policy is firing `FIX` continuously once health drops below the reactive threshold.

**Talking points**:
- The policy reads only `ObservedPrinterState`, not the true state — so it reacts to what a real operator would see.
- Late-run events (tail of the table) cycle FIX across heater → nozzle → blade → rail every tick: panic mode after the first hard failure.
- If we run the LLM-as-policy A/B, this chart sparser = smarter (preventive REPLACE > reactive FIX spam).

---

## 5. Coupling factors over time

Lines for the named entries in `CouplingContext.factors` — these are the **internal physics** the engine computes each tick from the previous state:

- `blade_loss_frac` — fraction of recoater thickness lost (sawtooths to 0 on REPLACE).
- `cleaning_efficiency` — drops with cumulative cleanings, resets on cleaning REPLACE.
- `heater_drift_frac` — Arrhenius drift, sawtooths down on heater REPLACE.
- `control_temp_error_c` — what the controller *thinks* is the temperature error; corrupted by sensor bias.
- `heater_thermal_stress_…` — the thermal stress the heater self-applies.
- (also: `powder_spread_quality`, `nozzle_clog_pct`, `humidity_contamination_effective`, `temperature_stress_effective`, `sensor_bias_c`.)

**Talking points**:
- This is the **cascade attribution view**: when `nozzle` drops in chart 1, walk the cascade — `nozzle.clog → humidity_contamination_effective → powder_spread_quality → blade.loss_frac × rail.alignment_error`.
- `cleaning_efficiency` resets correlate 1:1 with cleaning REPLACE events in chart 4.
- Caption reminder: *"powder_spread_quality / cleaning_efficiency are damage proxies that drop as upstream components age; nozzle_clog_pct rises with humidity."*

---

## 6. Heater true vs observed (the §3.4 story)

Two lines for the heater only: ground-truth `health_index` (engine internal) vs `observed_health_index` (what the sensor reports). The caption shows how often `sensor_note` was each of `ok / noisy / drift / stuck / absent` over the run.

**What you see in the baseline run**: the lines overlap almost perfectly — `{'ok': 224, 'noisy': 36}`, no drift/stuck. The framework is in place but the sensor stayed honest in this scenario.

**Talking points**:
- This is the §3.4 *Observability* twist: the operator only ever sees the observed line. When the sensor degrades, the gap between the two lines is the lie.
- **For the punchier demo, switch to `chaos-stress-test.yaml` or `phoenix-aggressive.yaml`** — those scenarios push the sensor into `drift` / `stuck` territory and the gap opens up.
- That gap is exactly what the LLM-as-policy agent uses to emit `TROUBLESHOOT(sensor) → REPLACE(sensor)` instead of misdiagnosing it as a heater fault.

---

## Demo flow (5 min)

1. Open with chart 1 — "six components, six failure laws, all coupled."
2. Drop to chart 2 — "these are the four drivers; the temperature sinusoid is what's making the heater bleed."
3. Chart 5 — "and here's the cascade — when the nozzle clogs it's because the powder line upstream is collapsing."
4. Chart 4 + chart 3 — "the policy reacts, but in this run it's reactive FIX spam; you can see the print outcome flipping to HALTED anyway."
5. Chart 6 — "and here's our unique angle — the operator's view is itself a failable signal. Switch scenarios to see the gap."

## Switching runs / scenarios

- Sidebar `run_id` dropdown picks any run already in the historian.
- To generate a new run: in another terminal, `cd sim && .venv/bin/copilot-sim run <scenario.yaml>` (e.g. `chaos-stress-test.yaml` or `phoenix-aggressive.yaml`), then refresh the page.
