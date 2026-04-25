# F2 — Architecture Slide Deck Outline

## TL;DR

Ten slides: Title + Problem (2) → Phase 1/2/3 pairs (6) → Live demo screenshot (1) →
What we'd do next (1). Closing slide is implicit (team/thank-you). Total wall-time
target at 5 min: ~25 s per content slide, so keep text ruthlessly sparse. Use
**Pitch** (pitch.com) — collaborative, exports PDF, no install friction at a hackathon.

---

## Slide-by-slide outline

| # | Title | One-line content brief |
|---|-------|------------------------|
| 1 | **Digital Co-Pilot for the HP Metal Jet S100** | Project name, team names, HackUPC 2026 — the hook sentence: "A twin that diagnoses its own future failures." |
| 2 | **The Problem: Blind Spots Cost Metal** | 45-second framing: unplanned downtime in binder-jetting = scrapped batches + idle furnace time; operators get no warning until a nozzle clogs or a blade snaps. |
| 3 | **Phase 1 — The Brain: Degradation Model** | Architecture diagram of the Logic Engine (3 subsystems × mandatory component, 4 input drivers, 2+ failure models: Archard wear, Arrhenius thermal); one callout box per failure model. |
| 4 | **Phase 1 — Math That Moves** | Show the actual degradation equations (Archard for recoater blade, Arrhenius for heating elements, clog-rate for nozzle plate); one cascading-failure arrow (blade wear → powder contamination → nozzle clog). |
| 5 | **Phase 2 — The Clock: Simulation Loop** | Data-flow diagram: driver profile → tick loop → Phase 1 engine → Historian (SQLite); show a 6-column schema snippet (timestamp, run\_id, component, health\_index, status, driver values). |
| 6 | **Phase 2 — What the Historian Sees** | Two time-series charts (health index 0→1 over N hours for each component); annotate the DEGRADED→CRITICAL transition point; demonstrate stochastic shock event if implemented. |
| 7 | **Phase 3 — The Voice: Grounded RAG Chatbot** | Architecture: user query → LLM tool call → SQLite SELECT → evidence rows → LLM answer with Citation + Severity tag; zero-hallucination protocol callout: "AI may not answer from training knowledge." |
| 8 | **Phase 3 — Live Reasoning Demo** | Screenshot or GIF of the chatbot answering "Why did the nozzle degrade so fast?" with the historian row inlined in the response (timestamp, run\_id, health=0.34, status=CRITICAL). |
| 9 | **Demo: The Full Loop** | Single annotated screenshot of the dashboard: time-series panel (left) + chatbot panel (right) + a proactive alert banner at the top; caption "Everything on screen traces to a row in the historian." |
| 10 | **What We'd Do Next** | Three bullets: (1) Reinforcement-learning maintenance agent to discover optimal schedules; (2) Digital Twin Sync — ingest real sensor readings, self-correct the model; (3) Voice interface for hands-free factory-floor use. |

---

## Judge-bait checklist

- **Slide 4** — Show the raw equations. HP AI Innovation Hub rewards rigor; visible math
  signals this is not a demo wrapper around GPT.
- **Slide 5** — Name the historian schema columns explicitly. Proves Phase 2 actually
  persists; reviewers can ask to see the SQLite file.
- **Slide 7** — State the grounding protocol verbatim ("every answer must cite a
  timestamp and run ID"). This directly mirrors the brief's zero-tolerance hallucination
  rule and shows you read it.
- **Slide 8** — Show a real response with an inline evidence citation. This is the
  surprise moment — the AI quoting its own historian row.
- **Slide 9** — Cascading-failure annotation on the time-series. Demonstrates systemic
  interaction (blade → powder → nozzle), which the brief scores as a bonus.
- **Slide 10** — RL maintenance agent as "next step" signals awareness of the Phase 2
  bonus track without overpromising.

---

## Tool recommendation

**Pitch** (pitch.com). Reasons: real-time collaborative editing (two people, one
machine), clean defaults with no visual noise, exports to PDF in one click, runs in
the browser with no install, and its diagram blocks handle architecture flows without
requiring a separate Figma file. Avoid Tome/Gamma — AI-generated prose looks lazy to
technical judges. Avoid Keynote if the team is on different OSes.

---

## References

- HackUPC 2026 briefing pack (`docs/briefing/`) — Phase evaluation criteria and
  grounding protocol.
- TRACK-CONTEXT.md — canonical project brief used as source for all phase content.
- Pitch.com product page — tool capability confirmation (no web fetch needed;
  well-known tool).
