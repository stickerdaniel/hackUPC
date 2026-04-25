# 16 — Submission Prep: Deadline, Deck, Report, Demo Split

## TL;DR

HackUPC closes Sunday 2026-04-26; **lock submission by Sun 09:00 CEST** (placeholder — confirm in Slack `C0AV9TTJT25`). Six deliverables: GitHub repo, slide deck, technical report, walkthrough video, live demo, optional Phase 3 bonus demo. Build artefacts now: a 9-slide deck mirrored by an 8-section report, a 5-minute demo split (Daniel ~3 min app/chatbot/voice, Chris ~2 min math/sim/agent), and 5 contingencies (canned historian, typed fallback, AI Gateway secondary, screen-recorded video, pre-rendered chart PNGs).

## Submission deadline & format

- **Deliverables (TRACK-CONTEXT.md §6):** working demo (P1+P2 min, P3 bonus), architecture slide deck, technical report, P3 bonus demo if shipped, GitHub repo with README, walkthrough video or live demo.
- **Deadline:** *placeholder* — Sun 2026-04-26, ~09:00 CEST hard freeze, judging windows 10:00–13:00. Confirm in Slack workspace `T0APCMG2G1Z`, channel `C0AV9TTJT25`.
- **Format expected:** GitHub URL + uploaded PDF deck + uploaded report (md or PDF) + video link (YouTube unlisted or Drive). Live demo at judging table.
- **Action item:** within first hour of build day 2, confirm exact deadline timestamp, judging slot start, and submission portal URL from Slack; pin reply to team.

> **Scope reminder (2026-04-25):** sim-only build. Phase 3 (chatbot/voice/frontend) deferred — slides 7–8 from the original outline are dropped and replaced with a sensor-fault-vs-component-fault story made possible by §3.4. Demo is sim + Streamlit dashboard.

## Slide deck outline (sim-only, 9 slides)

1. **Title — "When AI Meets Reality: a Digital Twin for the HP Metal Jet S100"** — team (Daniel + Chris + Jana + Leonie + criisshg), mentor (Nathan), one-liner: "A coupled digital twin where every failure tells a story."
2. **The mission** — 3-line problem (printer fails unpredictably, sensors lie too, operators run blind); the sim-only architecture diagram (Logic Engine → Coupled Loop + Historian → Streamlit dashboard).
3. **Phase 1 — The brain (six components)** — three subsystems × two components, each with its own textbook law: Archard (blade) + Weibull (rail), Coffin-Manson + Poisson clog (nozzle) + power-law-per-cycle wiper wear (cleaning), Arrhenius drift (heater) + Arrhenius bias drift (sensor). Multiplicative composition under shared Weibull baseline. Status thresholds 0.75 / 0.40 / 0.15.
4. **Phase 1 — Coupled engine + cascading failures + AI surrogate** — `Engine.step()` reads immutable `t-1` `PrinterState`, builds one `CouplingContext` (4 effective drivers + named `factors` dict), updates all 6 components from same snapshot. Three two-way loops (rail↔blade, cleaning↔nozzle, sensor↔heater) + two cross-subsystem cascades (powder→jetting, thermal→everything). Heater also runs as MLPRegressor surrogate trained on the analytic formula — "two lines that overlap perfectly".
5. **Phase 2 — The clock + the historian** — tick loop, SQLite WAL schema (runs · drivers · component_state · metrics · observed_component_state · observed_metrics · events), live weather driver (Open-Meteo Barcelona vs Phoenix), stochastic chaos overlay, time-series chart with at least one component reaching FAILED.
6. **Phase 2 — Sensors lie too (§3.4 observability split)** — true vs observed state; sensor `bias_C` accumulates Arrhenius-fast and propagates to the heater controller, which over-corrects, accelerating heater drift, accelerating sensor drift — a closed thermal loop. The dashboard shows true-vs-observed health side by side; the LLM-as-policy maintenance agent reads only observed and chooses TROUBLESHOOT vs FIX vs REPLACE accordingly.
7. **Phase 2 — AI Maintenance Agent A/B** — same seed, three policies (no-agent / heuristic / LLM-as-policy), `min(component_health)` over 180 days, maintenance triangles + FAILED ✗ markers. KPIs: uptime %, # events, # failures.
8. **What-if scenarios** — Barcelona vs Phoenix on the same printer; chaos on/off on the same seed; cascade on/off. Different physics dominate per climate (Phoenix → heater first; Barcelona → blade + nozzle first).
9. **Closing — what we'd do next** — Phase 3 grounded chatbot (research preserved in docs/research/10-13), digital twin sync from real telemetry, RL maintenance policy across thousands of episodes, multi-machine fleet view.

## Technical report outline (sim-only, 8 sections)

