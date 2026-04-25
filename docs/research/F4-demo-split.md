# F4 — Demo Split: Daniel (UX/chatbot/voice) + Chris (model + sim + historian)

## TL;DR

Chris opens with a 90-second live sim run to prove the engine works, Daniel owns the middle
three minutes showing the chatbot and voice interface against real historian data, Chris closes
with a 30-second "what's next" to leave judges on the AI Maintenance Agent angle. Two clean
hand-offs; the chatbot is the centrepiece, the sim is the credibility anchor.

---

## Recommended Run-of-Show

| Time      | Who    | What                                                                                                                                                     | Fallback                                                                          |
| --------- | ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| 0:00–0:20 | Chris  | One-sentence pitch: "We built a digital co-pilot for the HP Metal Jet S100 — a physics model, a time-advancing simulator, and a grounded AI operator."   | Skip if the intro card is already on screen; go straight to the terminal.        |
| 0:20–1:30 | Chris  | Launch the sim (terminal or simple UI). Fast-forward through a degradation scenario — show the recoater blade health index falling, nozzle clog rising. Point to the historian rows populating in real time. | Pre-run simulation stored in SQLite; replay from file if live run fails.         |
| 1:30–1:45 | Chris  | Hand-off line: "Every tick you just saw is now queryable. Daniel, ask it something."                                                                     | —                                                                                 |
| 1:45–3:00 | Daniel | Text chatbot demo. Type (or paste) three escalating questions: (1) "What is the current status of the nozzle plate?" (2) "When did it first enter DEGRADED?" (3) "What caused the cascade?" Each answer shows an evidence citation and severity tag. | Pre-recorded GIF/screenshot of correct responses on a backup laptop if the LLM API is unreachable. |
| 3:00–3:45 | Daniel | Switch to voice. Speak a proactive-alert question: "Will the heating element fail before the next scheduled maintenance?" Microphone picks up; response reads aloud. Show the grounding trace on screen simultaneously. | Fall back to text-only; skip the voice mic, narrate: "In production this is voice-enabled." |
| 3:45–4:00 | Daniel | Hand-off line: "Every answer is traceable to a historian row — zero hallucination by design. Chris, what does this unlock?" | —                                                                                 |
| 4:00–4:30 | Chris  | "What's next" close: AI Maintenance Agent that autonomously decides when to service the machine. Optional: 10-second teaser if it is already wired up.   | If not built, describe it verbally with the architecture slide on screen.        |
| 4:30–5:00 | Both   | Q&A buffer / judges' questions.                                                                                                                          | If overrun, drop the "what's next" segment; Daniel ends at 4:00.                |

---

## Hand-off Cues

1. **Chris -> Daniel (1:30–1:45):** Chris says "Daniel, ask it something" and steps back from the
   keyboard. Daniel is already positioned at the chatbot terminal or laptop.

2. **Daniel -> Chris (3:45–4:00):** Daniel says "Chris, what does this unlock?" Chris advances to
   the architecture slide or speaks from his position.

Both cues are verbal and explicit — no ambiguous pauses where the audience wonders who is talking.

---

## Pre-Demo Checklist (10 min before going on stage)

- [ ] Sim runs end-to-end from cold start and produces historian rows (Chris).
- [ ] SQLite / CSV historian file is populated with at least one interesting scenario (recoater
  degradation + cascade to nozzle, >100 ticks).
- [ ] Chatbot is connected to that historian file and returns cited answers for all three demo
  questions (Daniel).
- [ ] API key for the LLM is set in the environment and responding (Daniel).
- [ ] Voice mic tested; browser/app has mic permission granted (Daniel).
- [ ] Backup artefacts ready: pre-run historian file, response screenshots, architecture slide
  (both).
- [ ] Laptop display mirrored to the projector and resolution confirmed (both).
- [ ] Font size in terminal and chatbot UI is readable from 5 m away (both).
- [ ] Both teammates know the three demo questions by heart and the expected citation format.

---

## Open Questions

1. **Who controls the projector?** Decide before going on stage — one laptop, or HDMI swap?
2. **What scenario is pre-baked?** Agree on the exact run ID / scenario name so Daniel can
   reference it by name in the chatbot questions.
3. **Is voice fully built?** If not, decide now whether to skip or narrate-only; do not attempt
   a live mic demo for a feature that is not stable.
4. **Time-series visualisation:** Does Chris show a chart or just the terminal log? A chart is
   more impressive; confirm it renders without extra setup.
5. **Demo questions finalised?** Chris should review Daniel's three chatbot questions to confirm
   the historian data actually supports them (correct timestamps, cascade events present).

---

## References

- TRACK-CONTEXT.md, Section 8 (team split) and Section 7 (pre-demo self-check).
- Phase 3 evaluation pillars: Reliability, Intelligence, Autonomy, Versatility.
- Strategic bet: win on Phase 3 — grounded RAG/agentic chatbot + proactive alerts + voice.
