# hackUPC — When AI meets reality

Digital Co-Pilot for the **HP Metal Jet S100**. Models component degradation, simulates the printer forward in time, and exposes a grounded natural-language interface over the resulting telemetry.

Full briefing: [`TRACK-CONTEXT.md`](./TRACK-CONTEXT.md). Source docs: [`docs/briefing/`](./docs/briefing/). Decision docs: [`docs/research/`](./docs/research/).

---

## Status

**Research complete — ready to build.** All 16 pre-build decisions are locked. See [`docs/research/`](./docs/research/) for the full set; each links its sources.

---

## What we are building

A digital twin that doesn't just visualise telemetry — it **diagnoses its own future failures and tells the operator how to prevent them**, with every claim cited against a row in the historian.

```
                ┌──────────────────────┐
input drivers ─▶│  Degradation Model   │──▶ component health (t)
(temp, humidity,│  3 components × math │
 load, maint.)  └──────────────────────┘
                          ▲ │
            previous state│ │ next state
                          │ ▼
                ┌──────────────────────┐
                │  Simulation Loop     │  ──▶  Historian (SQLite, WAL)
                │  state(t+1) =        │       runs · drivers · component_state
                │    f(state(t), x(t)) │       metrics · events
                └──────────────────────┘
                          ▲ │
                 modifies │ │ reads
                          │ ▼
                ┌──────────────────────┐
                │  AI Maintenance Agent│  (heuristic primary, LLM-as-policy stretch)
                │  decides when to     │
                │  trigger maintenance │
                └──────────────────────┘
                            │
                            ▼
                ┌──────────────────────┐
                │  UX Layer (Next.js)  │
                │  - Time-series board │
                │  - Grounded chatbot  │  ──▶  user (text + voice)
                │    (ReAct, 5 tools)  │
                │  - Proactive alerts  │
                └──────────────────────┘
                            │
                            └─▶ every answer cites historian rows
```

Strategic bet: **Phase 3 is where we win** — agentic ReAct loop with mechanically-enforced citations, proactive `CRITICAL` alerts before the operator asks, and Web Speech voice mode. All four Phase 3 evaluation pillars (Reliability · Intelligence · Autonomy · Versatility) are addressable from the same code path.

---

## Research synthesis

The 16 research agents collectively answered: *given the brief, what is the smallest defensible set of decisions that lets us start building today?* What follows is the executive summary; the actual decision documents under [`docs/research/`](./docs/research/) hold the parameter values, math, references, and open questions.

### Phase 1 — three components, three textbook formulas, one shared composition rule

We model exactly the three mandatory components, each with its own driver-specific failure law layered under a shared Weibull aging baseline. The driver-specific layer ([`01`](./docs/research/01-recoater-blade-archard.md), [`02`](./docs/research/02-nozzle-plate-coffin-manson.md), [`03`](./docs/research/03-heating-elements-arrhenius.md)) is what the judges came to see — three textbook-distinct mechanisms, all hooked to the four required drivers. The aging baseline ([`04`](./docs/research/04-aging-baselines-and-normalization.md)) gives every component a graceful "background drift" that exists independently of the drivers, so even a perfectly-operated machine eventually fails.

| Subsystem | Component | Math | State metric | FAILED at | Dominant driver |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Recoating | **Recoater Blade** | Archard wear `Δh = k_eff·P·s_eff·dt/H` | thickness (mm) | 50% loss (~6 mo) | Humidity/Contamination → `k_eff = k0·(1+1.5·C)` |
| Printhead | **Nozzle Plate** | Coffin-Manson + Miner damage **and** Poisson clog hazard | composite `(1−clog%)·(1−D)` | `H ≤ 0.20` or `clog ≥ 95%` or `D ≥ 1` | Temp Stress → both, Contamination → λ |
| Thermal | **Heating Elements** | Arrhenius acceleration factor with self-heating feedback | resistance Ω drift (%) | +10% drift | Temperature Stress → AF (exponential) |

**Composition** ([`04`](./docs/research/04-aging-baselines-and-normalization.md)): `H_total = H_baseline(t) · H_driver(damage)`, both `[0,1]`. Multiplicative because failure modes compose in series-reliability theory (`R_system = ∏ R_i`), bounds are natural, and the chatbot can decompose any drop into "baseline aging is 0.78, driver damage is 0.79".

**Status thresholds** (single shared mapping): `> 0.75` FUNCTIONAL · `> 0.40` DEGRADED · `> 0.15` CRITICAL · else FAILED. The CRITICAL floor was raised from the suggested 0.10 so the proactive-alert agent has a useful warning window before terminal failure.

