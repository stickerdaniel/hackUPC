<div align="center">
  <h1>hackUPC — When AI meets reality</h1>

  <p>
    A deterministic, coupled digital twin of the <strong>HP Metal Jet S100</strong> — six components across three subsystems, sensors that fail too, and an AI maintenance agent that learns to tell sensor faults from component faults. Live weather, a stochastic chaos layer, and an ML surrogate for the heater are wired in as bonus levers.
  </p>

  <p>
    <a href="https://www.python.org/"><img alt="Python ≥3.12" src="https://img.shields.io/badge/python-%E2%89%A53.12-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=000000"></a>
    <img alt="Scope: Phase 1 + Phase 2" src="https://img.shields.io/badge/scope-Phase_1_%2B_Phase_2-000000?style=for-the-badge">
    <img alt="Status: engine landing" src="https://img.shields.io/badge/status-engine_landing-7C3AED?style=for-the-badge">
    <img alt="HackUPC 2026" src="https://img.shields.io/badge/HackUPC-2026-FF4F00?style=for-the-badge">
  </p>

  <p>
    <a href="#what-we-are-building"><strong>Architecture</strong></a> ·
    <a href="#research-synthesis-phase-1--phase-2"><strong>Research</strong></a> ·
    <a href="#the-killer-demo-sim-only-5-min"><strong>Demo</strong></a> ·
    <a href="#pre-build-research-checklist"><strong>Checklist</strong></a> ·
    <a href="#next-steps-build-order"><strong>Build order</strong></a>
  </p>
</div>

Full briefing: [`TRACK-CONTEXT.md`](./TRACK-CONTEXT.md). Source docs: [`docs/briefing/`](./docs/briefing/). Decision docs: [`docs/research/`](./docs/research/). Code: [`sim/`](./sim/).

> **Build scope: Phase 1 + Phase 2 only.** Phase 3 (chatbot, voice, frontend) is **deferred**. Research docs 10–13 are preserved for future work. Visualisation uses Python-native tools (Streamlit + matplotlib).

---

## Status

**Research locked. Engine types in code. Components landing.** The coupled-engine type layer — `Drivers`, `CouplingContext`, `PrinterState`, `ObservedPrinterState`, `MaintenanceAction`, `OperatorEvent` — lives in [`sim/src/copilot_sim/domain/`](./sim/src/copilot_sim/domain/) as frozen+slots dataclasses. Per-component `step()` functions are next.

---

## What we are building

A coupled digital twin where **every failure tells a story** — and where the operator's perception of the machine is itself a failable signal, not ground truth.

```
                ┌──────────────────────┐
input drivers ─▶│  Phase 1 — Logic     │──▶ next PrinterState (TRUE)
(temp, humidity,│  Engine.step()       │    + ObservedPrinterState
 load, maint.)  │  builds CouplingCtx, │      via per-component
 + live weather │  updates 6 components│      sensor models (§3.4)
 + prev state   │  from same prev      │
                │  snapshot, double-   │
                │  buffered            │
                └──────────────────────┘
                          ▲ │
                          │ │ deterministic, seeded, monotone
                          │ ▼
                ┌──────────────────────┐
                │  Phase 2 — Clock +   │  ──▶  Historian (SQLite WAL)
                │  Driver Generator +  │       runs · drivers ·
                │  Chaos Layer +       │       component_state · metrics ·
                │  Operator Loop       │       observed_component_state ·
                │                      │       observed_metrics · events
                └──────────────────────┘
                          ▲ │
                 modifies │ │ reads ObservedPrinterState (NOT true!)
                          │ ▼
                ┌──────────────────────┐
                │  AI Maintenance Agent│  emits TROUBLESHOOT / FIX / REPLACE
                │  (heuristic primary, │  per (component, action_kind)
                │   LLM-as-policy A/B) │  and writes rationale to events
                └──────────────────────┘
                            │
                            ▼
                ┌──────────────────────┐
                │  Streamlit Dashboard │  ──▶  judges + operators
                │  Time-series viz +   │       Phase 2 deliverable.
                │  true-vs-observed    │       Shows the §3.4 split
                │  toggle + scenarios  │       live.
                └──────────────────────┘
```

**Strategic bet:** stack every Phase 1 + Phase 2 bonus pillar, and lean into the §3.4 sensor-fault twist the organisers opened up.

