# hackUPC — Track Context

> Canonical brief for the "When AI meets reality / Build the Brain Behind the Machine" challenge by HP at HackUPC 2026.
> Authoritative source: [`docs/briefing/`](./docs/briefing/) (4 markdowns + slide deck PDF).
> Last updated: 2026-04-25

---

## 1. The Mission

Build a **Digital Co-Pilot** for the **HP Metal Jet S100** industrial 3D printer (binder jetting tech for metal parts).

Not a static dashboard — a partner that:

1. **Models** the printer's physics (component aging, failure, environmental sensitivity).
2. **Simulates** that model forward in time, producing timestamped telemetry.
3. **Communicates** through a grounded natural-language interface that reasons over real simulation data, never hallucinates, and proactively warns the operator.

Theme: *"When AI meets reality."* The judges (HP AI Innovation Hub) will reward complexity and AI use; they explicitly want to be **surprised**.

---

## 2. The Machine — HP Metal Jet S100 (Binder Jetting)

Process steps the simulation must respect:

1. **Powder Bed Preparation** — recoater spreads thin metal-powder layer.
2. **Binder Jetting** — printhead selectively jets liquid binder onto the powder.
3. **Layer Repetition** — platform lowers, repeat until green part complete.
4. **Curing** — heat consolidates the binder.
5. **Sintering** — furnace fuses metal particles into a dense part.
6. **Extraction & Post-Processing**.

Three subsystems are in scope. We **must** model at least one component from each.

| Subsystem | Mandatory Component | Failure Mode | Optional Components |
| :--- | :--- | :--- | :--- |
| **Recoating System** | **Recoater Blade** | Abrasive Wear (accelerated by Contamination) | Recoater Drive Motor (Mechanical Fatigue), Linear Guide / Rail |
| **Printhead Array** | **Nozzle Plate** | Clogging + Thermal Fatigue (accelerated when Temp Stress is out of bounds) | Thermal Firing Resistors, Cleaning Interface |
| **Thermal Control** | **Heating Elements** | Electrical Degradation (aging → more energy per °C) | Temperature Sensors, Insulation Panels (degraded insulation creates feedback loop) |

**Chosen Phase 1 component scope**

We will model two components per subsystem, chosen specifically because each pair creates an explainable feedback loop:

| Subsystem | Components to model | Coupling logic |
| :--- | :--- | :--- |
| **Recoating System** | **Recoater Blade**, **Linear Guide / Rail** | Alignment and rail wear affect blade contact quality; blade wear and misalignment degrade powder spreading quality, increasing downstream contamination risk. |
| **Printhead Array** | **Nozzle Plate**, **Cleaning Interface** | Nozzle clogging and cleaning efficiency form a mutual loop: clogged nozzles demand more cleaning, while a degraded cleaning interface leaves more residual clogging. |
| **Thermal Control** | **Heating Elements**, **Temperature Sensors** | Sensor readings influence heating control, while heating drift and sensor degradation create a feedback loop that changes effective temperature stress for every subsystem. |

This makes Phase 1 a coupled discrete-time model rather than independent component curves: every component update at `t` can depend on its own state at `t-1`, relevant component states at `t-1`, the current drivers, and the time delta.

---

## 3. The Data Contract (every phase respects this)

### 3.1 Inputs — the 4 Environmental & Operational Drivers

The Phase 1 engine must accept all four. Phase 2 generates them over time. Phase 3 reads them back from the historian.

- **Temperature Stress** — ambient °C, deviation from optimal.
- **Humidity / Contamination** — air moisture and powder purity.
- **Operational Load** — print hours / cycles completed.
- **Maintenance Level** — coefficient of how well the machine is being cared for; can be modified by maintenance events.

### 3.2 Outputs — Component State Report

Per component, every tick:

- **Health Index** — normalised `0.0` (dead) to `1.0` (new).
- **Operational Status** — categorical: `FUNCTIONAL` | `DEGRADED` | `CRITICAL` | `FAILED`.
- **Component Metrics** — physical quantities defined per component (e.g. blade thickness mm, nozzle clog %, heater resistance Ω).

### 3.3 Engine must be deterministic