**Two bonus levers** ([`05`](./docs/research/05-cascading-and-ai-degradation.md)) for "Complexity & Innovation" points without inventing physics:

- **Cascade**: blade `loss_frac` continuously injects into the nozzle's effective contamination input (`+0.5 · loss_frac`, capped at +0.25). A worn blade *makes* a clog. Alternative cascade (heater drift → temp-stress upgrade hitting nozzle and other heaters) is ready in case a judge says the blade story is too cute.
- **AI surrogate**: the heater's analytic Arrhenius function gets replaced by a sklearn `MLPRegressor (32,32,32)` trained on 20k Latin-Hypercube samples from the formula itself. Acceptance gate is MAE ≤ 2% on the test set; the deck slide is "two lines that overlap perfectly".

### Phase 2 — driving it forward in time

The simulation loop generates four synthetic drivers per tick, calls the Phase 1 engine, and writes everything to a SQLite historian. The driver generators ([`06`](./docs/research/06-driver-profiles-and-time.md)) are the simplest defensible choice per signal: sinusoidal day+season for Temperature, Ornstein-Uhlenbeck (Euler-Maruyama) for Humidity (mean-reverting noise is the textbook environmental model), monotonic + duty-cycle for Operational Load, step function for Maintenance Level. All draws share one seeded `numpy.random.default_rng(seed)` so runs are bit-exact reproducible — the brief's determinism contract requires it.

**Time step**: `dt = 1` simulated hour, **4380 ticks for 6 sim-months**. Justified because the slowest failure modes evolve over hundreds-to-thousands of hours; 4380 SQLite inserts is sub-second; demo can fast-forward to `dt = 6h` (~730 ticks) for a 5-second full lifecycle if needed.

**Live weather as a driver** ([`07`](./docs/research/07-weather-api.md)): **Open-Meteo Archive API** wins decisively. No API key, 10k calls/day free, **single GET returns 6 months of hourly `temperature_2m + relative_humidity_2m`**. OpenWeather's One Call 3.0 needs ~4380 separate requests for the same window, plus a credit card on file — disqualifying for a 36-hour build. We cache both Barcelona (41.39, 2.16) and Phoenix (33.45, -112.07) JSONs in the repo so the demo never depends on live network. The weather only patches `T_stress` and `Humidity`; Operational Load and Maintenance stay scenario-controlled, which is what makes Barcelona-vs-Phoenix a clean A/B (only 2 of 4 drivers change).

**Historian schema** ([`08`](./docs/research/08-historian-schema.md)): SQLite WAL, file at `data/historian.sqlite`. Long-form normalised across five tables instead of one wide row:

```
runs              ── one row per simulation run
drivers           ── one row per (run, ts), holds the 4 driver values
component_state   ── one row per (run, ts, component), holds health + status
metrics           ── one row per (run, ts, component, metric_name) — handles multi-metric components
events            ── sparse log: maintenance, status transitions, chaos injections
```

All time-series tables are `WITHOUT ROWID` so the PK B-tree IS the storage — no extra index level. PKs cover `(run_id, ts)` lookups natively; one extra index on `metrics(run_id, component, metric_name, ts)` matches the dominant Phase 3 query. **Volume**: ~26k metric + ~13k state + ~4.4k driver rows per run — under 50k total, a few MB, checks into git as a fallback. **`run_id` format** locked: `{scenario}-{profile}-{YYYYMMDD}-{seq}` (e.g. `barcelona-baseline-20260425-1`).

**Stochastic mode** (Phase 2 bonus pattern C, [`06`](./docs/research/06-driver-profiles-and-time.md)): a chaos layer overlays the deterministic profile when `config.chaos = true`. Poisson temp spikes (λ=2/month, ΔT~N(8,2)°C, exp decay), contamination bursts (λ=3/month, OU absorbs), Bernoulli skipped maintenance (p=0.1). Calibrated so ~1 in 3 seeds produces a CRITICAL within the 6-month horizon — not boring, not apocalyptic.

**AI Maintenance Agent** (Phase 2 bonus, [`09`](./docs/research/09-maintenance-agent.md)): primary is a **two-rule heuristic** (`if any health < 0.40 → maintain`, plus a 30-day scheduled trigger if `min(health) < 0.60`). Stretch is **LLM-as-policy** with the same `decide()` signature, called once per simulated hour, writing a one-sentence rationale to the events table — every maintenance event becomes citeable from the chatbot. RL is *specified* (full Gymnasium env spec, reward `+1/tick alive, −100/FAILED, −2/maintain`, 4320 steps × 180-day episode) but not implemented, so we have a precise answer for "did you consider RL?". Maintenance effects are per-component reset rules, not global: blade replaceable (`D←0`, `t_eff←0`, thickness restored), nozzle 80% recoverable (`D ← 0.2·D`, clog reset, fatigue × 0.5), heater field-uncalibratable (`D ← 0.5·D`, no thickness restore — heaters need lab work). The killer chart: same seed, three policies (no-agent / heuristic / LLM), `min(health)` over 180 days, with maintenance triangles and FAILED markers.

