# Dashboard guide — what each panel shows and how to present it

The Streamlit dashboard at `streamlit_app.py` packs maximum information about a single selected run into **four panels**. Pick the run with the sidebar `run_id` selector. Pick the focus component for panel 3 with the `component (panel 3)` selector (default `heater`). Move the slider above panel 1 to set the *selected tick* — a black dashed cursor that lines up across the heatmap.

Reference run used for the call-outs below: `barcelona-baseline-42-…` — horizon 260 ticks; final state nozzle / cleaning / rail FAILED, heater + sensor degrading.

The four panels answer four questions in order:
1. **What is failing?**
2. **Why is it failing?**
3. **Can we trust the observed data?**
4. **What did the operator (policy) do about it?**

---

## Metadata strip (top of page)

Two compact uppercase lines pulled from `runs` + the `print_outcome` distribution on `drivers`:

```
RUN  {run_id}  ·  SCENARIO  {scenario}  ·  PROFILE  {profile}
SEED {seed}  ·  HORIZON {horizon_ticks}  ·  DT {dt_seconds}s  ·  OK x%  ·  DEGRADED y%  ·  HALTED z%
```

The OK / DEGRADED / HALTED percentages are the operator-visible KPI — what fraction of ticks the printer actually printed cleanly versus produced bad parts versus halted. Drop a number in conversation when introducing the run.

---

## Panel 1 — Driver-coupled component decay

The hero panel. One composed Altair chart, three vertical bands.

**Top — three driver sparklines** (`temperature_stress`, `humidity_contamination`, `operational_load`). Thin black lines, no axes, right-edge percentage label. These are the engine's *inputs*; everything in the heatmap below is the *consequence*.

**Middle — component status heatmap**. One row per component (in canonical order: `blade`, `rail`, `nozzle`, `cleaning`, `heater`, `sensor`), one column per tick. Cell colour is the **status** at that tick:

- light grey → FUNCTIONAL
- medium grey → DEGRADED
- royal blue (`#3A6FE0`) → CRITICAL
- near-black (`#111111`) → FAILED

If the run has more than ~120 ticks, columns are downsampled and each bucket shows the **worst** status in its window (`FAILED > CRITICAL > DEGRADED > FUNCTIONAL`). Tooltip on every cell carries `tick`, `component`, `status`, exact `health_index`, and the three drivers.

**Overlays on the heatmap:**
- Black dashed vertical rule = the selected tick from the slider above the panel.
- Tiny shape glyphs above each row = maintenance events at that tick (▲ FIX, ▼ REPLACE, ◇ TROUBLESHOOT). The full event story is on panel 4 — these are an at-a-glance summary.
- Red dashed rules = environmental events (chaos overlays from the YAML — earthquake, HVAC failure, holiday). Only render when the scenario emits them.

**Talking points (Barcelona-baseline-42):**
- Nozzle row goes near-black almost immediately — humidity + bad powder spread quality cascade fast in the Barcelona profile.
- Cleaning follows nozzle into FAILED ~tick 109; that's the cleaning↔nozzle coupling loop closing.
- Rail flips to CRITICAL at 58 then FAILED — coupling driven, not standalone Weibull.
- Heater + sensor stay grey: the chosen scenario doesn't open the §3.4 sensor-fault gap. Switch to `chaos-stress-test-…` for that story.

---

## Panel 2 — Cascade attribution (left half of middle row)

For each component that crossed CRITICAL or FAILED, one card with:

- **Status transition header** — every status the component reached and the first tick it reached it. Reads top-to-bottom as a one-line failure timeline.
- **Top-3 coupling factors** at the worst-status tick, as a horizontal royal-blue bar chart with numeric labels. Source: `reader.fetch_coupling_factors_at(...)` — the same query the CLI's `inspect --failure-analysis` uses, so the numbers match exactly.
- **Causal chain text** beneath the bars when the queried factors actually contain the keys the chain references. Examples:
  - `humidity ↑ + powder_spread_quality ↓ → nozzle_clog ↑ → NOZZLE FAILED`
  - `nozzle_clog ↑ → cleaning_wear ↑ → cleaning_efficiency ↓ → CLEANING FAILED`
  - `vibration ↑ + blade_loss ↑ → rail_alignment ↑ → RAIL FAILED`

The bars are the source of truth; the chain is a human-readable annotation. If the data doesn't match the template, the chain is omitted — never invented.

The panel is capped at **3 cards** (worst transitions first, FAILED before CRITICAL, ties broken by lowest `health_index`). Any extras roll into an `Other transitions (n)` expander. If the run has zero CRITICAL/FAILED components, the panel says so plainly.

