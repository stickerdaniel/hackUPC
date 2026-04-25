# hackUPC — When AI meets reality

**Digital Twin** for the **HP Metal Jet S100**: a deterministic, mathematically-grounded simulation of three component subsystems aging under realistic environmental and operational drivers, with one-way component cascade, an AI-driven surrogate model, live weather as a driver, a stochastic chaos overlay, and an AI Maintenance Agent.

Full briefing: [`TRACK-CONTEXT.md`](./TRACK-CONTEXT.md). Source docs: [`docs/briefing/`](./docs/briefing/). Decision docs: [`docs/research/`](./docs/research/).

> **Build scope: Phase 1 + Phase 2 only.** Phase 3 (chatbot, voice, frontend) is **deferred** for this iteration. Research docs 10–13 are preserved for future work but are not the current build target. Visualisation uses Python-native tools (Streamlit + matplotlib), not a Next.js/React UI.

---

## Status

**Research complete — building the digital twin.** All Phase 1 + Phase 2 decisions are locked in [`docs/research/`](./docs/research/).

---

## What we are building

A digital twin that doesn't just visualise telemetry — it **simulates the physics of failure** across three subsystems and lets us run "what if?" scenarios that would take months on real hardware.

```
                ┌──────────────────────┐
input drivers ─▶│  Phase 1 — Logic     │──▶ component health (t)
(temp, humidity,│  Engine: 3 components │
 load, maint.)  │  × 3 textbook laws    │
 + live weather │  × Weibull baseline   │
                │  × multiplicative comp│
                └──────────────────────┘
                          ▲ │
            previous state│ │ next state (deterministic, seeded)
                          │ ▼
                ┌──────────────────────┐
                │  Phase 2 — Clock +   │  ──▶  Historian (SQLite WAL)
                │  Driver Generator +  │       runs · drivers ·
                │  Chaos Layer + Loop  │       component_state ·
                │                      │       metrics · events
                └──────────────────────┘
                          ▲ │
                 modifies │ │ reads
                          │ ▼
                ┌──────────────────────┐
                │  AI Maintenance Agent│  Phase 2 bonus
                │  (heuristic primary, │  same-seed A/B chart:
                │   LLM-as-policy A/B) │  no-agent vs heuristic vs LLM
                └──────────────────────┘
                            │
                            ▼
                ┌──────────────────────┐
                │  Streamlit Dashboard │  ──▶  judges + operators
                │  Time-series viz +   │       (Phase 2 minimum
                │  scenario picker     │        deliverable)
                └──────────────────────┘
```

**Strategic bet:** stack maximum bonus pillars in Phase 1 + Phase 2.

| Phase 1 evaluation | Phase 2 evaluation |
| :--- | :--- |
| Rigor — three textbook laws, all parameters cited | Time moves — `dt = 1h` × 4380 ticks, 6 sim-months |
| Systemic Interaction — all 4 drivers wired into all 3 components | Systemic Integration — Phase 1 called every tick, persisted |
| **Complexity & Innovation (bonus)** — cascade + AI surrogate | **Complexity & Innovation (bonus)** — chaos + maintenance agent |
| **Realism & Fidelity (bonus)** — physically motivated knees + thresholds | **Realism & Fidelity (bonus)** — live weather driver, stochastic shocks |

Bonus pillars we are explicitly going for: **Cascading Failures · Stochastic Realism · Maintenance as Input · AI-Powered Degradation · Live Environmental Data · What-If Scenarios · Chaos Engineering · AI Maintenance Agent**. Eight of the brief's nine sim-side bonus levers in one repo.

---

## Research synthesis (Phase 1 + Phase 2)

The research agents collectively answered: *given the brief, what is the smallest defensible set of decisions that lets us start building today?* Each section below summarises a doc; click into [`docs/research/`](./docs/research/) for parameter values, math, references, and open questions.

### Phase 1 — three components, three textbook formulas, one shared composition rule

