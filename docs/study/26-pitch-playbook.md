# 26 — 3+2 Pitch Playbook

> 3 minutes demo, 2 minutes Q&A, no slides allowed, code demo mandatory. Judging on **Technology · Idea · Learning** — equally weighted, gut-feel allowed. Code quality, pitch polish, and viability all *explicitly* excluded.

> **Time split**: **2 minutes on the simulation** (math + dashboard) · **1 minute on the chatbot**. The math is the harder thing to visualise, so it gets the bulk — but every math claim has to land on a screen, never on words alone.

---

## Opening principle: the demo IS the pitch

The judging criteria don't reward smooth talking — they reward *visible craft*. Every spoken word should name something currently on screen. Stand still and talk over a static screen and you fail not on content but on **demoability**.

**DO**: click while you talk · let visible state do the heavy lifting · show then narrate · pause after impact moments to let the chart breathe.

**DON'T**: open with "we built a digital twin" · narrate without showing · apologise for what's missing · explain math abstractly when you can point at the formula in the code.

---

## Pre-demo setup (do this before the judges sit down)

Tile the screen so you can switch contexts without alt-tabbing:

```
┌──────────────────────────┬────────────────────┐
│                          │                    │
│  Streamlit dashboard     │  IDE / text editor │
│  (browser tab 1)         │  open at:          │
│                          │  components/       │
│                          │     nozzle.py      │
│                          │  engine/coupling.py│
│                          │                    │
└──────────────────────────┴────────────────────┘
                           +
              ┌────────────────────────┐
              │  Web app browser tab 2 │
              │  /app/runs/<phoenix>   │
              │  AI chat focused,      │
              │  question pre-typed    │
              └────────────────────────┘
```

Pre-loaded historian state:
- `barcelona-baseline.yaml` (260 ticks, sensor stable)
- `phoenix-18mo.yaml` (78 ticks, sensor degrades — the demo run)
- Optional: `barcelona-with-chaos.yaml` for the chaos question fallback

Don't run scenarios live during the demo. Risk of failure or mid-pitch latency.

---

## The 3-minute flow (2 min sim + 1 min chatbot — print this, tape it to the laptop)

### 0:00 → 0:15 — Hook (≤30 words) [15s]

Pre-loaded: Streamlit dashboard, **Barcelona-baseline** run, panel 1 visible.

> *"Same industrial 3D printer. Two cities. Six months of operation. Barcelona — sensor stays trustworthy, nozzle dies first. Watch what happens in Phoenix."*

### 0:15 → 0:45 — The climate A/B (Idea pillar) [30s]

Switch the run_id dropdown to **phoenix-18mo**. Don't speak for 2 seconds while panels redraw — the visual jolt does the work.

> *"Same engine. Same seed. Only the climate changed — Phoenix has a hotter ambient, longer duty cycles, weaker maintenance. Now scroll down to panel 2."*

Scroll to panel 2. Point at the nozzle FAILED card.

> *"When the nozzle failed, top three causes by absolute magnitude: powder spread quality 0.93, sensor bias 0.88°C, controller temp error 0.88°C. The sensor is lying to the heater controller, the heater overshoots, the nozzle cooks. **Same printer, different climate, different failure mode.**"*

### 0:45 → 1:15 — The math, anchored to code (Technology pillar) [30s]

Switch to the IDE side panel. Open `sim/src/copilot_sim/components/nozzle.py` at line 64.

> *"Six classical failure laws, one per component. The nozzle plate runs Coffin-Manson thermal fatigue plus Palmgren-Miner damage accumulation plus a Poisson clog hazard — that's the worst-case TIJ printhead literature, three independent damage processes."*

Point at lines 80-100 (the `cm_temp_factor`, Poisson draw).

> *"Every formula is multiplied by a maintenance damper, every increment is bounded by `clip01`, every random draw flows through a per-component, per-tick numpy generator keyed on a `blake2b` digest. Same seed, byte-identical run, across processes."*

Switch tabs to `engine/coupling.py` line 36.

> *"All cross-component effects flow through one function. Ten named coupling factors built from the immutable `t-1` state — they're what the cascade card you just saw was reading. We persist them as JSON on every tick of the historian, so failure analysis is a SQL query, not an engine re-run."*

### 1:15 → 1:45 — The §3.4 wow (Technology + Idea) [30s]

Switch back to the dashboard. Scroll to panel 8 (proactive alerts feed).