| Phase 1 evaluation | Phase 2 evaluation |
| :--- | :--- |
| Rigor — six textbook laws, all parameters cited | Time moves — `dt = 1h` × 4380 ticks, 6 sim-months |
| Systemic Interaction — coupled engine, 3 two-way loops + 2 cross-subsystem cascades, all 4 drivers wired | Systemic Integration — Phase 1 called every tick, both true & observed states persisted |
| **Complexity & Innovation (bonus)** — coupling matrix + AI surrogate + §3.4 sensor model | **Complexity & Innovation (bonus)** — chaos + 3-action maintenance agent + sensor-fault-vs-component-fault story |
| **Realism & Fidelity (bonus)** — physically motivated knees + thresholds, observed != true | **Realism & Fidelity (bonus)** — live weather driver, stochastic shocks, `print_outcome ∈ {OK, QUALITY_DEGRADED, HALTED}` |

Bonus pillars in scope: **Cascading Failures · Stochastic Realism · Maintenance as Input · AI-Powered Degradation · Live Environmental Data · What-If Scenarios · Chaos Engineering · AI Maintenance Agent · Observability (§3.4)**. Nine levers; the §3.4 sensor-fault story is uniquely ours.

---

## Research synthesis (Phase 1 + Phase 2)

Each section below summarises a decision doc. Click into [`docs/research/`](./docs/research/) for parameter values, math, references, and open questions.

<details>
<summary><strong>Phase 1 — six components, six textbook formulas, one coupled engine</strong></summary>

We model **two components per subsystem** (six total) — each pair chosen because it forms an explainable feedback loop. Each component has its own driver-specific failure law layered under a shared Weibull aging baseline ([`04`](./docs/research/04-aging-baselines-and-normalization.md)).

| Subsystem | Component | Math | State metric | FAILED at | Coupling output |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Recoating | **Recoater Blade** ([`01`](./docs/research/01-recoater-blade-archard.md)) | Archard wear `Δh = k_eff·P·s_eff·dt/H` | thickness (mm) | 50 % loss | `blade.loss_frac ∈ [0,1]` |
| Recoating | **Linear Guide / Rail** ([`17`](./docs/research/17-linear-rail.md)) | Weibull β=2.0 / η=220 d + driver damage | `alignment_error_um ∈ [0,50]` | 50 µm (raceway pitting permanent) | `rail.alignment_error ∈ [0,1]` |
| Printhead | **Nozzle Plate** ([`02`](./docs/research/02-nozzle-plate-coffin-manson.md)) | Coffin-Manson + Miner damage **and** Poisson clog hazard | composite `(1−clog%)·(1−D)` | `H ≤ 0.20` or `clog ≥ 95 %` or `D ≥ 1` | `nozzle.clog_pct`, `nozzle.fatigue_damage` |
| Printhead | **Cleaning Interface** ([`18`](./docs/research/18-cleaning-interface.md)) | Power-law decay in cumulative cleanings + Weibull shelf-life | `cleaning_efficiency ∈ [0,1]` | < 0.15 | `cleaning.efficiency` (modulates nozzle clog reset) |
| Thermal | **Heating Elements** ([`03`](./docs/research/03-heating-elements-arrhenius.md)) | Arrhenius AF + self-heating feedback | resistance drift (%) | +10 % drift | `heater.drift_frac ∈ [0, 0.1+]` |
| Thermal | **Temperature Sensor** ([`19`](./docs/research/19-temperature-sensor.md)) | Arrhenius bias drift + sub-linear noise growth | composite of `bias_C` + `noise_sigma_C` | `\|bias_C\| > 5 °C` (hard) | `sensor.bias_c` (signed), `sensor.noise_sigma_c` |

**Coupled engine, not independent curves** ([`05`](./docs/research/05-cascading-and-ai-degradation.md)). Each `Engine.step()` reads the immutable `t-1` `PrinterState`, builds **one `CouplingContext`** (4 effective drivers + a named `factors` dict), updates **all six components from the same snapshot**, and emits `t`. Double-buffered — update order cannot affect results.

**Three two-way loops + two cross-subsystem cascades:**

- **Rail ↔ Blade**: `rail.alignment_error → blade.k_eff *= (1 + 0.5 · alignment)`; reverse, `blade.loss_frac → rail accumulator += 0.05 µm/h`.
- **Cleaning ↔ Nozzle**: `cleaning.efficiency` modulates the nozzle clog reset on maintenance (`clog_pct ← clog_pct · (1 − η)`); reverse, `nozzle.clog_pct → cleaning.wear_factor += 0.4 · clog_pct/100`.
- **Sensor ↔ Heater**: `sensor.bias` corrupts the temperature the heater "defends" (controller commands wrong setpoint → Arrhenius accelerates); reverse, hotter heater → faster sensor element aging (`dbias/dt *= 1 + 0.5 · drift_frac`).
- **Powder cascade (subsystem A → B)**: `Q_powder = (1 − blade.loss_frac) · (1 − rail.alignment_error)` → `humidity_contamination_effective += (1 − Q_powder)` → nozzle clog hazard ↑.
- **Thermal cascade (subsystem C → everything)**: `temperature_stress_effective += 0.3 · heater.drift_frac` → all components feel hotter.