We model exactly the three mandatory components, each with its own driver-specific failure law layered under a shared Weibull aging baseline. The driver-specific layer ([`01`](./docs/research/01-recoater-blade-archard.md), [`02`](./docs/research/02-nozzle-plate-coffin-manson.md), [`03`](./docs/research/03-heating-elements-arrhenius.md)) is what the judges came to see — three textbook-distinct mechanisms, all hooked to the four required drivers. The aging baseline ([`04`](./docs/research/04-aging-baselines-and-normalization.md)) gives every component a graceful "background drift" independent of the drivers, so even a perfectly-operated machine eventually fails.

| Subsystem | Component | Math | State metric | FAILED at | Dominant driver |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Recoating | **Recoater Blade** | Archard wear `Δh = k_eff·P·s_eff·dt/H` | thickness (mm) | 50% loss (~6 mo) | Humidity/Contamination → `k_eff = k0·(1+1.5·C)` |
| Printhead | **Nozzle Plate** | Coffin-Manson + Miner damage **and** Poisson clog hazard | composite `(1−clog%)·(1−D)` | `H ≤ 0.20` or `clog ≥ 95%` or `D ≥ 1` | Temp Stress → both, Contamination → λ |
| Thermal | **Heating Elements** | Arrhenius acceleration factor with self-heating feedback | resistance Ω drift (%) | +10% drift | Temperature Stress → AF (exponential) |

**Composition** ([`04`](./docs/research/04-aging-baselines-and-normalization.md)): `H_total = H_baseline(t) · H_driver(damage)`, both `[0,1]`. Multiplicative because failure modes compose in series-reliability theory (`R_system = ∏ R_i`), bounds are natural, and any health drop decomposes into "baseline aging is 0.78, driver damage is 0.79".

**Status thresholds** (single shared mapping): `> 0.75` FUNCTIONAL · `> 0.40` DEGRADED · `> 0.15` CRITICAL · else FAILED. The CRITICAL floor was raised from the suggested 0.10 so a future alert layer would have a useful warning window before terminal failure.

**Two bonus levers** ([`05`](./docs/research/05-cascading-and-ai-degradation.md)) for Complexity & Innovation points without inventing physics:

- **Cascade**: blade `loss_frac` continuously injects into the nozzle's effective contamination input (`+0.5 · loss_frac`, capped at +0.25). A worn blade *makes* a clog. Alternative cascade (heater drift → temp-stress upgrade hitting nozzle and other heaters) is ready in case a judge says the blade story is too cute.
- **AI surrogate**: the heater's analytic Arrhenius function gets replaced by a sklearn `MLPRegressor (32,32,32)` trained on 20k Latin-Hypercube samples from the formula itself. Acceptance gate is MAE ≤ 2 % on the test set; the deck slide is "two lines that overlap perfectly".

### Phase 2 — driving it forward in time

The simulation loop generates four synthetic drivers per tick, calls the Phase 1 engine, and writes everything to a SQLite historian. The driver generators ([`06`](./docs/research/06-driver-profiles-and-time.md)) are the simplest defensible choice per signal: sinusoidal day+season for Temperature, Ornstein-Uhlenbeck (Euler-Maruyama) for Humidity, monotonic + duty-cycle for Operational Load, step function for Maintenance Level. All draws share one seeded `numpy.random.default_rng(seed)` so runs are bit-exact reproducible — the brief's determinism contract requires it.

**Time step**: `dt = 1` simulated hour, **4380 ticks for 6 sim-months**. Justified because the slowest failure modes evolve over hundreds-to-thousands of hours; 4380 SQLite inserts is sub-second; demo can fast-forward to `dt = 6h` (~730 ticks) for a 5-second full lifecycle.

**Live weather as a driver** ([`07`](./docs/research/07-weather-api.md)): **Open-Meteo Archive API** wins decisively. No API key, 10k calls/day free, **single GET returns 6 months of hourly `temperature_2m + relative_humidity_2m`**. OpenWeather's One Call 3.0 needs ~4380 separate requests for the same window, plus a credit card on file — disqualifying for a 36-hour build. We cache both Barcelona (41.39, 2.16) and Phoenix (33.45, -112.07) JSONs in the repo so the demo never depends on live network. The weather only patches `T_stress` and `Humidity`; Operational Load and Maintenance stay scenario-controlled, which is what makes Barcelona-vs-Phoenix a clean A/B (only 2 of 4 drivers change).

