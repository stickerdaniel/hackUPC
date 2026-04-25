# hackUPC — When AI meets reality

Digital Co-Pilot for the **HP Metal Jet S100**. Models component degradation, simulates the printer forward in time, and exposes a grounded natural-language interface over the resulting telemetry.

Full briefing: [`TRACK-CONTEXT.md`](./TRACK-CONTEXT.md). Source docs: [`docs/briefing/`](./docs/briefing/). Decision docs: [`docs/research/`](./docs/research/).

---

## Status

**Research complete — ready to build.** All 16 pre-build decisions are locked. See [`docs/research/`](./docs/research/) for the full set; each links its sources.

---

## Pre-build research checklist

Each item links to a decision document under [`docs/research/`](./docs/research/). All locked on 2026-04-25.

### A. Phase 1 — picking the right failure math

- [x] **Recoater Blade — Abrasive Wear** → [`01-recoater-blade-archard.md`](./docs/research/01-recoater-blade-archard.md). Linear `Δh = k_eff · P · s_eff · dt / H_eff`; `k0 = 5e-5`, contamination scales `k` by `(1 + 1.5·C)`; FAILED at ≥50 % thickness loss (~6 months nominal).
- [x] **Nozzle Plate — Clogging + Thermal Fatigue** → [`02-nozzle-plate-coffin-manson.md`](./docs/research/02-nozzle-plate-coffin-manson.md). Coffin-Manson with Palmgren-Miner accumulation + Poisson clog hazard `λ(t) = λ_0·(1+α|ΔT|)·(1+β·C)/M`; composite `H = (1−clog%/100)·(1−D)`.
- [x] **Heating Elements — Electrical Degradation** → [`03-heating-elements-arrhenius.md`](./docs/research/03-heating-elements-arrhenius.md). Arrhenius acceleration-factor form, `E_a = 0.7 eV`; resistance drift compounded per tick; FAILED at +10 % drift.
- [x] **Universal aging baselines** → [`04-aging-baselines-and-normalization.md`](./docs/research/04-aging-baselines-and-normalization.md). All Weibull (β=2.5/η=180d blade, β=2.0/η=150d nozzle, β=1.0/η=240d heater); multiplicative composition `H = H_base · H_driver`.
- [x] **Health-index normalisation** → same doc 04. Thresholds revised to `>0.75` FUNCTIONAL, `>0.40` DEGRADED, `>0.15` CRITICAL, else FAILED (raised the critical floor from 0.10 to give the alert agent a useful warning window).
- [x] **Cross-component coupling (bonus)** → [`05-cascading-and-ai-degradation.md`](./docs/research/05-cascading-and-ai-degradation.md). One-way Blade → Nozzle: `C_nozzle_eff = clamp(C_input + 0.5 · blade.loss_frac, 0, 1)`. Heater → multi-component cascade kept as alternative.
- [x] **AI-degradation option (bonus)** → same doc 05. Replace the heater formula with sklearn `MLPRegressor` `(32,32,32)` trained on 20k Latin-Hypercube samples; acceptance gate MAE ≤ 2 %.

### B. Phase 2 — driver generation, time, and persistence

- [x] **Driver-profile generators** → [`06-driver-profiles-and-time.md`](./docs/research/06-driver-profiles-and-time.md). Sinusoidal day+season for Temp; Ornstein-Uhlenbeck (Euler-Maruyama) for Humidity; monotonic + duty-cycle for Load; step function for Maintenance.
- [x] **Live weather API** → [`07-weather-api.md`](./docs/research/07-weather-api.md). **Open-Meteo Archive API** (no auth, 10k calls/day, single GET returns 6 months hourly). OpenWeather rejected (1 timestamp per call). Cache JSON in repo for demo.
- [x] **Time step + horizon** → doc 06. `dt = 1 h`, **4380 ticks** for 6 sim-months; configurable to `dt = 6 h` fast-forward demo mode.
- [x] **Historian schema** → [`08-historian-schema.md`](./docs/research/08-historian-schema.md). SQLite WAL; long-form normalised tables: `runs`, `drivers`, `component_state`, `metrics`, `events`. All time-series tables `WITHOUT ROWID`.
- [x] **Run/scenario identity** → same doc 08. Format `{scenario}-{profile}-{YYYYMMDD}-{seq}`, e.g. `barcelona-baseline-20260425-1`.
- [x] **Stochastic mode (bonus)** → doc 06. Poisson temp spikes (λ=2/month, ΔT~N(8,2)), contamination bursts (λ=3/month), Bernoulli skipped maintenance (p=0.1). All seeded from one config field.
- [x] **AI Maintenance Agent (bonus)** → [`09-maintenance-agent.md`](./docs/research/09-maintenance-agent.md). Primary = heuristic (`min(H) < 0.4` triggers); stretch = LLM-as-policy with stored rationale. Full Gymnasium env spec on standby.