**Composition** ([`04`](./docs/research/04-aging-baselines-and-normalization.md)): `H_total = H_baseline(t) · H_driver(damage)`, both `[0,1]`. Multiplicative composition lets the dashboard decompose any health drop into "baseline aging is 0.78, driver damage is 0.79", and matches series-reliability theory.

**Status thresholds** (single shared mapping): `> 0.75` FUNCTIONAL · `> 0.40` DEGRADED · `> 0.15` CRITICAL · else FAILED. Sensor adds a hard fail at `|bias_C| > 5 °C` regardless of HI.

**Two bonus levers** ([`05`](./docs/research/05-cascading-and-ai-degradation.md)) for Complexity & Innovation:

- **Coupling matrix** — already described above. Subsumes the previous one-way cascade; old "blade → nozzle.C @ α=0.5" is now a special case of the powder pipeline (row 11 of the matrix).
- **AI surrogate**: the heater's analytic Arrhenius function gets replaced by a sklearn `MLPRegressor (32,32,32) tanh` trained on 20k Latin-Hypercube samples. Acceptance gate MAE ≤ 2 %; CLI dispatch via `--heater-model={analytic,nn}`. Deck slide: "two lines that overlap perfectly".

</details>

<details>
<summary><strong>§3.4 Observability split — sensors lie too</strong></summary>

The organisers confirmed (`TRACK-CONTEXT.md §3.4`) that **sensors are optional per component, sensors decay and fail too, and print outcome is a first-class observable signal**. We split **true state** (engine ground truth) from **observed state** (what the operator, policy, and co-pilot see) — encoded in the type system:

- `domain.state.PrinterState` and `ComponentState` carry the **true** values, used internally only.
- `domain.state.ObservedPrinterState` and `ObservedComponentState` carry the **observed** view: per-metric `observed_metrics: float | None` (None means sensor absent or stuck-at-None), per-metric `sensor_health: float | None`, a `sensor_note ∈ {ok, noisy, drift, stuck, absent}`, and `observed_status` that may be `UNKNOWN`.
- `domain.enums.PrintOutcome ∈ {OK, QUALITY_DEGRADED, HALTED}` is a top-level field on `PrinterState`.
- `domain.events.OperatorEventKind ∈ {TROUBLESHOOT, FIX, REPLACE}` is the action vocabulary the maintenance policy uses.

Doc 19 is the **reference per-component sensor model** that every other sensored component reuses: `(true_value, sensor_state) → (observed_value, sensor_note)` plus a Poisson dropout for stuck windows and a permanent `absent` after catastrophic bias. The `factors["sensor_bias_c"]` in `CouplingContext` is what feeds back into the heater controller — same loop, but now visible to the operator only as a `sensor_note: drift` on the temperature sensor's observed view.

**Why this matters for the demo**: it lets us tell a sensor-fault-vs-component-fault story that the brief explicitly rewards under Reasoning Depth and Proactive Intelligence. The LLM-as-policy maintenance agent (doc 09) reads only `ObservedPrinterState`, so when the heater appears to drift but the temperature sensor's `sensor_note = "drift"`, the agent emits `TROUBLESHOOT(sensor)` followed by `REPLACE(sensor)` — and stores the rationale in the events table.

</details>

<details>
<summary><strong>Phase 2 — driving it forward in time</strong></summary>