Same inputs → same outputs. Stochasticity, if added, is seeded.

### 3.4 Observability — sensors are optional, partial, and themselves fail

Confirmed by the challenge organisers: **we choose how the operator perceives component health**. Not every component carries a health sensor, and the ones that do can themselves degrade.

- **Per component, we decide whether it has a sensor.** Sensored components expose direct readouts (e.g. heater resistance, nozzle clog %, blade thickness via load cell). Unsensored ones are only knowable through downstream effects.
- **Sensors decay and fail too.** A sensor can drift, freeze, or report unrealistic values — and a wrong reading the system trusts can drive bad maintenance decisions and affect production.
- **The print itself is a signal.** When a component is badly degraded, the print either halts entirely or produces a part with visibly poor quality. The operator notices, stops the machine, troubleshoots, and fixes or replaces the part before resuming.
- **Operator loop we are supporting:** *notice anomaly → stop → diagnose → fix or replace → resume.* The Digital Co-Pilot's job is to shorten or pre-empt every step of this loop.

**Implications for our model**

| Layer | What changes |
| :--- | :--- |
| **Phase 1** | Separate **true state** (ground-truth health, used internally) from **observed state** (what a sensor or quality metric exposes). Each sensored component carries its own sensor model: `(true_value, sensor_health, drift, noise) → observed_value`. |
| **Phase 2** | Historian stores both true and observed values per tick, plus a `print_outcome` field per run (`OK` / `QUALITY_DEGRADED` / `HALTED`) and operator events (`troubleshoot`, `fix`, `replace`). |
| **Phase 3** | The co-pilot must reason about **how much to trust each reading** and cross-reference sensors, print outcomes, and component history to distinguish *component fault* from *sensor fault*. Natural fit for the Agentic Diagnosis pattern and a strong differentiator on the Reasoning Depth and Proactive Intelligence pillars. |

**Open design choices** *(to resolve in Phase 1 planning)*
- Which components get a direct sensor and which are inferred from print quality / halts?
- Failure modes per sensor: stuck-at, drift, additive noise, full dropout?
- What "print outcome" signals do we expose to the operator/AI as ground-truth observable events?

---

## 4. The Three Phases

### Phase 1 — Model (the Brain)

Build a **Logic Engine** — a mathematical, modular, callable function that ingests `(previous_state, drivers, time_increment)` and returns the next state per component. **No UI, no loop here.**

**Minimum bar:**
1. ≥1 component per subsystem (3 total).
2. ≥2 standard mathematical failure models applied (e.g. Exponential Decay, Weibull, Arrhenius, Coffin-Manson, Archard, Paris).
3. All components react to **at least the four input drivers** above.
4. Deterministic, callable from an external loop (Phase 2 will drive it).

**Implementation modes:** rule-based (formulas) or data-driven (regressor / NN / LSTM trained on synthetic data). Both valid.

**Advanced (bonus) ideas:**
- **Cascading failures** — degraded blade → contaminates powder → clogs nozzle.
- **Stochastic realism** — environmental shocks, sensor drift, probabilistic events.
- **Maintenance as input** — partial health recovery, decay-curve reset.
- **AI degradation model** — replace one component's formula with a learned model.
- **Live weather API** — Open-Meteo / OpenWeather as the temperature/humidity driver.

**Evaluation:** Rigor · Systemic Interaction · Complexity & Innovation (bonus) · Realism & Fidelity (bonus).

### Phase 2 — Simulate (the Clock + the Historian)

Wrap Phase 1 in a time-advancing loop and persist every state to a queryable historian.

**Data flow per tick:**
1. Loop generates / reads the four driver values for `t`.
2. Loop calls Phase 1 with `(prev_state, drivers, dt)`.
3. Phase 1 returns new component states.
4. Loop attaches timestamp + run/scenario ID and writes to the historian.

**Minimum bar:**
1. Functional clock loop with a chosen `dt` (e.g. 1 min, 1 hour).
2. Persistence to **CSV, JSON, or SQLite** — every tick, every component, every driver, timestamp, run ID.
3. Phase 1 engine called every tick (no shortcuts).

**Implementation modes (pick one or more, equally valid):**
- **Batch** — run the full scenario, export a single file.
- **Real-time streaming** — emit data points one-by-one for live demos.

