# Dashboard guide — what each panel shows and how to present it

The Streamlit dashboard at `streamlit_app.py` packs the most useful technical views about a single run into **seven panels**, grouped into three rows (core demo, "also available", Phase 3 preview). Pick the run with the sidebar `run_id` selector. The sidebar also has a "Run selected scenario" button that kicks the CLI from inside the dashboard, so you can generate fresh runs without leaving the page.

Reference run for the call-outs below: `barcelona-baseline-42-…` — horizon 260 ticks; final state nozzle / cleaning / rail FAILED, heater + sensor degrading. 49 OK / 174 DEGRADED / 37 HALTED ticks. 257 maintenance events.

The dashboard is structured to answer three questions in order:
1. **What is failing, and why?** → Panels 1 + 2
2. **What did the operator (policy) do about it?** → Panel 4
3. **What would the AI co-pilot have said?** → Phase 3 preview row (Panels 7 + 8)

---

## Metadata strip (top of page)

Nine pill chips on a single row, wrapping to two lines on narrow screens:

```
[RUN run_id] [SCENARIO …] [PROFILE …] [SEED …] [HORIZON …] [DT …s]
[● OK x%]  [● DEGRADED y%]  [● HALTED z%]
```

Each pill: light-blue tint, rounded, uppercase blue label + tabular-num black value. The three outcome pills get a small coloured dot — green / amber / red — for at-a-glance status without breaking the sparse blue palette. Source: `runs` table for the metadata; `drivers.print_outcome` value-counts for the percentages.

Drop a number in conversation when you introduce the run. "67% of ticks were degraded prints" sets the scene faster than any chart.

---

## Panel 1 — Component health over time *(Phase 1 / coupled engine)*

One Altair line chart, six lines (one per component), `health_index ∈ [0, 1]` over `tick`. Status thresholds: `>0.75` FUNCTIONAL · `>0.40` DEGRADED · `>0.15` CRITICAL · else FAILED.

Environmental events (named one-offs from the chaos YAML — earthquake, HVAC failure, holiday) overlay as **grey dashed vertical rules** with the event name as a small label. They only appear when the scenario actually emits them.

**Talking points (Barcelona-baseline-42):**
- Nozzle (pink) collapses fastest — humidity + powder contamination drives clog hazard up.
- Heater (red) decays smoothly without a reset; once drift exceeds the +10 % cliff it stays FAILED.
- `sensor` (green, top) barely moves over 260 ticks — slow Arrhenius drift on the temperature sensor is the expected shape.

---

## Panel 2 — Cascade attribution *(Phase 1 / failure explanation, full width)*

For each component that crossed CRITICAL or FAILED, render one card:

- **Status stepper** — coloured pills (one per status the component reached) connected by `→` arrows, with the tick number embedded as `t=N`. CRITICAL is royal blue, FAILED is the deep brand blue with white text.
- **Top-3 coupling factors** at the worst-status tick, as a horizontal blue bar chart with numeric labels. Source: `reader.fetch_coupling_factors_at(...)` — the same query the CLI's `inspect --failure-analysis` uses, so the numbers match exactly.
- **Causal chain text** beneath the bars when the queried factors actually contain the keys the chain references. Examples:
  - `humidity ↑ + powder_spread_quality ↓ → nozzle_clog ↑ → NOZZLE FAILED`
  - `nozzle_clog ↑ → cleaning_wear ↑ → cleaning_efficiency ↓ → CLEANING FAILED`

The bars are the source of truth; the chain is a human-readable annotation. If the data doesn't match the template, the chain is omitted — never invented.

The panel is capped at **3 cards** (worst transitions first, FAILED before CRITICAL, ties broken by lowest `health_index`). Any extras roll into an `Other transitions (n)` expander. If the run has zero CRITICAL/FAILED components, the panel says so plainly.

**Talking points:** this is where the simulator looks smarter than a normal dashboard. A traditional health curve says "nozzle failed at t=11"; the cascade card shows the status stepper and explicitly names the top contributing factors. That's the coupling story made unambiguous.

---

## Panel 4 — Maintenance load by component *(Phase 2 / operator response)*

Six horizontal stacked bars (one per component), segments coloured by `OperatorEventKind`:

- **black** = FIX
- **royal blue** = REPLACE
- **light grey** = TROUBLESHOOT

Bar totals appear at the right end. Above the chart, a counts strip summarises totals: `FIX 187 · REPLACE 22 · TROUBLESHOOT 48 · TOTAL 257`. Below the chart, an `Event log (last 50)` expander hides the raw dataframe for backup questions.

