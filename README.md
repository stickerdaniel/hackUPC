<div align="center">
  <h1>A digital twin for the HP Metal Jet S100.</h1>

  <p>
    Deterministic and coupled — six components across three subsystems, sensors that fail too, and an AI maintenance agent that learns to tell sensor faults from component faults. Live weather, a stochastic chaos layer, and an ML surrogate for the heater are wired in as bonus levers.
  </p>

  <p>
    <a href="https://www.python.org/"><img alt="Python ≥3.12" src="https://img.shields.io/badge/python-%E2%89%A53.12-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=000000"></a>
    <img alt="Scope: Phase 1 + Phase 2" src="https://img.shields.io/badge/scope-Phase_1_%2B_Phase_2-000000?style=for-the-badge">
    <img alt="Status: engine landing" src="https://img.shields.io/badge/status-engine_landing-7C3AED?style=for-the-badge">
    <img alt="HackUPC 2026" src="https://img.shields.io/badge/HackUPC-2026-FF4F00?style=for-the-badge">
  </p>

  <p>
    <a href="#cloning"><strong>Cloning</strong></a> ·
    <a href="#what-we-are-building"><strong>Architecture</strong></a> ·
    <a href="#research-synthesis-phase-1--phase-2"><strong>Research</strong></a> ·
    <a href="#the-killer-demo-sim-only-5-min"><strong>Demo</strong></a>
  </p>
</div>

Briefing: [`TRACK-CONTEXT.md`](./TRACK-CONTEXT.md) · Decisions: [`docs/research/`](./docs/research/) · Code: [`sim/`](./sim/)

> **Build scope: Phase 1 + Phase 2 only.** Phase 3 (chatbot, voice, frontend) is deferred.

---

## Cloning

The repo is plain git except for two oversized HP brand assets (one PowerPoint playbook, one Photoshop source) that exceed GitHub's 100 MB per-file hard limit and live in Git LFS. Install `git-lfs` first (`brew install git-lfs && git lfs install`, or your distro's equivalent), then clone normally:

```bash
git clone https://github.com/stickerdaniel/hackUPC.git
cd hackUPC
```

If you don't need the two LFS files (most contributors don't — everything else is regular git), skip the LFS payload:

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/stickerdaniel/hackUPC.git
```

You'll still get every other brand asset, all simulation code, and the docs. Pull individual LFS files later with `git lfs pull --include="<path>"`.

If you already cloned and the working tree contains ~130-byte text files where the binaries should be, run `git lfs install && git lfs pull` from the repo root.

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
| LLM (maintenance-agent stretch) | OpenRouter via `httpx` (no extra SDK); model swap via `LLM_MODEL` env var (default `google/gemma-4-31b-it`, A/B with `anthropic/claude-sonnet-4.6`) | 1 call/sim-hour writing a rationale string |

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

Six charts, one SQLite historian, one Streamlit dashboard:

- **Six components degrading** — health time-series with status bands; at least one hits `FAILED` in the window.
- **Sensor-fault story (§3.4)** — true vs observed for the heater+sensor pair; LLM agent emits `TROUBLESHOOT(sensor)` → `REPLACE(sensor)`.
- **Three-policy A/B** ([`09`](./docs/research/09-maintenance-agent.md)) — no-agent vs heuristic vs LLM, same seed, 180 days. *"Same printer, three policies, three uptimes."*
- **Barcelona vs Phoenix** ([`07`](./docs/research/07-weather-api.md)) — same printer + duty cycle + seed; only weather swaps. Phoenix kills the heater + sensor first; Barcelona kills the blade + nozzle first.
- **AI surrogate parity** ([`05`](./docs/research/05-cascading-and-ai-degradation.md)) — analytic vs MLP, MAE ≤ 2 %. Two lines that overlap.
- **Cascade attribution** — pick a CRITICAL moment, walk `coupling_factors_json` back four hops to its root cause.
- **Chaos overlay** *(stretch)* — same seed, `config.chaos = false` vs `true`.

Minute-by-minute split in [`16`](./docs/research/16-submission-prep.md).