Each tick: the loop generates four drivers, calls the Phase 1 engine, and writes to SQLite. Driver generators ([`06`](./docs/research/06-driver-profiles-and-time.md)) are the simplest defensible choice per signal — sinusoidal day+season for Temperature, Ornstein-Uhlenbeck (Euler-Maruyama) for Humidity, monotonic + duty-cycle for Operational Load, step function for Maintenance Level — all sharing one seeded `numpy.random.default_rng(seed)` for bit-exact reproducibility (the brief's determinism contract).

**Time step**: `dt = 1` simulated hour, **4380 ticks for 6 sim-months**. The slowest failure modes evolve over hundreds-to-thousands of hours; 4380 SQLite inserts is sub-second; demo fast-forwards to `dt = 6h` (~730 ticks) for a 5-second full lifecycle.

**Live weather as a driver** ([`07`](./docs/research/07-weather-api.md)): **Open-Meteo Archive API**. No key, 10k calls/day free, **one GET returns 6 months of hourly `temperature_2m + relative_humidity_2m`**. OpenWeather's One Call 3.0 needs ~4380 requests and a credit card on file — disqualifying for a 36-hour build. Both Barcelona (41.39, 2.16) and Phoenix (33.45, -112.07) JSONs are cached in-repo so the demo never depends on the network. Weather only patches `T_stress` and `Humidity`; Operational Load and Maintenance stay scenario-controlled, which keeps Barcelona-vs-Phoenix a clean A/B (only 2 of 4 drivers change).

**Historian schema** ([`08`](./docs/research/08-historian-schema.md)): SQLite WAL, file at `data/historian.sqlite`. Long-form normalised, with both true and observed views per the §3.4 split:

```
runs                       ── one row per simulation run
drivers                    ── one row per (run, ts) — 4 raw drivers + print_outcome + coupling_factors_json
component_state            ── one row per (run, ts, component) — TRUE health + status + age_ticks
metrics                    ── one row per (run, ts, component, metric_name) — TRUE physical values
observed_component_state   ── §3.4 mirror — observed health/status/sensor_note (status may be UNKNOWN)
observed_metrics           ── §3.4 mirror — observed_value (NULL when sensor absent) + sensor_health
events                     ── operator actions (TROUBLESHOOT/FIX/REPLACE), chaos injections, status transitions
```

All time-series tables are `WITHOUT ROWID`. PKs cover `(run_id, ts)` lookups natively. **Volume (6 components, both layers)**: ~190k rows per run, well under 10 MB SQLite — checks into git as a fallback for ~5 demo runs. **`run_id` format** locked: `{scenario}-{profile}-{YYYYMMDD}-{seq}` (e.g. `barcelona-baseline-20260425-1`). The `coupling_factors_json` column on `drivers` persists every named factor from `CouplingContext` so the dashboard can attribute upstream causes ("nozzle clogged faster because `powder_spread_quality = 0.83` at this tick") without re-running the engine.

**Stochastic mode** (Phase 2 bonus pattern C, [`06`](./docs/research/06-driver-profiles-and-time.md)): a chaos layer overlays the deterministic profile when `config.chaos = true` — Poisson temp spikes (λ=2/month, ΔT~N(8,2) °C, exp decay), contamination bursts (λ=3/month, OU absorbs), Bernoulli skipped maintenance (p=0.1). Calibrated so ~1 in 3 seeds hits CRITICAL inside the 6-month horizon.

**AI Maintenance Agent** (Phase 2 bonus, [`09`](./docs/research/09-maintenance-agent.md)). Action vocabulary is `OperatorEventKind ∈ {TROUBLESHOOT, FIX, REPLACE}` — three kinds, not binary. Primary is a **three-rule heuristic** reading only `ObservedPrinterState`: `(1)` any component `UNKNOWN` → `TROUBLESHOOT(component)` (never act blind on a missing sensor); `(2)` reactive `FIX` / `REPLACE` on observed health crossings; `(3)` scheduled preventive `FIX` on the longest-unmaintained component. Stretch is **LLM-as-policy** — same signature, recognises sensor-fault-vs-component-fault from `sensor_note`, emits `TROUBLESHOOT(sensor)` → `REPLACE(sensor)` with a stored rationale. RL is *specified* (full Gymnasium env on standby) but not implemented.

Reset rules are per-component, per-action ([doc 09](./docs/research/09-maintenance-agent.md)): blade has no `FIX` (consumable, only `REPLACE`); rail's raceway pitting is permanent (FIX only addresses lubricant + corrosion); nozzle's `FIX` cleans clog scaled by `cleaning.efficiency`; heater's `FIX` halves drift, `REPLACE` swaps the element; sensor's `FIX` is calibration (zeros bias only — connector noise is irreversible without `REPLACE`).

</details>

<details>
<summary><strong>Stack & topology — Python-only (already locked in <code>sim/pyproject.toml</code>)</strong></summary>

| Layer | Choice | Why |
| :--- | :--- | :--- |
| Sim language | **Python ≥ 3.12** (3.12–3.14) + **uv** | numpy/scipy/pandas/scikit-learn for math + ML surrogate; pydantic for typed state |
| Sim libs | numpy · scipy · scikit-learn · pandas · matplotlib · streamlit · pydantic · pyyaml · httpx | Locked in `sim/pyproject.toml` |
| Persistence | **SQLite WAL** at `data/historian.sqlite` | One file, embeddable, queryable, commits to git for fallback |
| Dashboard | **Streamlit** | Pure Python; one app, all six demo charts |
| Deck charts | **matplotlib** | High-DPI PNG export for the slides |
| Lint / format / type | Ruff + ty | uv-managed; ruff `E F I B UP SIM`; quote-style double; pre-commit configured |
| Test | pytest + pytest-cov + pytest-xdist | uv-managed |
| LLM (maintenance-agent stretch) | optional `anthropic` extra | 1 call/sim-hour writing a rationale string |

**Critical SQLite hygiene** (from [`14`](./docs/research/14-stack-and-topology.md)): writer-side pragmas `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`. Streamlit reader opens the same file read-only.

**Domain types are already in code** at [`sim/src/copilot_sim/domain/`](./sim/src/copilot_sim/domain/) — frozen+slots dataclasses for `Drivers`, `CouplingContext`, `ComponentState` / `PrinterState`, `ObservedComponentState` / `ObservedPrinterState`, `MaintenanceAction`, `OperatorEvent`, plus the `OperationalStatus` (with `UNKNOWN`), `PrintOutcome`, `Severity`, `OperatorEventKind` enums. The component `step()` functions read `prev_state` + `coupling: CouplingContext` + `drivers: Drivers` + `dt` and return their slice of the next state — no exceptions, fully typed, ty-strict.

> The Next.js + better-sqlite3 + AI SDK web stack from [`14`](./docs/research/14-stack-and-topology.md) and the docs in 10–13 are **deferred** along with Phase 3. Preserved for future work.

</details>

<details>
<summary><strong>Domain priors — the citation trail behind the parameter choices</strong></summary>

[`15`](./docs/research/15-domain-priors.md): **HP Metal Jet S100** is binder-jet metal AM with **6 thermal inkjet printheads totalling 63,360 nozzles**, 1,200 dpi, 35–140 µm layer thickness, 1,990 cc/hr build speed, build platform 430 × 309 × 200 mm. Materials: 316L and 17-4 PH (later Sandvik Osprey 316L, Indo-MIM M2 tool steel). Customers: VW, GKN, Cobra Golf, Schneider Electric, Parmatech, Domin, Lumenium. Announced 2018, launched IMTS Sept 2022.

References: **recoater wear** (*Inside Metal Additive Manufacturing*, Jan 2024), **nozzle clogging** (Waasdorp et al., *RSC Advances*, 2018), **heating-element drift** (oxidation thins cross-section + thermal-cycle elongation → Ohm's-law power loss).

**NASA C-MAPSS** and **PHM Society** are visual shape priors only — flat → knee → cliff curve with regime-switching jumps. Not training data.

</details>

<details>
<summary><strong>Submission plan</strong></summary>

[`16`](./docs/research/16-submission-prep.md): six deliverables (repo, deck, report, demo, walkthrough video, optional bonus demo). Deadline placeholder Sun 2026-04-26 ~09:00 CEST — **action: confirm in Slack `C0AV9TTJT25` first hour of build day 2**. Doc 16's "Demo split" still mentions chatbot + voice; **the live demo is sim-only** (see "The killer demo" below). The deck and report outlines stay relevant once the chatbot slide is dropped or replaced with "future work".

</details>

---

## The killer demo (sim-only, 5 min)

Six charts, one SQLite historian, one Streamlit dashboard with scenario selectors:

1. **Six components degrading** under a chosen scenario (`barcelona-baseline-…`). Time-series of `health` for blade / rail / nozzle / cleaning / heater / sensor. Status colour bands (green / yellow / orange / red). At least one component reaches `FAILED` inside the window.
2. **The §3.4 sensor-fault story**: side-by-side **true vs observed** health for the heater + sensor pair. The heater appears to drift but the temperature sensor's `sensor_note = "drift"` reveals the real fault. The LLM-as-policy maintenance agent emits `TROUBLESHOOT(sensor)` → `REPLACE(sensor)` with a stored rationale.
3. **Same-seed three-policy A/B** ([`09`](./docs/research/09-maintenance-agent.md)): no-agent vs heuristic vs LLM-as-policy. `min(component_health)` over 180 days. Maintenance triangles (with `OperatorEventKind` colour) + FAILED ✗ markers. Title: *"Same printer, three policies, three uptimes."*
4. **What-if: Barcelona vs Phoenix** ([`07`](./docs/research/07-weather-api.md)). Same printer, same duty cycle, same seed; only `T_stress` and `Humidity` swap (Open-Meteo). Different failure modes dominate per climate (Phoenix → heater + sensor first, Barcelona → blade + nozzle first).
5. **AI surrogate parity** ([`05`](./docs/research/05-cascading-and-ai-degradation.md)): analytic Arrhenius curve vs MLPRegressor surrogate over the same 6-month run, MAE ≤ 2 %. Two lines that overlap.
6. **Coupling cascade attribution**: pick a moment when nozzle hits CRITICAL; query `coupling_factors_json` and walk back through the four hops — `nozzle.clog → humidity_contamination_effective → powder_spread_quality → blade.loss_frac × rail.alignment_error`. The dashboard renders the chain as a small graph.
7. (Stretch) **Chaos overlay**: same seed with `config.chaos = false` vs `true`. Poisson temp spikes amplifying the cascade.

Demo split: Chris ~3 min on math + chart 1 + chart 3, Jana / Leonie ~1 min on chart 4 (what-if), Daniel ~1 min on chart 2 (sensor-fault story) + chart 5 (surrogate). See [`16`](./docs/research/16-submission-prep.md) for the full minute-by-minute split.

---

## Pre-build research checklist

Each item links to its decision document. All locked on 2026-04-25.

<details>
<summary><strong>A. Phase 1 — picking the right failure math (6 components)</strong></summary>

- [x] **Recoater Blade — Abrasive Wear** → [`01-recoater-blade-archard.md`](./docs/research/01-recoater-blade-archard.md). Linear `Δh = k_eff · P · s_eff · dt / H_eff`; FAILED at ≥50 % thickness loss.
- [x] **Linear Guide / Rail — Mechanical Fatigue** → [`17-linear-rail.md`](./docs/research/17-linear-rail.md). Weibull β=2.0 / η=220 d + driver damage; FAILED at 50 µm alignment error; raceway pitting permanent.
- [x] **Nozzle Plate — Clogging + Thermal Fatigue** → [`02-nozzle-plate-coffin-manson.md`](./docs/research/02-nozzle-plate-coffin-manson.md). Coffin-Manson + Miner damage + Poisson clog hazard; composite `H = (1−clog%/100)·(1−D)`.
- [x] **Cleaning Interface — Wear-per-Cycle** → [`18-cleaning-interface.md`](./docs/research/18-cleaning-interface.md). Power-law `H_use = 1 − a·n^p`; rewrites doc 02's clog reset to `× (1 − cleaning_efficiency)`.
- [x] **Heating Elements — Electrical Degradation** → [`03-heating-elements-arrhenius.md`](./docs/research/03-heating-elements-arrhenius.md). Arrhenius AF, `E_a = 0.7 eV`; FAILED at +10 % drift.
- [x] **Temperature Sensor — Drift + §3.4 ref impl** → [`19-temperature-sensor.md`](./docs/research/19-temperature-sensor.md). PT100 bias drift Arrhenius-fast; reference per-component sensor model; hard FAILED at `\|bias_C\| > 5 °C`.
- [x] **Universal aging baselines** → [`04-aging-baselines-and-normalization.md`](./docs/research/04-aging-baselines-and-normalization.md). Weibull per component (table now 6 rows); multiplicative composition `H = H_base · H_driver`.
- [x] **Health-index normalisation** → same doc 04. Thresholds: `>0.75` FUNCTIONAL, `>0.40` DEGRADED, `>0.15` CRITICAL, else FAILED.
- [x] **Coupling matrix + cross-component coupling (bonus)** → [`05-cascading-and-ai-degradation.md`](./docs/research/05-cascading-and-ai-degradation.md). 12-row matrix; 3 two-way loops (rail↔blade, cleaning↔nozzle, sensor↔heater) + 2 cross-subsystem cascades (powder→jetting, thermal→everything); CouplingContext factor names locked.
- [x] **AI-degradation option (bonus)** → same doc 05. Heater = sklearn `MLPRegressor (32,32,32) tanh` on 20k Latin-Hypercube samples; acceptance gate MAE ≤ 2 %.
- [x] **Engine architecture (`Engine.step()` pattern)** → implemented in code at [`sim/src/copilot_sim/domain/`](./sim/src/copilot_sim/domain/) (commit `64b3e0d`). Frozen+slots dataclasses for `Drivers`, `CouplingContext`, `PrinterState`, `ObservedPrinterState`, `MaintenanceAction`, `OperatorEvent`. AGENTS.md locks the double-buffered update rule.
- [x] **§3.4 Observability split** → `TRACK-CONTEXT.md §3.4` (commit `bb73666`); reference impl in doc 19; historian schema in doc 08 mirrors true and observed views.

</details>

<details>
<summary><strong>B. Phase 2 — driver generation, time, and persistence</strong></summary>

- [x] **Driver-profile generators** → [`06-driver-profiles-and-time.md`](./docs/research/06-driver-profiles-and-time.md). Sinusoidal Temp, OU Humidity, monotonic+duty Load, step Maintenance.
- [x] **Live weather API** → [`07-weather-api.md`](./docs/research/07-weather-api.md). **Open-Meteo Archive API** (no auth, 10k/day, single GET returns 6 mo hourly).
- [x] **Time step + horizon** → doc 06. `dt = 1 h`, **4380 ticks** for 6 sim-months.
- [x] **Historian schema** → [`08-historian-schema.md`](./docs/research/08-historian-schema.md). SQLite WAL; **seven** tables: `runs`, `drivers` (now also carries `print_outcome` + `coupling_factors_json`), `component_state`, `metrics`, `observed_component_state`, `observed_metrics`, `events`. All time-series tables `WITHOUT ROWID`.
- [x] **Run/scenario identity** → same doc 08. Format `{scenario}-{profile}-{YYYYMMDD}-{seq}`.
- [x] **Stochastic mode (bonus)** → doc 06. Poisson temp spikes, contamination bursts, Bernoulli skipped maintenance. All seeded.
- [x] **AI Maintenance Agent (bonus)** → [`09-maintenance-agent.md`](./docs/research/09-maintenance-agent.md). Three-action vocabulary `TROUBLESHOOT/FIX/REPLACE`; reads only `ObservedPrinterState`; per-component reset rules updated for 6 components.

</details>

<details>
<summary><strong>C. Stack & repo skeleton (sim-only path)</strong></summary>

- [x] **Sim core language** → [`14-stack-and-topology.md`](./docs/research/14-stack-and-topology.md). Python 3.12 + uv.
- [x] **Sim libs** → numpy · pandas · simpy · scikit-learn · pydantic.
- [x] **Persistence** → SQLite WAL at `data/historian.sqlite`. WAL pragmas on writer; reader opens same file.
- [x] **Dashboard** → **Streamlit** (Python-native; one app, all five demo charts). matplotlib for deck PNG export.
- [x] **Repo layout** → see below; top-level `Makefile` with `make sim`, `make app`, `make seed`.

</details>

<details>
<summary><strong>D. Domain priors</strong></summary>

- [x] **HP Metal Jet S100** → [`15-domain-priors.md`](./docs/research/15-domain-priors.md). 6 printheads · 63,360 nozzles · 1,200 dpi · 316L/17-4 PH · launched IMTS 2022.
- [x] **Wear / clog / drift references** → same doc 15. Inside Metal AM 2024, Waasdorp et al. RSC 2018, oxidation+elongation chain.
- [x] **NASA C-MAPSS / PHM Society** → same doc 15. Visual shape prior only — flat → knee → cliff. Not training data.

</details>

<details>
<summary><strong>E. Submission-side prep</strong></summary>

- [x] **Submission deadline / format** → [`16-submission-prep.md`](./docs/research/16-submission-prep.md). Placeholder Sun 09:00 CEST; **confirm in Slack first hour of day 2**.
- [x] **Slide deck outline** → same doc 16, but drop the chatbot/voice slides (slides 7–8) for now and replace with "future work".
- [x] **Technical report outline** → same doc 16, omit Phase 3 section.
- [x] **Demo split** → see "The killer demo" above; Chris ~3 min on math + sim, Daniel ~2 min on bonuses.

</details>

<details>
<summary><strong>F. Phase 3 work — preserved, deferred</strong></summary>

These are written but not part of the current build:

- [`10-chatbot-architecture.md`](./docs/research/10-chatbot-architecture.md) — Pattern C ReAct, 5 tools, defense-in-depth citations.
- [`11-vercel-ai-sdk.md`](./docs/research/11-vercel-ai-sdk.md) — AI SDK v6 + Gateway, Sonnet 4.6 / Opus 4.6.
- [`12-proactive-alerts.md`](./docs/research/12-proactive-alerts.md) — sim-writes-events + client polling pattern.
- [`13-voice-interface.md`](./docs/research/13-voice-interface.md) — Web Speech primary, OpenAI Realtime stretch.

If Phase 1 + Phase 2 finishes early, revisit in this order: 10 → 11 → 12 → 13. Otherwise, future work for the deck.

</details>

---

## Repo layout (target — sim-focused)

<details>
<summary><strong>Show tree</strong></summary>

```
.
├── sim/
│   ├── pyproject.toml         # uv-managed
│   ├── engine/                # Phase 1 — pure formulas (blade, nozzle, heater, baseline)
│   │   ├── components/        # one file per component model
│   │   ├── composition.py     # H = H_base · H_driver, status mapping
│   │   └── surrogate.py       # MLPRegressor wrapper for the heater
│   ├── loop/                  # Phase 2 — clock + driver generators + writer
│   │   ├── drivers/           # sinusoid, OU, duty-cycle, step, weather adapter
│   │   ├── chaos.py           # Poisson spikes, contamination bursts
│   │   ├── historian.py       # SQLite WAL writer
│   │   └── main.py            # `python -m loop.main --scenario default`
│   ├── agent/                 # Phase 2 bonus — heuristic + LLM-as-policy
│   ├── scenarios/             # YAML driver profiles (barcelona, phoenix, chaos, abusive)
│   ├── viz/                   # Streamlit app + matplotlib export
│   └── tests/
├── data/
│   ├── historian.sqlite       # committed seed (regenerate with `make seed`)
│   └── weather/               # cached Open-Meteo JSON for Barcelona + Phoenix
├── docs/
│   ├── briefing/              # HP-provided source material
│   ├── research/              # 16 locked decision docs (10–13 deferred)
│   └── report/                # technical report + slide deck source
├── scripts/                   # one-shots: run scenario, train surrogate, export CSV
└── Makefile                   # `make sim`, `make app`, `make seed`, `make train`
```

</details>

---

## Next steps (build order)

✅ **Done:** `sim/pyproject.toml`, `sim/src/copilot_sim/domain/` (frozen+slots dataclasses for `Drivers`, `CouplingContext`, `PrinterState`, `ObservedPrinterState`, `MaintenanceAction`, `OperatorEvent`, plus the four enums), AGENTS.md engine update rule, `TRACK-CONTEXT.md §3.4` observability split.

▶ **Now:**

1. **Historian writer** ([doc 08](./docs/research/08-historian-schema.md)) in `sim/src/copilot_sim/historian/`. Smoke-test: empty DB created, all seven tables (4 true + observed_component_state + observed_metrics + events), indexes, WAL pragmas.
2. **`engine.coupling.build_coupling_context(prev, drivers, dt)`** following [doc 05](./docs/research/05-cascading-and-ai-degradation.md). Pure function over `prev_state`; populates the `factors` dict with the 7 named entries + the 4 `*_effective` drivers.
3. **Six per-component `step()` functions** in `sim/src/copilot_sim/components/`, in this order (easiest → hardest): blade ([01](./docs/research/01-recoater-blade-archard.md)) → heater ([03](./docs/research/03-heating-elements-arrhenius.md)) → rail ([17](./docs/research/17-linear-rail.md)) → cleaning ([18](./docs/research/18-cleaning-interface.md)) → nozzle ([02](./docs/research/02-nozzle-plate-coffin-manson.md)) → sensor ([19](./docs/research/19-temperature-sensor.md)). Each is deterministic, reads `(prev_self, coupling, drivers, dt)`, returns `next_self`. Unit-tested in isolation.
4. **Composition + status mapping** ([04](./docs/research/04-aging-baselines-and-normalization.md)): Weibull baseline + multiplicative composition + status enum, applied uniformly inside each `step()` to produce `ComponentState`.
5. **Per-component sensor models** ([19](./docs/research/19-temperature-sensor.md) §reference impl): `(true_value, sensor_state) → (observed_value, sensor_note)` — wraps each component's true output into an `ObservedComponentState`.
6. **`Engine.step()`**: read `prev_state`, call `build_coupling_context`, call all six `step()` functions from the same snapshot, assemble `next_state`, return — double-buffered. Plus `apply_maintenance(MaintenanceAction)` that mutates next state per [doc 09](./docs/research/09-maintenance-agent.md) reset rules.
7. **Phase 2 loop** ([06](./docs/research/06-driver-profiles-and-time.md)): driver generators (sin / OU / duty / step), `OpenMeteoDriver` adapter ([07](./docs/research/07-weather-api.md)), chaos overlay, tick loop, historian writes, `print_outcome` derivation. Commit a seeded `historian.sqlite` once it runs end-to-end.
8. **AI surrogate** ([05](./docs/research/05-cascading-and-ai-degradation.md)): 20k Latin-Hypercube samples, train MLPRegressor, joblib-dump, swap in behind `--heater-model={analytic,nn}`, prove parity.
9. **Maintenance agent** ([09](./docs/research/09-maintenance-agent.md)): heuristic first reading `ObservedPrinterState`, emitting `Action(kind, component_id)`; if time, LLM-as-policy A/B.
10. **Streamlit dashboard**: scenario selector, time-series with true-vs-observed toggle, A/B policy picker, surrogate-parity chart, coupling-cascade attribution panel. Export PNGs for the deck.
11. **Deck + report**: populate from the doc 16 sim-only outlines.