**Architectural patterns:**

| Pattern | Level | Logic |
| :--- | :--- | :--- |
| **A. Deterministic Replay** | Minimum | Sequential, fixed inputs from a profile. |
| **B. Informed Extrapolation** | Advanced | Sync to historical data, then predict forward. |
| **C. Stochastic Simulation** | Advanced | Inject noise / random events into the driver stream. |

**Advanced (bonus) ideas:**
- **What-if scenarios** — same printer, different climates / duty cycles.
- **Chaos injection** — random shocks the twin must survive.
- **AI Maintenance Agent** — autonomously decides *when* to maintain to maximise uptime.
- **RL policy** — train across thousands of episodes to discover an optimal maintenance schedule.
- **Digital Twin Synchronisation** — feed in "real" sensor readings, let the twin self-correct.

**Evaluation:** Time moves · Systemic Integration · Complexity & Innovation (bonus) · Realism & Fidelity (bonus).

### Phase 3 — Interact (the Voice)

Build a grounded natural-language interface over the Phase 2 historian. The AI is a **reasoning layer**, not an oracle: it queries the data and explains what it found.

**Reasoning ladder:**

| Pattern | Level | Logic |
| :--- | :--- | :--- |
| **A. Simple Context Injection** | Mandatory baseline | Current state injected into the system prompt. Answers "what is the status now?" |
| **B. Contextual RAG** | Advanced | Translate user question → DB query → retrieve relevant rows → answer. Handles "what happened at 2pm?" |
| **C. Agentic Diagnosis** | Advanced (highest) | Tool-calling ReAct loop. AI searches, compares, concludes across multi-step investigations. |

**Grounding Protocol (zero-tolerance hallucination):**
- AI may not use training-knowledge to answer questions about the printer state.
- Every response must be traceable to a specific timestamp / component / run ID.
- Every response must include an **Evidence Citation**.
- Every response must include a **Severity Indicator**: `INFO` | `WARNING` | `CRITICAL`.

**Advanced (bonus) ideas:**
- **Proactive alerting** — background monitor that fires *before* the operator asks.
- **Voice / hands-free** — voice-to-voice for factory-floor demo.
- **Root-cause diagnosis** — chain events into a story, not just status.
- **Action paths** — recommend what to do, with priority and impact.
- **Autonomous collaborator** — persistent memory across sessions, repetitive-query automation.

**Evaluation pillars:**
1. **Reliability** — Grounding Accuracy (zero hallucinations), Communication Clarity.
2. **Intelligence** — Reasoning Depth (diagnosis, root cause).
3. **Autonomy** — Proactive Intelligence, Collaborative Memory.
4. **Versatility** — Interaction Modality (voice / multi-modal).

A team can win on any one pillar.

---

## 5. Constraints & Rules

- **Free tech stack** — any language, framework, cloud.
- **No pre-made data** — we generate all telemetry from our own simulator.
- **AI/LLM is highly valued** but every AI answer must be traceable to a specific simulation data point. No reasoning from training knowledge about the printer state.
- **Out of scope** — physical hardware integration, CAD-level physics. We model *part-level degradation*, not the full machine physics.

---

## 6. Submission Requirements

| # | Deliverable |
| :- | :--- |
| 1 | **Working Demo** — Phase 1 + Phase 2 minimum, Phase 3 is a significant bonus |
| 2 | **Architecture Slide Deck** — math models, simulation loop, AI design, diagrams |
| 3 | **Technical Report** — modeling approach, simulation design, AI implementation, challenges & solutions |
| 4 | **Phase 3 Bonus Demo** — if implemented |
| 5 | **GitHub Repo** — clean, modular, README with setup instructions |
| 6 | **Walkthrough Video / Live** — show the "intelligence" of the twin |

---

## 7. Pre-Demo Self-Check (from the brief)

**Phase 1**
- [ ] ≥1 component per subsystem modeled
- [ ] Each uses ≥1 driver
- [ ] ≥2 failure models implemented
- [ ] Outputs include health index, operational status, metrics
- [ ] Team can explain the degradation logic