> *"This is the surprise. The brief said sensors can fail too. So we built that. The temperature sensor ages on its own Arrhenius curve, has its own physics file, drifts a calibration offset over time. The maintenance policy reads only the observed state — exactly like a real operator. When the sensor lies, the policy gets fooled."*

Point at a `SENSOR → DEGRADED` row in the alerts feed.

> *"Every status transition the engine produced, timestamped, with the top driver factor at that exact tick. This is the policy reacting to the lying sensor in real time."*

### 1:45 → 2:00 — Sensor-heater closed loop (one sentence) [15s]

> *"The kicker: a drifting sensor → controller commands more heat → heater overshoots → heater ages faster from Arrhenius → drifted heater throws thermal stress on the sensor → sensor drifts faster. Closed feedback loop, in code."*

### 2:00 → 2:30 — The chatbot (Phase 3 grounding) [30s]

Switch to web app tab 2 — `/app/runs/<phoenix-run-id>` with chat focused. Submit the pre-typed question:

**`Why did the nozzle fail in this run?`**

> *"Watch what the agent does. It has seven tools that wrap database queries — that's the *only* path to printer state. It just called `getStateAtTick`, then `inspectSensorTrust`, now it's narrating — with citations: runId, tick, component."*

### 2:30 → 2:45 — Why grounding is structural (Technology) [15s]

> *"It cannot hallucinate because **it has no training-aware path to printer-state values**. Tool-only access is stronger than any prompt rule. Every claim cites a `runId/tick/componentId`. Without a citation, the answer is by definition ungrounded — and the model has nothing else to cite."*

### 2:45 → 3:00 — Closer (≤25 words) [15s]

> *"Six failure laws, ten coupling factors, every failure traceable to a tick, an agent that can't hallucinate. Three minutes. Questions."*

---

## The 2-minute Q&A toolkit — 10 likely questions, 15-second answers

### Technology

**Q1: "How do you guarantee the AI doesn't hallucinate?"**
> Tool-only data access. The agent has seven typed tools that wrap database queries; that's the only path to printer state. Plus a system prompt that forces `runId/tick/componentId` citations. Without a citation, the answer is by definition ungrounded — and the model has nothing to cite from training.

**Q2: "What's the most impressive technical thing you built?"**
> The single coupling-context object that all six component physics functions read from. Update-order independence by construction — reordering the components mathematically can't change the result. And we persist its 10 named factors as JSON per tick, so failure analysis is a pure SQL query, no engine re-run.

**Q3: "Why these physics laws?"**
> They're the textbook ones for each mechanism. Archard is *the* abrasive-wear law since 1953, Lundberg-Palmgren is *the* bearing-fatigue law NSK and THK use in their datasheets, Coffin-Manson is *the* low-cycle thermal-fatigue law for thin-film resistors. We didn't invent physics — we applied it.

**Q4: "How does determinism work with stochastic processes?"**
> Three RNG axes: scenario seed, tick number, blake2b digest of component ID. Every component gets its own statistically independent stream, but same seed always reproduces the same trajectory — independent of process, parallelism, or `PYTHONHASHSEED`. Tested in `tests/engine/test_rng_determinism.py`.

**Q5: "What's the historian schema look like?"**
> Seven SQLite tables, all time-series tables `WITHOUT ROWID` so each row is stored inline with its index — single B-tree lookup per query. WAL mode so the dashboard can read while the simulator writes. The killer column is `coupling_factors_json` on the drivers table — full attribution for every tick.

### Idea & Innovation

**Q6: "What makes this different from existing digital twin tools?"**
> Most digital twins simulate components in parallel as independent curves. Ours is *coupled* — six components share one state, and a sensor failure in the thermal subsystem can cascade into the printhead clogging in the recoater system. We model how real industrial machines actually fail: through their interactions.

**Q7: "What's your 'wow' moment?"**
> The §3.4 sensor-fault story. The brief said sensors can fail too — so we made the temperature sensor age on its own Arrhenius curve, lie to the heater controller, and made the maintenance agent read only the observed view. The agent gets fooled by the lying sensor and emits TROUBLESHOOT(sensor) — exactly like a real operator. That's a closed loop in code.

**Q8: "What was the hardest design decision?"**
> Choosing `dt = 1 simulated week` instead of 1 hour. At 1 hour, the slowest component (linear rail, η = 540 days) needs ~13,000 ticks to fail — 13× the historian writes, 13× slower demo. At 1 week, full failure arc in 78 ticks for an 18-month run, sub-second writes, instant dashboard. The trade-off was losing diurnal variability — defensible because the slowest physics doesn't see daily noise anyway.