### Phase 3 — the grounded co-pilot (where we win)

This is the strategic bet. The architecture ([`10`](./docs/research/10-chatbot-architecture.md)) is **Pattern C (Agentic ReAct)** with B and A as graceful fallbacks emerging from the same code path — a one-step ReAct loop calling `current_status()` *is* Pattern A. All three brief patterns from one codebase. **Five read-only tools**, every one returning evidence-shaped rows so the LLM has nothing else to cite with:

| Tool | Purpose | Returns |
| :--- | :--- | :--- |
| `current_status(component?)` | Latest snapshot — Pattern A baseline | rows w/ severity, drivers |
| `query_health(component, time_range, run_id?)` | Time-series fetch — Pattern B's bread-and-butter | rows w/ ts, health, metric_value, severity |
| `get_failure_events(run_id?, severity?, component?)` | Discrete events | events w/ kind, severity, ts |
| `compare_runs(run_a, run_b, component?)` | Cross-run delta | summary + evidence array |
| `recommend_action(component)` | Policy lookup (NOT LLM-decided) | `{action, priority, source}` |

**Citation enforcement is defense in depth**: (A) Zod-constrained final output where every assertion needs `≥ 1 evidence` row with `{run_id, ts, component, metric, value}`; plus (B) a transcript-hash validator that hashes every `(run_id, ts, component, metric)` tuple from tool returns into a Set and rejects any cited tuple not in the Set, with 2 retries before falling through to "I don't have enough data". Fabrication becomes mechanically impossible at the response boundary, not just discouraged in prose.

**Severity is deterministic, computed in the tool layer** before the LLM ever sees a row. Mapping reuses doc 04's thresholds — no re-litigating numbers, one severity function in code: `H > 0.75 → INFO`, `> 0.40 → INFO`, `> 0.15 → WARNING`, `≤ 0.15 → CRITICAL`. `FAILED` events upgrade to CRITICAL. The LLM only relays the tag; we can show judges the exact line that decided CRITICAL.

**SDK choice** ([`11`](./docs/research/11-vercel-ai-sdk.md)): **Vercel AI SDK v6 + AI Gateway**. One key, hundreds of models, automatic provider failover for venue insurance. Primary `anthropic/claude-sonnet-4.6`, demo bump to `claude-opus-4.6` if latency allows, fallback chain `anthropic → openai/gpt-5.4 → google/gemini-3.1-pro`. `streamText` + `tool()` + `stopWhen: stepCountIs(8)` is the canonical multi-step loop; `onStepFinish` streams "thought → tool call → observation" to the UI as the visible "intelligence" the brief asks for. Cost ceiling for a 60-second demo: ~$0.12 on Sonnet, ~$0.60 on Opus. Not a constraint. **v5 patterns to avoid** (these will silently break a fresh AI SDK install): `maxSteps`, `parameters` (now `inputSchema`), `toDataStreamResponse` (now `toUIMessageStreamResponse`), `useChat`'s `input/handleSubmit/handleInputChange` (manage with `useState` + `sendMessage`), `addToolResult` (now `addToolOutput`).

**Proactive alerts** (Autonomy pillar, [`12`](./docs/research/12-proactive-alerts.md)): the sim writes `events` rows at status transitions, the React client polls `GET /api/alerts?since=<ts>` every 2 s, and new events surface as a Sonner toast plus a sticky banner. **We deliberately rejected SSE** despite Next.js App Router supporting it, because the stream lifecycle, heartbeat, and reconnect logic introduce a class of bugs we can't afford to debug at 03:00. Polling is one `fetch` and one `setState`, deterministic, replayable, citable. 2 s latency is invisible to judges. Every alert payload includes `evidence` so the chatbot quotes the same row when the operator follows up — alerts and chat share the same grounding contract.

**Voice** (Versatility pillar, [`13`](./docs/research/13-voice-interface.md)): **Web Speech API primary** — `SpeechRecognition` + `SpeechSynthesis`, free, browser-native, ~25 lines, demoable in <30 minutes on Chrome. The voice layer is purely an I/O wrapper around the existing `/api/chat`, so every spoken answer keeps its citation — the audience *hears* the citation. Stretch is **OpenAI `gpt-realtime` via WebRTC** for sub-second voice-to-voice with native tool calling, only built Sunday morning if Phase 2 is solid; one-click fallback button to Web Speech so the demo can't die. ElevenLabs skipped — premium voices don't move the rubric for our use case.

