# hackUPC

HackUPC hackathon project.

## TODO

Pre-kickoff exploration. Tick these off before we start building.

### Context & briefing

- [ ] Pull all track context dropped in the [Slack channel](https://app.slack.com/client/T0APCMG2G1Z/C0AV9TTJT25) and commit it to this repo (briefing markdowns, slides, scoring criteria, examples).
- [ ] Fold any new info into [`TRACK-CONTEXT.md`](./TRACK-CONTEXT.md) and update the open-questions list.
- [ ] Confirm submission format, deadline, and judging criteria.

### Research — digital twin frameworks & libraries

- [ ] Survey existing **digital twin frameworks / libraries** for implementation reference (models, algorithms, functions we can reuse).
  - Candidates to evaluate: Eclipse Ditto, Microsoft Azure Digital Twins SDK, NVIDIA Omniverse, Modelica/OpenModelica, FMI/FMU, Asset Administration Shell (AAS), Eclipse BaSyx, PySDF/SimPy, twinify.
  - For each: license, language, scope (geometric vs behavioural), what we can lift vs what's overkill.
- [ ] Survey **AI-supported digital twin** repos / papers / frameworks.
  - How are they wiring AI in? (surrogate models, anomaly detection, RUL prediction, RL controllers, LLM agents on top.)
  - What problem is the AI actually solving in each? (replace expensive sim, predict failure, recommend action, natural-language UX.)
  - Which patterns map cleanly onto our 3D-printer-degradation scope?

### Research — domain (3D printer degradation)

- [ ] Identify which printer components are most interesting to model first (motor, hotend, belts, fans, bearings, nozzle, build plate, extruder, etc.) and the wear drivers per part.
- [ ] Find **public degradation / RUL datasets** we can borrow shapes from (NASA C-MAPSS, PHM Society challenges, bearing datasets) — even if we generate our own, real curves are good priors.
- [ ] Find published wear/degradation equations per component class (Arrhenius for thermal aging, Coffin-Manson for cyclic fatigue, Paris' law for crack growth, motor brush wear models, etc.).
- [ ] Look up which **environment variables actually matter** (temp, humidity, vibration, dust, duty cycle, ambient pressure) and where to source them via API (Open-Meteo, OpenWeather, etc.).

### Research — UX / agent layer

- [ ] Look at **grounded chatbot** patterns over time-series data (RAG over tabular/TS, tool-calling agents, MCP servers, function-calling on a metrics API).
- [ ] Look at **predictive / proactive UX** patterns: alerting, what-if sliders, recommendation cards, copilot panels.
- [ ] Pick a dashboard stack candidate (Next.js + Recharts/visx, Streamlit, Grafana, Plotly Dash, Observable Framework) and decide based on what plays best with our chatbot.

### Stack & scaffolding decisions

- [ ] Decide language for the simulation core (Python for AI/data ergonomics, or TS/Node for tight web integration).
- [ ] Decide where the simulation runs (in-process, separate service, edge function, scheduled cron).
- [ ] Decide data store for generated time series (SQLite, DuckDB, Postgres/Timescale, Parquet on disk).
- [ ] Decide AI provider strategy (Vercel AI Gateway with model routing vs single provider).
- [ ] Set up the repo skeleton once decisions are locked.

### Team & ops

- [ ] Split work between Daniel and Chris based on stage interest (data/AI heavy vs UX heavy).
- [ ] Agree on a working cadence (commit often, push often, small PRs).
- [ ] Pin the `#hp` Slack channel and surface any judge clarifications back into `TRACK-CONTEXT.md`.