### Learning

**Q9: "What did you learn this weekend?"**
> Pick one each from the team: `pydantic` for YAML validation that catches typos at load-time instead of runtime; `Convex Agent` for typed tool-calling with structured citations; SQLite WAL pragmas for concurrent reader/writer; `blake2b` for process-stable RNG keys when Python's built-in hash is salted. The boring one but maybe the most useful: how to compose a coupled discrete-time system without letting update order leak into results.

**Q10: "What would you do differently?"**
> Train the AI surrogate sooner. We specified an `MLPRegressor (32, 32, 32) tanh` to replace the heater's analytic Arrhenius — same input/output shape, parity within 2 % MAE — but didn't get to wire it in. It's the AI-in-the-physics bonus from stage-1.md. With another four hours we'd have it.

---

## Three "wow" anchors — these are the moments that should make a judge tilt their head

1. **Phoenix vs Barcelona A/B in the first 45 seconds** — same engine, same seed, *climate alone* swaps which component fails first. Visual jolt.
2. **Cascade card showing `sensor_bias_c = 0.88` as a top-3 cause of nozzle FAILED** — not what a judge expects to see. Lets you tell the §3.4 story in 10 seconds.
3. **The agent making real tool calls live with `runId/tick/component` citations** — Pattern C agentic diagnosis with grounding, on stage. Most teams will say "we have an AI feature". You can *show* the agent calling `getStateAtTick` then `inspectSensorTrust`.

---

## What to map to each judging criterion (60-second mental rehearsal)

| Criterion | Your demo line that hits it |
|---|---|
| **Technology** | "Tool-only data access — the agent has no path to printer state except through 7 typed query handlers. Stronger than any prompt instruction." |
| **Idea & Innovation** | "Same engine, same seed, only the climate changes — and a sensor lying to a heater controller closes a feedback loop in code." |
| **Learning** | "Two of us hadn't touched Convex agents before this weekend. One had never written SQLite WAL pragmas. Three days ago we didn't know what Coffin-Manson fatigue was." |

---

## Final dress-rehearsal checklist

- [ ] Pre-load both runs in the historian: `barcelona-baseline` and `phoenix-18mo`. Don't run scenarios live.
- [ ] Tile the screen: Streamlit + IDE + web-app browser tabs. Have `components/nozzle.py` and `engine/coupling.py` already open.
- [ ] Type the agent question in advance, but don't submit. You hit enter live.
- [ ] Have a fallback: if the agent times out, pivot to *"let me show you the data it would have queried"* and open panel 2 in Streamlit. Same story, no agent.
- [ ] Practice the closer — most demos die in the last 15 seconds because the demoer relaxes. Land it crisp.
- [ ] Don't apologise for missing things. If asked, *"specified, queued, here's the spec"* is a stronger answer than *"we didn't get to it"*.
- [ ] Keep your hands visible. Don't fold your arms. Body language affects judge gut feel even though they don't think it does.

---

## Why this 2:1 split is right

The math model is the harder thing to visualise — graphs of equations don't pop on a screen the way a live AI conversation does. Allocating 2/3 of the demo to the simulation gives you:

- 30 s for the climate A/B (visual jolt)
- 30 s anchored on actual code (formulas → coupling factors → JSON)
- 30 s on the §3.4 sensor-fault wow (panel 8 + closed-loop narration)
- 30 s on the chat (agent calling tools, citing data)
- 15 s × 2 for the hook + closer

Compressing the chatbot to 1 minute is fine because the demo is short enough that one well-formed question + one tool-call narration is enough. **The chatbot's job in this pitch is to *prove* the grounding contract, not to show off a long conversation.** One question, one tool chain, one cited answer — done.

---

## Cross-references

- Defense audit (every requirement, every file path): [`25-defense-audit.md`](25-defense-audit.md)
- Dashboard panel walkthrough: [`24-dashboard-walkthrough.md`](24-dashboard-walkthrough.md)
- Per-component math: [`components/10-blade.md`](components/10-blade.md) through [`components/15-sensor.md`](components/15-sensor.md)
- Coupling and cascades: [`03-coupling-and-cascades.md`](03-coupling-and-cascades.md)
- Realism audit (what's an honest gap vs an oversell): [`22-realism-audit.md`](22-realism-audit.md)