1. **Executive summary** — one paragraph: what we built (six-component coupled discrete-time twin with §3.4 observability split, AI-surrogate heater, AI-driven maintenance agent), why it's defensible, what's novel.
2. **Problem & approach** — restate the brief; map our work to Phase 1+2 evaluation pillars (Rigor · Systemic Interaction · Realism & Fidelity · Complexity & Innovation).
3. **Phase 1 — modeling approach** — per-component formulas with citations to research notes **01 (blade) · 02 (nozzle) · 03 (heater) · 17 (rail) · 18 (cleaning) · 19 (sensor)**; baseline composition (note 04); coupling matrix (note 05).
4. **Phase 2 — simulation design** — `Engine.step()` + `CouplingContext` + double-buffering (per AGENTS.md and `sim/src/copilot_sim/domain/`), historian schema (note 08), driver profiles (note 06), weather driver (note 07), stochastic mode + seeding (note 06 §chaos).
5. **§3.4 Observability layer** — true-vs-observed split, per-component sensor models (reference implementation in note 19), `print_outcome` derivation, operator events vocabulary.
6. **AI Maintenance Agent** — heuristic vs LLM-as-policy comparison (note 09), reset rules per component, A/B chart methodology.
7. **Challenges & solutions** — preventing two-way-loop runaway (stability via clamps + sub-unity gains), keeping sim throughput high, calibrating coefficients to land hackathon-friendly failure timelines.
8. **Evaluation + future work** — checklist from TRACK-CONTEXT §7; future = Phase 3 grounded chatbot (notes 10–13), RL policy, multi-machine fleet, twin sync.

## Demo split (5-minute slot, sim-only)

| Time | Owner | Segment | Beats |
| ---: | :--- | :--- | :--- |
| 0:00–0:30 | Daniel | Title + framing | One-liner; "every failure tells a story" |
| 0:30–1:30 | Chris | Phase 1 math (slides 3–4) | Six components, three subsystems, three laws + Weibull baseline; the coupled engine sketch — `prev_state → CouplingContext → next_state` |
| 1:30–2:15 | Chris | Coupling cascade + chart 1 | Walk the worked example: blade wears → powder dirty → nozzle clogs faster → wiper works harder; show the time-series with FAILED marker. |
| 2:15–3:00 | Jana / Leonie | What-if (chart 3) | Barcelona vs Phoenix side by side via Open-Meteo; show different components fail first; toggle chaos on/off on same seed |
| 3:00–3:45 | Daniel | Sensor-fault story (slide 6) | True vs observed health; show heater "drift" actually originates in sensor; LLM agent emits TROUBLESHOOT(sensor) → REPLACE(sensor) with rationale |
| 3:45–4:30 | Daniel | Maintenance A/B (chart 2) | Same-seed three-policy chart; uptime KPIs |
| 4:30–4:45 | Chris | AI surrogate (chart 4) | Analytic vs MLPRegressor heater curves overlaid — visually indistinguishable |
| 4:45–5:00 | Both | Close + future | Slide 9; future Phase 3 + RL; thank judges |

## Risk list & contingencies

| Risk | Likelihood | Fallback |
| --- | --- | --- |
| Sim fails to run live during demo | Medium | Commit a pre-recorded `historian.sqlite` with a known-good failure scenario; chatbot points at the canned DB |
| Voice (browser mic permission denied or noisy room) | High | Toggle to typed prompt mid-flow without breaking the 3-question script; mention voice as bonus pillar instead |
| LLM provider outage (Anthropic / OpenAI down) | Low–Medium | Vercel AI Gateway secondary provider; pre-warm two model IDs; cached responses for the canned 3 questions |
| Proactive alert doesn't fire on cue | Medium | Manually nudge driver values from a debug panel to force `CRITICAL`; or play a 10-second screen recording of a previous run |
| Wifi flaky / dashboard fails to load | Medium | Local `next dev` running on Daniel's laptop; pre-rendered chart PNGs in the deck as final fallback |
| Walkthrough video not uploaded in time | Low | Record a 3-minute Loom on Sat evening as a safety net before live polish continues Sunday |

## Open questions / action items

- **[blocking]** Confirm submission deadline + portal URL + judging slot from Slack `C0AV9TTJT25`; pin reply.
- **[Daniel]** Set up unlisted YouTube/Loom video; record draft Sat 22:00 even if app isn't final.
- **[Daniel]** Wire AI Gateway with a secondary provider before demo run-through.
- **[Chris]** Freeze a `demo-scenario.sqlite` Sun 06:00; tag commit `demo-frozen`.
- **[Both]** Dry-run the demo split twice with a stopwatch; first run by Sun 07:00, second by Sun 08:30.
- **[Mentor — Nathan]** Sanity-check the report's evaluation-against-pillars section before submission.
