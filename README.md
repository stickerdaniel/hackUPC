# hackUPC — When AI meets reality

Digital Co-Pilot for the **HP Metal Jet S100**. Models component degradation, simulates the printer forward in time, and exposes a grounded natural-language interface over the resulting telemetry.

Full briefing: [`TRACK-CONTEXT.md`](./TRACK-CONTEXT.md). Source docs: [`docs/briefing/`](./docs/briefing/).

---

## Pre-build research checklist

We are research-blocked, not implementation-blocked. Tick these off **before** writing the simulator. Each item is targeted at a specific decision we have to make.

### A. Phase 1 — picking the right failure math

We need ≥2 distinct mathematical failure models across our 3 mandatory components. Decide which formula maps to which component, with a one-line justification per choice.

- [ ] **Recoater Blade — Abrasive Wear:** read up on **Archard's wear law** (`V = k · F · s / H`). Decide our state metric (blade thickness in mm) and how Humidity/Contamination scales `k`.
- [ ] **Nozzle Plate — Clogging + Thermal Fatigue:** review **Coffin-Manson** (low-cycle thermal fatigue) for the fatigue side and a Poisson / hazard-rate model for the clog side. Decide whether clog probability per tick rises with `|temp_stress - optimal|`.
- [ ] **Heating Elements — Electrical Degradation:** review the **Arrhenius equation** (`rate ∝ exp(-Ea/kT)`) for thermally-accelerated aging, plus a simple resistance-drift model. Decide our state metric (resistance Ω vs. baseline).
- [ ] **Universal aging baselines:** confirm we understand **Exponential Decay** (`H(t) = e^-λt`) and the **Weibull reliability function** (`R(t) = exp(-(t/η)^β)`); pick whichever fits each component as the "background aging" term layered under the driver-specific stressor.
- [ ] **Health-index normalisation:** decide the policy for converting a raw metric (mm, Ω, %) to `[0,1]` health and to the four-state enum `FUNCTIONAL / DEGRADED / CRITICAL / FAILED`. Pick thresholds (e.g. `>0.75` functional, `>0.4` degraded, `>0.1` critical, else failed) and document why.
- [ ] **Cross-component coupling (bonus):** identify *one* cascading link we can defend (e.g. blade health < 0.3 → contamination driver +X% → nozzle clog rate ↑). One link is enough; don't over-engineer.
- [ ] **AI-degradation option (bonus):** decide whether one component's `f(...)` is a tiny learned regressor (sklearn / scikit-learn / a small NN) trained on synthetic data we generate from the analytic formula — gives us "AI inside the model" with zero data-collection overhead.

### B. Phase 2 — driver generation, time, and persistence

- [ ] **Driver-profile generators:** look at standard patterns for synthetic time-series drivers — sinusoidal day/night cycles for temperature, Ornstein–Uhlenbeck for humidity drift, Poisson spikes for contamination events. Pick the simplest per driver.
- [ ] **Live weather API as bonus driver:** evaluate **Open-Meteo** (free, no auth) vs. **OpenWeather** (free tier). Decide whether we wire one in for the demo's "Barcelona vs. Phoenix" what-if.
- [ ] **Time step + horizon:** pick `dt` (1 sim-minute? 1 sim-hour?) and total simulated horizon (weeks? months?) so the time-series chart shows visible failures within a 60-second demo run. Run a back-of-envelope: at `dt=1h` over 6 months that's ~4400 ticks — fine.
- [ ] **Historian schema:** decide on **SQLite** (queryable, demoable) vs. Parquet/CSV (simpler). Lock the schema: `(run_id, ts, component, health, status, metric_name, metric_value, driver_temp, driver_humidity, driver_load, driver_maint)`.
- [ ] **Run/scenario identity:** pick a `run_id` strategy so we can demo "same printer, different climates" side-by-side from one DB.
- [ ] **Stochastic mode (bonus):** read up on simple chaos injection (random spike events, noise on drivers) — this is a Phase 2 bonus and cheap if we plan it now.
- [ ] **AI Maintenance Agent (bonus):** sketch the simplest possible policy agent — observation = current health vector, action = `{do_nothing, run_maintenance}`, reward = uptime. Decide between hand-coded heuristic, LLM-as-policy, or a tiny RL loop with `gymnasium`. Heuristic is probably the right call given hackathon time.

### C. Phase 3 — the grounded chatbot (where we win)