**Phase 2**
- [ ] Time advances correctly and consistently
- [ ] Phase 1 called every tick
- [ ] Every record saved to historian with timestamp + drivers
- [ ] Runs/scenarios identifiable separately
- [ ] Time-series viz shows health evolving
- [ ] Team can identify when and why each component fails

**Phase 3**
- [ ] Interface reads from the Phase 2 historian
- [ ] Responses grounded; not hallucinated
- [ ] Every answer has explicit citation/timestamp
- [ ] Advanced reasoning still traceable to logs

**Demo readiness**
- [ ] Team can explain how the three phases connect
- [ ] Demo reproducible end-to-end
- [ ] Every AI answer's source data can be shown

---

## 8. Our Team & Strategic Bet

- **Daniel** — full-stack, owns Phase 1+2 bonuses (cascade, AI surrogate, weather, chaos, dashboard).
- **Chris** — data engineer / CS, owns Phase 1+2 core (math, sim loop, historian).
- **Mentor:** Nathan.
- **Stated interest:** data-heavy tracks; we lean into rigorous physics + AI-driven simulation bonuses.

**Strategic bet (revised 2026-04-25):** the win is in **Phase 1 + Phase 2 done exceptionally well**. Stack as many sim-side bonus pillars as we can — **Cascading Failures · Stochastic Realism · Maintenance as Input · AI-Powered Degradation · Live Environmental Data · What-If Scenarios · Chaos Engineering · AI Maintenance Agent**. **Phase 3 (chatbot, voice, frontend) is deferred** for this iteration; research is preserved in `docs/research/10-13.md` for future work.

Surprise factor we want: a digital twin that produces **time-series stories you can defend with citations** — Barcelona vs Phoenix under live weather, three-policy maintenance A/B on the same seed, a learned heater model indistinguishable from the analytic, and a worn blade that visibly cascades into a clogged nozzle.

---

## 9. Architecture Sketch (working draft)

```
                ┌──────────────────────┐
input drivers ─▶│  Degradation Model   │──▶ component health (t)
(temp, humidity,│  (formulas + ≥1 ML)  │
 load, maint.)  └──────────────────────┘
                          ▲ │
            previous state│ │ next state
                          │ ▼
                ┌──────────────────────┐
                │  Simulation Loop     │  ──▶  Historian (SQLite)
                │  state(t+1) =        │       runs, ticks, drivers,
                │    f(state(t), x(t)) │       health, status, metrics
                └──────────────────────┘
                          ▲ │
                 modifies │ │ reads
                          │ ▼
                ┌──────────────────────┐
                │  AI Maintenance Agent│  (Phase 2 bonus)
                │  decides when to     │
                │  trigger maintenance │
                └──────────────────────┘
                            │
                            ▼
                ┌──────────────────────┐
                │  Streamlit Dashboard │  ──▶  judges + operators
                │  - Time-series viz   │
                │  - Scenario picker   │
                │  - A/B policy chart  │
                └──────────────────────┘

      Phase 3 (chatbot · voice · grounded RAG) is researched but DEFERRED.
```

---

## 10. Changelog

- **2026-04-25** — Initial draft from verbal briefing transcript.
- **2026-04-25** — Rewritten from authoritative briefing pack (4 markdowns + 21-page deck): added HP Metal Jet S100 specifics, mandatory components per subsystem, the four-driver contract, output schema with status enum, Phase 1/2/3 patterns and minimum bars, Phase 3 grounding protocol + four evaluation pillars, submission package, pre-demo checklist, strategic bet on Phase 3.
- **2026-04-25** — Added §3.4 Observability after organiser clarification: sensors are optional and per-component, sensors themselves decay and can mislead, print halt / quality drop are first-class observable signals, and the operator's notice→stop→diagnose→fix→resume loop is what the Co-Pilot supports. Introduces the true-state vs observed-state split, sensor models, and `print_outcome` / operator-event fields in the historian.
- **2026-04-25** — Strategic bet revised: focus on Phase 1 + Phase 2 (digital twin simulation) only. Phase 3 deferred. Architecture sketch updated to remove the chatbot/voice layer; replaced with a Streamlit-based time-series dashboard that satisfies the Phase 2 deliverable.
