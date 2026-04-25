# 16 — Submission Prep: Deadline, Deck, Report, Demo Split

## TL;DR

HackUPC closes Sunday 2026-04-26; **lock submission by Sun 09:00 CEST** (placeholder — confirm in Slack `C0AV9TTJT25`). Six deliverables: GitHub repo, slide deck, technical report, walkthrough video, live demo, optional Phase 3 bonus demo. Build artefacts now: a 9-slide deck mirrored by an 8-section report, a 5-minute demo split (Daniel ~3 min app/chatbot/voice, Chris ~2 min math/sim/agent), and 5 contingencies (canned historian, typed fallback, AI Gateway secondary, screen-recorded video, pre-rendered chart PNGs).

## Submission deadline & format

- **Deliverables (TRACK-CONTEXT.md §6):** working demo (P1+P2 min, P3 bonus), architecture slide deck, technical report, P3 bonus demo if shipped, GitHub repo with README, walkthrough video or live demo.
- **Deadline:** *placeholder* — Sun 2026-04-26, ~09:00 CEST hard freeze, judging windows 10:00–13:00. Confirm in Slack workspace `T0APCMG2G1Z`, channel `C0AV9TTJT25`.
- **Format expected:** GitHub URL + uploaded PDF deck + uploaded report (md or PDF) + video link (YouTube unlisted or Drive). Live demo at judging table.
- **Action item:** within first hour of build day 2, confirm exact deadline timestamp, judging slot start, and submission portal URL from Slack; pin reply to team.

## Slide deck outline

1. **Title — "When AI Meets Reality: a Digital Co-Pilot for the HP Metal Jet S100"** — team names (Daniel + Chris), mentor (Nathan), one-liner: "A digital twin that diagnoses its own future failures."
2. **The mission** — 3-line problem statement (printer fails unpredictably, operators have no grounded AI partner, training-knowledge LLMs hallucinate); the 3-phase architecture diagram (Brain → Clock → Voice).
3. **Phase 1 — The brain** — per-component math: Archard wear (recoater blade), Coffin-Manson + clog accumulation (nozzle plate), Arrhenius drift (heater); deterministic state function `f(state, drivers, dt)`.
4. **Phase 1 — Cascading + AI surrogate (bonus)** — degraded blade → contaminated powder → faster nozzle clog; one component swapped for a learned regressor trained on synthetic data; live weather driver via Open-Meteo.
5. **Phase 2 — The clock + the historian** — tick loop, SQLite schema (runs, ticks, drivers, components), time-series chart of health index with a `FAILED` event annotated; deterministic + stochastic modes.
6. **Phase 2 — AI Maintenance Agent (bonus)** — A/B chart: no-maintenance vs agent-driven maintenance; uptime delta and cost trade-off; policy described in plain English.
7. **Phase 3 — Grounded agentic chatbot** — ReAct tool-calling loop, tools (`query_historian`, `get_component_state`, `compare_runs`); every answer cites timestamp + run + component and surfaces a severity badge.
8. **Phase 3 — Proactive alerts + voice (bonus pillars)** — background monitor fires `WARNING`/`CRITICAL` toasts before the operator asks; voice mode for hands-free factory-floor demo; covers all four P3 pillars (Reliability, Intelligence, Autonomy, Versatility).
9. **Closing — what we'd do next** — digital twin sync from real telemetry, RL maintenance policy across thousands of episodes, multi-machine fleet view, persistent collaborator memory, mobile alerting.

## Technical report outline

1. **Executive summary** — one paragraph: what we built, why it's grounded, what's novel (cascading + agentic chatbot).
2. **Problem & approach** — restate the brief in our words; map our work to the four P3 pillars.
3. **Phase 1 — modeling approach** — per-component formulas with citations to research notes 01–05; driver normalisation (note 04); cascading rules (note 05).
4. **Phase 2 — simulation design** — loop + dt choice, historian schema (note 08), driver profiles (note 06), weather driver (note 07), stochastic mode + seeding.
5. **Phase 3 — AI implementation** — agent architecture (note 10), tool surface, grounding/citation contract, severity classification, proactive alert engine (note 12), voice modality, maintenance agent (note 09).
6. **Challenges & solutions** — preventing hallucinations, balancing realism vs runtime, cascading numerical stability, voice latency.
7. **Evaluation against the brief's pillars** — checklist from TRACK-CONTEXT §7 with evidence links to commits / charts.
8. **Future work** — same as deck slide 9, plus open research questions (RL reward shaping, twin sync convergence).

## Demo split (5-minute slot)

| Time | Owner | Segment | Beats |
| ---: | --- | --- | --- |
| 0:00–0:30 | Daniel | Title + framing | One-liner; "every claim cited or it doesn't ship" |
| 0:30–1:30 | Chris | Phase 1 math | Walk slides 3–4: Archard, Coffin-Manson, Arrhenius; cascading sketch |
| 1:30–2:15 | Chris | Phase 2 chart + agent | Time-series with `FAILED` event; A/B uptime chart from maintenance agent |
| 2:15–4:15 | Daniel | Phase 3 live | Open dashboard; 3 chatbot Qs (status now, what happened at tick N, why is heater drifting) — middle Q in voice mode; show proactive alert toast firing |
| 4:15–4:45 | Daniel | Citations + severity | Click a citation, jump to historian row; show severity badge promotion |
| 4:45–5:00 | Both | Close + future work | Slide 9; thank judges; Q&A handoff |

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