**Historian schema** ([`08`](./docs/research/08-historian-schema.md)): SQLite WAL, file at `data/historian.sqlite`. Long-form normalised across five tables instead of one wide row:

```
runs              ── one row per simulation run
drivers           ── one row per (run, ts), holds the 4 driver values
component_state   ── one row per (run, ts, component), holds health + status
metrics           ── one row per (run, ts, component, metric_name) — handles multi-metric components
events            ── sparse log: maintenance, status transitions, chaos injections
```

All time-series tables are `WITHOUT ROWID` so the PK B-tree IS the storage — no extra index level. PKs cover `(run_id, ts)` lookups natively; one extra index on `metrics(run_id, component, metric_name, ts)` matches the dominant query. **Volume**: ~26k metric + ~13k state + ~4.4k driver rows per run — under 50k total, a few MB, checks into git as a fallback. **`run_id` format** locked: `{scenario}-{profile}-{YYYYMMDD}-{seq}` (e.g. `barcelona-baseline-20260425-1`).

**Stochastic mode** (Phase 2 bonus pattern C, [`06`](./docs/research/06-driver-profiles-and-time.md)): a chaos layer overlays the deterministic profile when `config.chaos = true`. Poisson temp spikes (λ=2/month, ΔT~N(8,2) °C, exp decay), contamination bursts (λ=3/month, OU absorbs), Bernoulli skipped maintenance (p=0.1). Calibrated so ~1 in 3 seeds produces a CRITICAL within the 6-month horizon — not boring, not apocalyptic.

**AI Maintenance Agent** (Phase 2 bonus, [`09`](./docs/research/09-maintenance-agent.md)): primary is a **two-rule heuristic** (`if any health < 0.40 → maintain`, plus a 30-day scheduled trigger if `min(health) < 0.60`). Stretch is **LLM-as-policy** with the same `decide()` signature, called once per simulated hour, writing a one-sentence rationale to the events table. RL is *specified* (full Gymnasium env spec, reward `+1/tick alive, −100/FAILED, −2/maintain`, 4320 steps × 180-day episode) but not implemented, so we have a precise answer for "did you consider RL?".

Maintenance effects are per-component reset rules, not global: blade replaceable (`D←0`, `t_eff←0`, thickness restored), nozzle 80 % recoverable (`D ← 0.2·D`, clog reset, fatigue × 0.5), heater field-uncalibratable (`D ← 0.5·D`, no thickness restore — heaters need lab work). The killer chart: same seed, three policies (no-agent / heuristic / LLM), `min(health)` over 180 days, with maintenance triangles and FAILED markers.

### Stack & topology — Python-only

| Layer | Choice | Why |
| :--- | :--- | :--- |
| Sim language | **Python 3.12 + uv** | numpy/pandas/simpy/sklearn for the math + ML surrogate |
| Sim libs | numpy · pandas · simpy · scikit-learn · pydantic | Phase 1 formulas + ML surrogate + typed driver/state schemas |
| Persistence | **SQLite WAL** at `data/historian.sqlite` | One file, embeddable, queryable, commits to git for fallback |
| Dashboard | **Streamlit** | Pure Python, dashboards in <30 lines, scenario comparison is one selectbox |
| Deck charts | **matplotlib** | High-DPI PNG export for the slides |
| Lint / format | Ruff + Black | uv-managed |
| LLM (for the maintenance-agent stretch only) | Direct Anthropic SDK or `httpx` against Claude | We only need 1 call/sim-hour writing a rationale string — no Vercel AI SDK, no streaming, no tool-calling |