**Talking points:** in Barcelona-baseline the heater and nozzle bars are the longest by far — the heuristic policy is babysitting the components that fail first. That visual is the pitch for the LLM-as-policy: same scenario should produce shorter bars (fewer reactive FIX events) once the LLM agent runs preventive REPLACE earlier.

---

## "Also available" row — extra views to swap in if needed

Two side-by-side panels you can promote into the main demo if they fit the audience better.

### Panel 5 — Driver streams *(Phase 2 / brief inputs)*

Four small black-line sparklines stacked vertically: `temperature_stress`, `humidity_contamination`, `operational_load`, `maintenance_level`. Right-edge value (in saturated blue) shows the latest reading. This is the visible proof for the brief's "all 4 drivers wired" criterion.

### Panel 6 — Status timeline *(Phase 1 / status decay)*

Per-component Gantt: each component is a row, segmented into coloured bars showing how long it stayed in each status. Same data as Panel 1 but a categorical "calendar" view that reads at a glance — easy to spot the moment each row turns blue (CRITICAL) or near-black (FAILED).

---

## "Phase 3 preview" row — what the AI co-pilot would say

Both panels are **rule-based today**, sourced from real historian data, framed as the future co-pilot's UX. The captions say so explicitly so judges aren't misled.

### Panel 7 — Recommendation cards *(Phase 3 / heuristic preview)*

One bordered card per FAILED/CRITICAL component:
- Coloured severity dot + component name + `@ t=N · health X · status STATUS`
- "Why:" line citing the top coupling factor + cascade chain (when the factors match a known template)
- "Suggested next step" outlined badge (`WATCH` / `SCHEDULE FIX` / `REPLACE NOW`) + plain-English recommendation

These are **announcements, not buttons** — the dashboard isn't wired to a maintenance backend. The action element is intentionally an outlined badge (white background, blue border, blue dot) so it doesn't look pressable. When the LLM agent lands in Phase 3, the lookup table (`_PHASE3_RULES`) gets replaced with a generated rationale; the card layout stays the same.

### Panel 8 — Proactive alerts feed *(Phase 3 / autonomy preview)*

Scrollable list of every status crossing the engine produced. Each row: glyph (`◐`/`◑`/`●`) + `TICK N` + component + `→ STATUS` + the dominant coupling factor at that tick. Capped at 360 px tall with overflow scroll so the panel never blows out the layout. This is what an autonomous agent would have raised in real time.

---

## 5-minute demo flow (4 chosen panels, ≥1 per phase)

If you have to pick four panels for the demo with the constraint **at least one per phase**, the recommended set is **2, 4, 5, 7**:

| Time | Panel | What you say |
| --- | --- | --- |
| 0:00–0:30 | Metadata strip | "Same printer, same six components, one selected run. 49 OK ticks out of 260." |
| 0:30–1:30 | **Panel 5 — Driver streams** | "Four engine inputs every tick. Temperature, humidity, load, maintenance — all wired." |
| 1:30–3:00 | **Panel 2 — Cascade attribution** | "Every failure has a chain of causes. Top-3 coupling factors at the failure tick, lifted straight from the historian." |
| 3:00–4:00 | **Panel 4 — Maintenance load** | "Here's the policy reacting — heater and nozzle dominate the load. The LLM agent in Phase 3 should flatten this." |
| 4:00–5:00 | **Panel 7 — Recommendation cards** | "And here's what the co-pilot would say. Today it's a rule-based lookup; in Phase 3 the LLM replaces the lookup with a generated rationale." |

If the audience needs the sensor-trust story, the previous Panel 3 (true vs observed) was removed in this pass — it can be reinstated, since the historian still carries `observed_component_state` rows.

---

## Switching runs / scenarios

- Sidebar `run_id` dropdown picks any run already in the historian.
- "Run selected scenario" button (sidebar) executes `copilot-sim run <yaml>` from inside the dashboard and shows stdout in an expander.
- To regenerate from terminal: `cd sim && uv run copilot-sim run <scenario.yaml>`.
- To wipe the historian after a schema change: `rm sim/data/historian.sqlite*` then rerun.

---

## Aesthetic choices

- White background, black type. Saturated brand blue `#1846F5` (the `hpct.work` accent) is reserved for: REPLACE markers in Panel 4, the recommendation pill in Panel 7, the cascade bars in Panel 2, and the title accent on `HP `**`Co`**`Pilot Twin`. A slightly lighter blue `#5683FF` is used for CRITICAL status cells in Panel 6.
- Greys carry FUNCTIONAL/DEGRADED/TROUBLESHOOT.
- Status palette pinned in one constant (`STATUS_COLOURS` in `streamlit_app.py`) so all panels match.
- Metadata pills get coloured dots only on the three outcome chips (green / amber / red); everywhere else stays sparse blue + black + grey.