### C. Phase 3 — the grounded chatbot (where we win)

- [x] **Pattern choice** → [`10-chatbot-architecture.md`](./docs/research/10-chatbot-architecture.md). Pattern C (Agentic ReAct) is the target; B and A emerge from the same tool set as graceful fallbacks.
- [x] **Tool design** → same doc 10. Five read-only tools — `query_health`, `get_failure_events`, `compare_runs`, `current_status`, `recommend_action`. Each returns rows shaped as evidence with severity baked in.
- [x] **AI SDK / Gateway** → [`11-vercel-ai-sdk.md`](./docs/research/11-vercel-ai-sdk.md). Vercel AI SDK v6 + AI Gateway. Primary `anthropic/claude-sonnet-4.6`, demo bump `claude-opus-4.6`, fallback chain via `providerOptions.gateway.order`.
- [x] **Citation enforcement** → doc 10. Defense in depth: Zod-constrained final output (every assertion needs `≥1` evidence row) + transcript-hash validator that rejects any cited tuple not in the tool transcript. 2-retry budget.
- [x] **Severity tagging** → doc 10. **Tool-layer deterministic** mapping reused from doc 04 thresholds. LLM never invents severity.
- [x] **Proactive alerting (bonus)** → [`12-proactive-alerts.md`](./docs/research/12-proactive-alerts.md). Sim writes to `events` table at threshold crossings; client polls `/api/alerts?since=<ts>` every 2 s; Sonner toast + sticky banner.
- [x] **Voice interface (bonus)** → [`13-voice-interface.md`](./docs/research/13-voice-interface.md). **Web Speech API** primary (free, ~25 lines, demo-ready), **OpenAI `gpt-realtime`** WebRTC stretch.
- [x] **Persistent memory (bonus)** → punted (see open questions in doc 10). Skipping unless time allows; alert acknowledgements are the cheapest path to a "Collaborative Memory" pillar point if we get there.

### D. Stack & repo skeleton decisions

- [x] **Sim core language** → [`14-stack-and-topology.md`](./docs/research/14-stack-and-topology.md). **Python 3.12 + uv**; numpy/pandas/simpy/sklearn/pydantic.
- [x] **UI / chatbot stack** → same doc 14. Next.js 15 App Router on Vercel + bun + shadcn/ui + Tailwind v4 + Recharts + Vercel AI SDK v6.
- [x] **Topology** → same doc 14. Single `data/historian.sqlite` in WAL mode. Python writes, Next.js reads via `better-sqlite3` opened readonly. **No FastAPI shim.**
- [x] **Deploy target** → same doc 14. Web on Vercel; sim local during demo; commit a seeded `historian.sqlite` so a fresh clone is never empty. Pin Node 22 (better-sqlite3 fails on Node 24).
- [x] **Repo skeleton** → same doc 14. Top-level `Makefile` with `make dev` (parallel sim + web) and `make seed`.

### E. Domain priors

- [x] **HP Metal Jet S100** → [`15-domain-priors.md`](./docs/research/15-domain-priors.md). 6 thermal inkjet printheads · 63,360 nozzles · 1,200 dpi · 316L/17-4 PH · customers Volkswagen, GKN, Cobra Golf, Schneider Electric.
- [x] **Wear / clog / drift references** → same doc 15. Recoater (Inside Metal AM 2024), nozzle (Waasdorp et al. RSC 2018, real ~75 µm thermal-inkjet mechanisms), heater drift (oxidation + thermal-cycle elongation).
- [x] **NASA C-MAPSS / PHM Society** → same doc 15. Visual shape prior only — flat → knee → cliff curve, multi-mode regime jumps. Not training data.

### F. Submission-side prep

- [x] **Submission deadline / format** → [`16-submission-prep.md`](./docs/research/16-submission-prep.md). Placeholder Sun 2026-04-26 ~09:00 CEST freeze; **action: verify in Slack `C0AV9TTJT25` first hour of day 2**.
- [x] **Slide deck outline** → same doc 16. 9 slides (Title + Mission + 3 phases × 2 slides + Closing).
- [x] **Technical report outline** → same doc 16. 8 sections mirroring the deck, cross-linked to research notes 01–12.
- [x] **Demo split** → same doc 16. 5-min slot: Daniel ~3 min (chatbot + voice + alert), Chris ~2 min (math walk + sim chart + agent A/B). 6 contingencies pre-listed.

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