### Stack & topology — the simplest cross-language bridge that exists

Stack ([`14`](./docs/research/14-stack-and-topology.md)) is locked end-to-end. **Python sim, Next.js web, one SQLite file in between.**

| Layer | Choice | Why |
| :--- | :--- | :--- |
| Sim language | Python 3.12 + uv | numpy/pandas/simpy/sklearn — stronger than the JS ecosystem for the math + ML surrogate. Chris owns it. |
| Web | Next.js 15 App Router + bun | Server Components run `better-sqlite3` cleanly; bun is fast enough not to matter. |
| UI | shadcn/ui + Tailwind v4 + Recharts | Hackathon-fast, owns its source, no learning tax. |
| AI | Vercel AI SDK v6 + AI Gateway → Claude | One SDK, streaming, tool-calling, fallback. |
| Bridge | SQLite WAL, `data/historian.sqlite` | Python writes, Node reads via synchronous `better-sqlite3`. **No FastAPI shim.** WAL gives one-writer-many-readers without lock errors. |
| Deploy | Vercel for web, sim runs locally during demo | **Commit a seeded `historian.sqlite`** so a fresh clone (and Vercel's build) always have something to read. |

**Critical gotcha**: pin Node 22 in `package.json` `engines` — there's an open bug (`vercel/vercel#12040`) where `better-sqlite3` fails to register on Node 24 during Vercel build. **WAL pragmas required on both sides** — `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000` on the Python writer; `journal_mode=WAL`, `query_only=true` on the Node reader. This is what makes the writer-and-many-readers topology crash-free during the demo.

### Domain priors — the citation trail behind the parameter choices

[`15`](./docs/research/15-domain-priors.md): **HP Metal Jet S100** is binder-jet metal AM with **6 thermal inkjet printheads totalling 63,360 nozzles**, 1,200 dpi resolution, 35–140 µm layer thickness, 1,990 cc/hr build speed, build platform 430 × 309 × 200 mm. Materials: 316L and 17-4 PH (later Sandvik Osprey 316L, Indo-MIM M2 tool steel). Customers named at launch: VW, GKN, Cobra Golf, Schneider Electric, Parmatech, Domin, Lumenium. Announced 2018, launched IMTS Sept 2022.

Real-world references behind each formula: **recoater wear** = streaking + lack-of-fusion porosity from repeated part contact (*Inside Metal Additive Manufacturing*, Jan 2024). **Nozzle clogging** = four real mechanisms (size-exclusion, fouling, solvent drying, hydrodynamic bridging) on actual ~75 µm thermal inkjet nozzles (Waasdorp et al., *RSC Advances*, 2018). **Heating-element drift** = oxidation thins cross-section + thermal-cycle elongation → resistance ↑ → power ↓ by Ohm's law.

**NASA C-MAPSS** and **PHM Society** datasets are used **as a visual prior only** — the flat-then-knee-then-cliff curve shape with regime-switching jumps. We synthesise our own data; using turbofan signals as training would be a category error and we'd lose grounding marks for it.

### Submission plan

[`16`](./docs/research/16-submission-prep.md): six deliverables (repo, deck, report, demo, walkthrough video, optional Phase 3 bonus demo). Deadline placeholder Sun 2026-04-26 ~09:00 CEST — **action: confirm in Slack `C0AV9TTJT25` first hour of build day 2**.

**Deck** = 9 slides: Title · Mission · Phase 1 brain · Phase 1 cascade+surrogate · Phase 2 clock+historian · Phase 2 maintenance agent · Phase 3 chatbot · Phase 3 alerts+voice · Closing. **Report** = 8 sections mirroring the deck, cross-linked to research notes 01–12. **Demo (5 min)** = Daniel ~3 min (chatbot + voice + alert + citation jump), Chris ~2 min (math walk + sim chart + agent A/B), 30 s close. **Risk plan**: 6 contingencies pre-listed including canned `historian.sqlite`, typed fallback for voice, AI Gateway secondary, manual driver nudge to force CRITICAL, pre-rendered chart PNGs in the deck, Saturday-evening Loom safety-net video.

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

### C. Phase 3 — the grounded chatbot

- [x] **Pattern choice** → [`10-chatbot-architecture.md`](./docs/research/10-chatbot-architecture.md). Pattern C (Agentic ReAct); B and A as fallbacks from same code path.
- [x] **Tool design** → same doc 10. Five read-only tools: `query_health`, `get_failure_events`, `compare_runs`, `current_status`, `recommend_action`.
- [x] **AI SDK / Gateway** → [`11-vercel-ai-sdk.md`](./docs/research/11-vercel-ai-sdk.md). Vercel AI SDK v6 + AI Gateway; Sonnet 4.6 primary, Opus 4.6 demo, OpenAI/Gemini fallback.
- [x] **Citation enforcement** → doc 10. Zod schema + transcript-hash validator (defense in depth), 2-retry budget.
- [x] **Severity tagging** → doc 10. Tool-layer deterministic, reuses doc 04 thresholds.
- [x] **Proactive alerting (bonus)** → [`12-proactive-alerts.md`](./docs/research/12-proactive-alerts.md). Sim writes events; client polls every 2 s; Sonner toast + sticky banner.
- [x] **Voice interface (bonus)** → [`13-voice-interface.md`](./docs/research/13-voice-interface.md). Web Speech API primary, OpenAI `gpt-realtime` WebRTC stretch.
- [x] **Persistent memory (bonus)** → punted; alert acknowledgements are the cheapest path if time allows.

### D. Stack & repo skeleton

- [x] **Sim core language** → [`14-stack-and-topology.md`](./docs/research/14-stack-and-topology.md). Python 3.12 + uv.
- [x] **UI / chatbot stack** → same doc 14. Next.js 15 + bun + shadcn/ui + Tailwind v4 + Recharts + AI SDK v6.
- [x] **Topology** → same doc 14. Single `data/historian.sqlite` WAL. Python writes, Next.js reads via `better-sqlite3` readonly. **No FastAPI shim.**
- [x] **Deploy target** → same doc 14. Web on Vercel; sim local; commit seeded `historian.sqlite`. Pin Node 22.
- [x] **Repo skeleton** → same doc 14. Top-level `Makefile` with `make dev` (parallel) and `make seed`.

### E. Domain priors

- [x] **HP Metal Jet S100** → [`15-domain-priors.md`](./docs/research/15-domain-priors.md). 6 printheads · 63,360 nozzles · 1,200 dpi · 316L/17-4 PH · launched IMTS 2022.
- [x] **Wear / clog / drift references** → same doc 15. Inside Metal AM 2024, Waasdorp et al. RSC 2018, oxidation+elongation chain.
- [x] **NASA C-MAPSS / PHM Society** → same doc 15. Visual shape prior only — flat → knee → cliff. Not training data.

### F. Submission-side prep

- [x] **Submission deadline / format** → [`16-submission-prep.md`](./docs/research/16-submission-prep.md). Placeholder Sun 09:00 CEST; **confirm in Slack first hour of day 2**.
- [x] **Slide deck outline** → same doc 16. 9 slides.
- [x] **Technical report outline** → same doc 16. 8 sections.
- [x] **Demo split** → same doc 16. Daniel ~3 min, Chris ~2 min; 6 contingencies.

---

## Repo layout (target)

```
.
├── sim/              # Phase 1 + Phase 2 — Python, owns the historian
│   ├── pyproject.toml
│   ├── engine/      # Phase 1 — pure formulas
│   ├── loop/        # Phase 2 — clock + writer
│   ├── scenarios/   # YAML driver profiles
│   └── tests/
├── web/              # Phase 3 — Next.js, dashboard + grounded chatbot
├── data/             # historian.sqlite (committed seed), scenario configs
├── docs/
│   ├── briefing/     # HP-provided source material
│   ├── research/     # locked pre-build decisions (16 docs)
│   └── report/       # our technical report + slide deck source
├── scripts/          # one-shot CLI for runs, exports, fixtures
└── Makefile          # `make dev`, `make seed`
```

---

## Next steps

1. Scaffold `sim/` with uv + the historian schema from [doc 08](./docs/research/08-historian-schema.md).
2. Implement Phase 1 components in this order: blade ([01](./docs/research/01-recoater-blade-archard.md)) → heater ([03](./docs/research/03-heating-elements-arrhenius.md)) → nozzle ([02](./docs/research/02-nozzle-plate-coffin-manson.md)) — easiest first.
3. Wrap in Phase 2 loop ([06](./docs/research/06-driver-profiles-and-time.md)), commit a seed `historian.sqlite`.
4. Scaffold `web/` and wire the five tools ([10](./docs/research/10-chatbot-architecture.md)) over the historian.
5. Layer in proactive alerts ([12](./docs/research/12-proactive-alerts.md)) and voice ([13](./docs/research/13-voice-interface.md)) on Sunday once the core works.