**Critical SQLite hygiene** (from [`14`](./docs/research/14-stack-and-topology.md)): writer-side pragmas `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`. Streamlit reader opens the same file read-only.

> The Next.js + better-sqlite3 + AI SDK web stack from [`14`](./docs/research/14-stack-and-topology.md) and the docs in 10–13 are **deferred** along with Phase 3. They're preserved, but not in the current build path.

### Domain priors — the citation trail behind the parameter choices

[`15`](./docs/research/15-domain-priors.md): **HP Metal Jet S100** is binder-jet metal AM with **6 thermal inkjet printheads totalling 63,360 nozzles**, 1,200 dpi, 35–140 µm layer thickness, 1,990 cc/hr build speed, build platform 430 × 309 × 200 mm. Materials: 316L and 17-4 PH (later Sandvik Osprey 316L, Indo-MIM M2 tool steel). Customers: VW, GKN, Cobra Golf, Schneider Electric, Parmatech, Domin, Lumenium. Announced 2018, launched IMTS Sept 2022.

References: **recoater wear** (*Inside Metal Additive Manufacturing*, Jan 2024), **nozzle clogging** (Waasdorp et al., *RSC Advances*, 2018), **heating-element drift** (oxidation thins cross-section + thermal-cycle elongation → Ohm's-law power loss).

**NASA C-MAPSS** and **PHM Society** are visual shape priors only — flat → knee → cliff curve with regime-switching jumps. Not training data.

### Submission plan

[`16`](./docs/research/16-submission-prep.md): six deliverables (repo, deck, report, demo, walkthrough video, optional bonus demo). Deadline placeholder Sun 2026-04-26 ~09:00 CEST — **action: confirm in Slack `C0AV9TTJT25` first hour of build day 2**. Note: the "Demo split" section in doc 16 still mentions chatbot + voice; **the live demo will be sim-only** (see "The killer demo" below). The deck and report outlines stay relevant once the chatbot slide is dropped or replaced with "future work".

---

## The killer demo (sim-only, 5 min)

Five charts/screens, all from the same SQLite historian, pre-rendered as a Streamlit dashboard with scenario selectors:

1. **Three components degrading** under a chosen scenario (`barcelona-baseline-…`). Time-series of `health` for blade / nozzle / heater. Status colour bands (green / yellow / orange / red). At least one component reaches `FAILED` inside the window.
2. **Same-seed three-policy A/B** ([`09`](./docs/research/09-maintenance-agent.md)): no-agent vs heuristic vs LLM-as-policy. `min(component_health)` over 180 days. Maintenance triangles + FAILED ✗ markers. Title: *"Same printer, three policies, three uptimes."*
3. **What-if: Barcelona vs Phoenix**. Same printer, same duty cycle, same seed; only `T_stress` and `Humidity` swap (Open-Meteo). Shows different failure modes dominate per climate (Phoenix → heater first, Barcelona → blade + nozzle first).
4. **AI surrogate parity** ([`05`](./docs/research/05-cascading-and-ai-degradation.md)): analytic Arrhenius curve vs MLPRegressor surrogate over the same 6-month run, MAE ≤ 2 %. Two lines that overlap.
5. **Cascade story**: same scenario with cascade off vs on. Without cascade the nozzle hangs in there; with cascade, the worn blade tips it over. Annotate the moment `loss_frac > 0.4`.
6. (Stretch) **Chaos overlay**: same seed with `config.chaos = false` vs `true`. Poisson temp spikes amplifying the cascade.

Demo split: Chris ~3 min on math + chart 1 + chart 2 + chart 3, Daniel ~2 min on cascade + surrogate + chaos + closing.

---

## Pre-build research checklist

Each item links to its decision document. All locked on 2026-04-25.

### A. Phase 1 — picking the right failure math

- [x] **Recoater Blade — Abrasive Wear** → [`01-recoater-blade-archard.md`](./docs/research/01-recoater-blade-archard.md). Linear `Δh = k_eff · P · s_eff · dt / H_eff`; `k0 = 5e-5`, contamination scales `k` by `(1 + 1.5·C)`; FAILED at ≥50 % thickness loss (~6 months nominal).
- [x] **Nozzle Plate — Clogging + Thermal Fatigue** → [`02-nozzle-plate-coffin-manson.md`](./docs/research/02-nozzle-plate-coffin-manson.md). Coffin-Manson with Palmgren-Miner accumulation + Poisson clog hazard `λ(t) = λ_0·(1+α|ΔT|)·(1+β·C)/M`; composite `H = (1−clog%/100)·(1−D)`.
- [x] **Heating Elements — Electrical Degradation** → [`03-heating-elements-arrhenius.md`](./docs/research/03-heating-elements-arrhenius.md). Arrhenius acceleration-factor form, `E_a = 0.7 eV`; resistance drift compounded per tick; FAILED at +10 % drift.
- [x] **Universal aging baselines** → [`04-aging-baselines-and-normalization.md`](./docs/research/04-aging-baselines-and-normalization.md). All Weibull (β=2.5/η=180d blade, β=2.0/η=150d nozzle, β=1.0/η=240d heater); multiplicative composition `H = H_base · H_driver`.
- [x] **Health-index normalisation** → same doc 04. Thresholds: `>0.75` FUNCTIONAL, `>0.40` DEGRADED, `>0.15` CRITICAL, else FAILED.
- [x] **Cross-component coupling (bonus)** → [`05-cascading-and-ai-degradation.md`](./docs/research/05-cascading-and-ai-degradation.md). One-way Blade → Nozzle: `C_nozzle_eff = clamp(C_input + 0.5 · blade.loss_frac, 0, 1)`.
- [x] **AI-degradation option (bonus)** → same doc 05. Heater = sklearn `MLPRegressor (32,32,32)` trained on 20k Latin-Hypercube samples; acceptance gate MAE ≤ 2 %.

### B. Phase 2 — driver generation, time, and persistence

- [x] **Driver-profile generators** → [`06-driver-profiles-and-time.md`](./docs/research/06-driver-profiles-and-time.md). Sinusoidal Temp, OU Humidity, monotonic+duty Load, step Maintenance.
- [x] **Live weather API** → [`07-weather-api.md`](./docs/research/07-weather-api.md). **Open-Meteo Archive API** (no auth, 10k/day, single GET returns 6 mo hourly).
- [x] **Time step + horizon** → doc 06. `dt = 1 h`, **4380 ticks** for 6 sim-months.
- [x] **Historian schema** → [`08-historian-schema.md`](./docs/research/08-historian-schema.md). SQLite WAL; long-form normalised: `runs`, `drivers`, `component_state`, `metrics`, `events`. All `WITHOUT ROWID`.
- [x] **Run/scenario identity** → same doc 08. Format `{scenario}-{profile}-{YYYYMMDD}-{seq}`.
- [x] **Stochastic mode (bonus)** → doc 06. Poisson temp spikes, contamination bursts, Bernoulli skipped maintenance. All seeded.
- [x] **AI Maintenance Agent (bonus)** → [`09-maintenance-agent.md`](./docs/research/09-maintenance-agent.md). Heuristic primary; LLM-as-policy stretch; full Gymnasium env spec on standby.

### C. Stack & repo skeleton (sim-only path)

- [x] **Sim core language** → [`14-stack-and-topology.md`](./docs/research/14-stack-and-topology.md). Python 3.12 + uv.
- [x] **Sim libs** → numpy · pandas · simpy · scikit-learn · pydantic.
- [x] **Persistence** → SQLite WAL at `data/historian.sqlite`. WAL pragmas on writer; reader opens same file.
- [x] **Dashboard** → **Streamlit** (Python-native; one app, all five demo charts). matplotlib for deck PNG export.
- [x] **Repo layout** → see below; top-level `Makefile` with `make sim`, `make app`, `make seed`.

### D. Domain priors

- [x] **HP Metal Jet S100** → [`15-domain-priors.md`](./docs/research/15-domain-priors.md). 6 printheads · 63,360 nozzles · 1,200 dpi · 316L/17-4 PH · launched IMTS 2022.
- [x] **Wear / clog / drift references** → same doc 15. Inside Metal AM 2024, Waasdorp et al. RSC 2018, oxidation+elongation chain.
- [x] **NASA C-MAPSS / PHM Society** → same doc 15. Visual shape prior only — flat → knee → cliff. Not training data.

### E. Submission-side prep

- [x] **Submission deadline / format** → [`16-submission-prep.md`](./docs/research/16-submission-prep.md). Placeholder Sun 09:00 CEST; **confirm in Slack first hour of day 2**.
- [x] **Slide deck outline** → same doc 16, but drop the chatbot/voice slides (slides 7–8) for now and replace with "future work".
- [x] **Technical report outline** → same doc 16, omit Phase 3 section.
- [x] **Demo split** → see "The killer demo" above; Chris ~3 min on math + sim, Daniel ~2 min on bonuses.

### F. Phase 3 work — preserved, deferred

These are written but not part of the current build:

- [`10-chatbot-architecture.md`](./docs/research/10-chatbot-architecture.md) — Pattern C ReAct, 5 tools, defense-in-depth citations.
- [`11-vercel-ai-sdk.md`](./docs/research/11-vercel-ai-sdk.md) — AI SDK v6 + Gateway, Sonnet 4.6 / Opus 4.6.
- [`12-proactive-alerts.md`](./docs/research/12-proactive-alerts.md) — sim-writes-events + client polling pattern.
- [`13-voice-interface.md`](./docs/research/13-voice-interface.md) — Web Speech primary, OpenAI Realtime stretch.

If Phase 1 + Phase 2 finishes early, revisit in this order: 10 → 11 → 12 → 13. Otherwise, future work for the deck.

---

## Repo layout (target — sim-focused)

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

---

## Next steps (build order)

1. **Scaffold `sim/`** with `uv init` and the historian schema from [doc 08](./docs/research/08-historian-schema.md). Smoke-test: empty DB created, all five tables, indexes, WAL pragmas.
2. **Phase 1 components**, easiest first: blade ([01](./docs/research/01-recoater-blade-archard.md)) → heater ([03](./docs/research/03-heating-elements-arrhenius.md)) → nozzle ([02](./docs/research/02-nozzle-plate-coffin-manson.md)). Each has a deterministic `step(prev, drivers, dt) → next` and unit tests.
3. **Composition layer** ([04](./docs/research/04-aging-baselines-and-normalization.md)): Weibull baseline + multiplicative composition + status enum.
4. **Phase 2 loop** ([06](./docs/research/06-driver-profiles-and-time.md)): driver generators, tick loop, historian writes. Commit a seeded `historian.sqlite` once it runs end-to-end.
5. **Cascade** ([05](./docs/research/05-cascading-and-ai-degradation.md)): one-way blade → nozzle wiring inside the Phase 1 step.
6. **AI surrogate** ([05](./docs/research/05-cascading-and-ai-degradation.md)): generate 20k Latin-Hypercube samples, train MLPRegressor, joblib-dump, swap in behind a `--heater-model={analytic,nn}` flag, prove parity.
7. **Live weather** ([07](./docs/research/07-weather-api.md)): cache Barcelona + Phoenix JSON, wire `OpenMeteoDriver` adapter behind the same interface as the synthetic generator.
8. **Chaos layer** ([06](./docs/research/06-driver-profiles-and-time.md)): Poisson spikes / contamination bursts / Bernoulli skipped maintenance, all seeded.
9. **Maintenance agent** ([09](./docs/research/09-maintenance-agent.md)): heuristic first; produce the same-seed three-policy chart with no-agent + heuristic; if time, LLM-as-policy A/B.
10. **Streamlit dashboard**: scenario selector, time-series charts, A/B picker, surrogate-parity chart, cascade on/off toggle. Export PNGs for the deck.
11. **Deck + report**: populate from the doc 16 outline minus the Phase 3 slides.
