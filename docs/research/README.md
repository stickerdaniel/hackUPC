# Pre-build research

Decision documents produced before writing any sim code. Each file picks one path and locks parameters, so Phase 1 + Phase 2 implementation can start without re-litigating choices.

Source briefs: [`../briefing/`](../briefing/). Canonical context: [`../../TRACK-CONTEXT.md`](../../TRACK-CONTEXT.md).

> **Build scope: Phase 1 + Phase 2 only.** Docs **10–13** (chatbot architecture, AI SDK, proactive alerts, voice) are **preserved but deferred**; the Phase-3 portions of docs 14 and 16 likewise. They are not part of the current build.

## Index

### Phase 1 — the brain (math models) — IN SCOPE

| # | Topic | Decision |
| :- | :--- | :--- |
| 01 | [Recoater Blade — Archard wear](./01-recoater-blade-archard.md) | Linear `Δh = k_eff·P·s_eff·dt/H`; thresholds at 20 / 40 / 50 % thickness loss |
| 02 | [Nozzle Plate — Coffin-Manson + clog hazard](./02-nozzle-plate-coffin-manson.md) | Composite `H = (1−clog%/100)·(1−D)`; Palmgren-Miner accumulation |
| 03 | [Heating Elements — Arrhenius drift](./03-heating-elements-arrhenius.md) | Acceleration-factor form, `E_a = 0.7 eV`, fail at +10 % drift |
| 04 | [Aging baselines + Health normalization](./04-aging-baselines-and-normalization.md) | Weibull per component, multiplicative composition, status thresholds 0.75 / 0.40 / 0.15 |
| 05 | [Cascade + AI-driven degradation (bonus)](./05-cascading-and-ai-degradation.md) | Blade→Nozzle contamination cascade; sklearn `MLPRegressor` surrogate for heater |

### Phase 2 — the clock + the historian — IN SCOPE

| # | Topic | Decision |
| :- | :--- | :--- |
| 06 | [Driver profiles + time + chaos](./06-driver-profiles-and-time.md) | Sin / OU / monotonic / step; `dt = 1 h`, 4380 ticks; Poisson chaos overlay |
| 07 | [Live weather API](./07-weather-api.md) | Open-Meteo Archive API (no auth); cached JSON for demo robustness |
| 08 | [Historian schema](./08-historian-schema.md) | SQLite WAL; long-form normalised tables (`runs`, `drivers`, `component_state`, `metrics`, `events`) |
| 09 | [AI Maintenance Agent (bonus)](./09-maintenance-agent.md) | Heuristic primary; LLM-as-policy stretch; full Gymnasium env spec on standby |

### Phase 3 — the voice (grounded chatbot) — DEFERRED

These docs were written but the work is **not** part of the current build. Preserved for future work.

| # | Topic | Decision |
| :- | :--- | :--- |
| 10 | [Chatbot architecture](./10-chatbot-architecture.md) *(deferred)* | Pattern C (Agentic ReAct); 5 read-only tools; Zod + transcript-hash citation validator |
| 11 | [Vercel AI SDK v6 + Gateway](./11-vercel-ai-sdk.md) *(deferred)* | AI SDK v6, Gateway with multi-provider fallback, Sonnet 4.6 primary / Opus 4.6 demo |
| 12 | [Proactive alerts](./12-proactive-alerts.md) *(deferred)* | Sim writes `events` table; client polls `/api/alerts?since=` every 2 s |
| 13 | [Voice interface](./13-voice-interface.md) *(deferred)* | Web Speech API primary; OpenAI `gpt-realtime` (WebRTC) stretch |

### Stack, domain, submission

| # | Topic | Decision |
| :- | :--- | :--- |
| 14 | [Stack + topology](./14-stack-and-topology.md) | **Sim-only path**: Python 3.12 + uv + SQLite WAL. Streamlit dashboard. The Next.js / better-sqlite3 / AI SDK web stack inside this doc is **deferred** along with Phase 3. |
| 15 | [Domain priors](./15-domain-priors.md) | HP S100 specs (63,360 nozzles, 1,200 dpi, 316L); citation trail per component; C-MAPSS as visual prior only |
| 16 | [Submission prep](./16-submission-prep.md) | 9-slide deck (drop slides 7–8 chatbot/voice; replace with future work); 8-section report (omit Phase 3); 5-min demo split rewritten in root README |

## Reading order

Read **04** before any other Phase 1 doc — it sets the status thresholds and composition rule that 01/02/03 depend on.

For the Phase 2 build: **08** (schema) → **06** (drivers + time + chaos) → **07** (weather adapter) → **09** (maintenance agent).

For the deck/report, **15** (domain priors) and **16** (submission prep) are the source material — modulo the Phase 3 sections of 16, which are out of scope for now.

## How these were produced

One focused research agent per decision, run in parallel on 2026-04-25, each grounded in current docs and papers (no training-data citations). Cross-references between docs were validated by hand after the fact (e.g. doc 09 closes an open question from doc 04). The sim-only refocus happened later the same day; the docs themselves were not rewritten when scope narrowed.