This is our differentiator. Spend the most research budget here.

- [ ] **Pattern choice:** confirm we're targeting **C: Agentic Diagnosis** with a fallback to **B: Contextual RAG**. A is a baseline we get for free.
- [ ] **Tool design:** draft the tool schema the LLM will call against the historian. Likely:
  - `query_health(component, time_range, run_id?)` → rows
  - `get_failure_events(run_id?, severity?)` → events with timestamps
  - `compare_runs(run_a, run_b, component?)` → delta summary
  - `current_status(component?)` → latest snapshot
  - `recommend_action(component)` → policy lookup
- [ ] **AI SDK / Gateway:** evaluate **Vercel AI SDK v6 + AI Gateway** for tool-calling + provider routing vs. direct Anthropic SDK. Gateway gives us multi-provider fallback for free.
- [ ] **Citation enforcement:** research how teams force citations in tool-calling agents (structured output schemas, post-processing validators, system-prompt contracts that reject uncited claims). Pick one approach.
- [ ] **Severity tagging:** decide if `INFO/WARNING/CRITICAL` is computed in the tool layer (deterministic from health thresholds) or asked of the LLM (riskier). Tool layer is safer.
- [ ] **Proactive alerting (bonus pillar — Autonomy):** research the simplest pattern — a poller that watches the historian and pushes WebSocket / SSE alerts when any component crosses `CRITICAL`. Decide stack (Next.js route handler + SSE? Vercel Cron? local interval?).
- [ ] **Voice interface (bonus pillar — Versatility):** evaluate **OpenAI Realtime** vs. **ElevenLabs Conversational** vs. browser **Web Speech API + TTS**. Web Speech is free and fastest to demo; Realtime is the "wow" path. Pick one target, one fallback.
- [ ] **Persistent memory (bonus pillar — Autonomy):** decide whether we layer per-session conversation memory or skip it. Probably skip unless time allows.

### D. Stack & repo skeleton decisions

- [ ] **Sim core language:** Python (numpy/pandas/simpy ergonomics, easy ML hooks) vs. TypeScript (one-language repo). **Lean Python.**
- [ ] **UI / chatbot stack:** Next.js App Router on Vercel, AI SDK v6, Recharts or visx for time-series, shadcn/ui for components.
- [ ] **Topology:** monorepo with `sim/` (Python) writing to `data/historian.sqlite`, `web/` (Next.js) reading via a thin Python FastAPI shim *or* a TS-side `better-sqlite3` reader. Decide which avoids cross-language friction.
- [ ] **Deploy target:** Vercel for the web app; sim runs locally or on a Vercel Sandbox / Function. Decide if we need any of that for the demo or if local-only is fine.
- [ ] **Repo skeleton:** lock folder structure (`sim/`, `web/`, `docs/`, `scripts/`) and one-command bootstrap (`make dev` or `bun run dev`).

### E. Domain priors (read once, reference often)

- [ ] Skim the **HP Metal Jet S100** product page and binder-jetting overview so the slide deck and chatbot answers don't sound naive.
- [ ] Look up one or two real **recoater blade wear** / **inkjet nozzle clogging** / **heating element resistance drift** references — even one paragraph each — so our parameter choices have a citation trail.
- [ ] Check **NASA C-MAPSS** and **PHM Society challenge** datasets *only as shape priors* for what realistic degradation curves look like. We don't train on them; we just want to mimic the visual feel.

### F. Submission-side prep (do early, not last)

- [ ] Confirm submission deadline, format, and judging slot from the Slack channel; add to TRACK-CONTEXT.md.
- [ ] Outline the architecture slide deck headings now (3 phases × 2 slides + a closing "what we'd do next").
- [ ] Outline the technical report headings now (mirror the deck).
- [ ] Decide who demos what (Daniel: UX/chatbot/voice. Chris: model + sim + historian).

---

## Repo layout (target)

```
.
├── sim/              # Phase 1 + Phase 2 — Python, owns the historian
├── web/              # Phase 3 — Next.js, dashboard + grounded chatbot
├── data/             # historian.sqlite, scenario configs
├── docs/
│   ├── briefing/     # HP-provided source material
│   └── report/       # our technical report + slide deck source
└── scripts/          # one-shot CLI for runs, exports, fixtures
```

---

## Status

Pre-build. Briefing is ingested ([`TRACK-CONTEXT.md`](./TRACK-CONTEXT.md)). No code yet.