**Talking points:** this is where the simulator looks smarter than a normal dashboard. A traditional health curve says "nozzle failed at t=11"; the cascade card says "nozzle failed at t=11 *because* powder_spread_quality dropped to 0.62 because blade_loss_frac and rail_alignment_error pulled it down." That's the coupling story.

---

## Panel 3 — True vs observed (right half of middle row)

The §3.4 sensor-trust panel. The component is chosen from the sidebar (`component (panel 3)`). Renders for the chosen component:

- **Trust verdict chip** at the top — `SENSOR TRUST: TRUSTED / NOISY / DRIFTING / STUCK / ABSENT / SUSPECT`. Verdict is computed in strict priority order (first match wins): `ABSENT > STUCK > DRIFTING > SUSPECT > NOISY > TRUSTED`. Non-`TRUSTED` chips are royal blue; the alarm level is in the *text*, not extra colours.
- **Two-line chart** — true `health_index` (thin black) vs `observed_health_index` (deeper blue `#0647E8`). When the operator's view diverges from the real state, the gap is the lie the sensor is telling.
- **Sensor-note strip** below the chart — one row, coloured by `sensor_note` (`ok`, `noisy`, `drift`, `stuck`, `absent`, `degraded`). The strip is the *category* of failure the sensor is in at each tick.
- **No-data fallback**: if `observed_health_index` is NULL for the entire component (no sensor at all), the observed line drops out, only the true line renders, and the chip reads `ABSENT` with an explanatory caption.
- Caption ends with the `Note distribution: {…}` dict and a hint to switch to a chaos run if the gap looks small.

**Talking points:** Barcelona-baseline keeps the sensor honest (`{ok: ~85%, noisy: ~15%}`), so the lines overlap. Switch to `chaos-stress-test-…` and pick `sensor` or `heater` to expose the gap — that's where the LLM-as-policy agent (when implemented) would emit `TROUBLESHOOT(sensor) → REPLACE(sensor)` instead of misdiagnosing it as a heater fault.

---

## Panel 4 — Maintenance event timeline (bottom, full width)

Per-component event timeline. Six rows × tick axis. Glyphs:

- ▲ FIX (black)
- ▼ REPLACE (royal blue — the only blue in this panel)
- ◇ TROUBLESHOOT (light grey outline)

Above the timeline, a counts strip summarises totals: `FIX 187 · REPLACE 22 · TROUBLESHOOT 48 · TOTAL 257`. Below the timeline, an `Event log (last 50)` expander hides the raw dataframe for backup questions.

**Talking points:** in Barcelona-baseline the timeline is dense black FIX glyphs late in the run on heater / nozzle / blade / rail — the heuristic policy is in panic-fix mode after the first hard failure. That visual is the pitch for the LLM-as-policy: blue REPLACE markers earlier, sparser overall.

---

## 5-minute demo flow

| Time | Panel | What you say |
| --- | --- | --- |
| 0:00–0:30 | Metadata strip + Panel 1 sparklines | "Six components, three drivers, one operator KPI. The cascading status heatmap is the run at a glance." |
| 0:30–1:30 | Panel 1 heatmap | "Nozzle goes black first — coupled to humidity and bad powder. Cleaning, rail follow. Heater + sensor stay grey in this scenario." |
| 1:30–2:30 | Panel 2 cards | "Every failure has a causal chain — top-3 coupling factors at the failure tick, lifted from the historian, not narrated." |
| 2:30–3:30 | Panel 3 (switch to chaos run if available) | "And the operator only ever sees the *observed* line. When the sensor lies, this gap opens up." |
| 3:30–4:30 | Panel 4 | "Here's the policy reacting — dense FIX glyphs late in the run is the panic mode. The LLM-as-policy version (next milestone) cuts this in half with preventive REPLACE earlier." |
| 4:30–5:00 | Back to Panel 1 | "Same engine, different scenario flips the failure order — Phoenix would put heater + sensor first." |

---

## Switching runs / scenarios

- Sidebar `run_id` dropdown picks any run already in the historian.
- To generate a new run: in another terminal, `cd sim && uv run copilot-sim run <scenario.yaml>` (e.g. `chaos-stress-test.yaml` or `phoenix-aggressive.yaml`), then refresh the page (the cached `open_db` connection auto-picks up new rows).
- To wipe the historian (e.g. after a schema change): delete `sim/data/historian.sqlite*` and rerun.

## Aesthetic choices

- White background, black type. Royal blue (`#3A6FE0`) is reserved for CRITICAL cells, REPLACE markers, the trust-verdict chip when not `TRUSTED`. A slightly deeper blue (`#0647E8`) is reserved for the observed-health line in panel 3.
- Selected-tick rule is **black dashed**, never blue, so the cursor never doubles up as a status indicator.
- Status palette uses one constant (`STATUS_COLOURS` in `streamlit_app.py`) so all panels match.
