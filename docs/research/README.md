# Pre-build research

Decision documents produced before writing any sim or web code. Each file picks one path and locks parameters, so Phase 1–3 implementation can start without re-litigating choices.

Source briefs: [`../briefing/`](../briefing/). Canonical context: [`../../TRACK-CONTEXT.md`](../../TRACK-CONTEXT.md).

## Index

### Phase 1 — the brain (math models)

| # | Topic | Decision |
| :- | :--- | :--- |
| 01 | [Recoater Blade — Archard wear](./01-recoater-blade-archard.md) | Linear `Δh = k_eff·P·s_eff·dt/H_eff`; thresholds at 20/40/50 % thickness loss |
| 02 | [Nozzle Plate — Coffin-Manson + clog hazard](./02-nozzle-plate-coffin-manson.md) | Composite `H = (1−clog%/100)·(1−D)`; Palmgren-Miner accumulation |
| 03 | [Heating Elements — Arrhenius drift](./03-heating-elements-arrhenius.md) | Acceleration-factor form, `E_a = 0.7 eV`, fail at +10 % drift |
| 04 | [Aging baselines + Health normalization](./04-aging-baselines-and-normalization.md) | Weibull per component, multiplicative composition, status thresholds 0.75 / 0.40 / 0.15 |
| 05 | [Cascade + AI-driven degradation (bonus)](./05-cascading-and-ai-degradation.md) | Blade→Nozzle contamination cascade; sklearn `MLPRegressor` surrogate for heater |

### Phase 2 — the clock + the historian

| # | Topic | Decision |
| :- | :--- | :--- |
| 06 | [Driver profiles + time + chaos](./06-driver-profiles-and-time.md) | Sin / OU / monotonic / step; `dt = 1 h`, 4380 ticks; Poisson chaos overlay |
| 07 | [Live weather API](./07-weather-api.md) | Open-Meteo Archive API (no auth); cached JSON for demo robustness |
| 08 | [Historian schema](./08-historian-schema.md) | SQLite WAL; long-form normalised tables (`runs`, `drivers`, `component_state`, `metrics`, `events`) |
| 09 | [AI Maintenance Agent (bonus)](./09-maintenance-agent.md) | Heuristic primary; LLM-as-policy stretch; full Gymnasium env spec on standby |

### Phase 3 — the voice (grounded chatbot)

| # | Topic | Decision |
| :- | :--- | :--- |
| 10 | [Chatbot architecture](./10-chatbot-architecture.md) | Pattern C (Agentic ReAct); 5 read-only tools; Zod-constrained citations + transcript-hash validator |
| 11 | [Vercel AI SDK v6 + Gateway](./11-vercel-ai-sdk.md) | AI SDK v6, Gateway with multi-provider fallback, Sonnet 4.6 primary / Opus 4.6 demo |
| 12 | [Proactive alerts](./12-proactive-alerts.md) | Sim writes `events` table; client polls `/api/alerts?since=` every 2 s; Sonner toast + sticky banner |
| 13 | [Voice interface](./13-voice-interface.md) | Web Speech API primary; OpenAI `gpt-realtime` (WebRTC) stretch |

### Stack, domain, submission

| # | Topic | Decision |
| :- | :--- | :--- |
| 14 | [Stack + topology](./14-stack-and-topology.md) | Python sim writes `data/historian.sqlite`; Next.js reads via `better-sqlite3`; deploy to Vercel |
| 15 | [Domain priors](./15-domain-priors.md) | HP S100 specs (63,360 nozzles, 1,200 dpi, 316L); citation trail per component; C-MAPSS as visual prior only |
| 16 | [Submission prep](./16-submission-prep.md) | 9-slide deck, 8-section report, 5-min demo split (Daniel ~3 min / Chris ~2 min) |

## Reading order

Read **04** before any other Phase 1 doc — it sets the status thresholds and composition rule that 01/02/03 depend on.

For the chatbot work, read **08** (schema) → **10** (architecture) → **11** (SDK) → **12** (alerts) → **13** (voice) in that order.

For the deck/report, **15** (domain priors) and **16** (submission prep) are the source material.

## How these were produced

One focused research agent per decision, run in parallel on 2026-04-25, each grounded in current docs and papers (no training-data citations). Cross-references between docs were validated by hand after the fact (e.g. doc 09 closes an open question from doc 04).
