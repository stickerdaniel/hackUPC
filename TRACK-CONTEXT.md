# hackUPC — Track Context

> Living document. Captures everything we know about the challenge so far.
> Last updated: 2026-04-25

---

## 1. The Challenge (Vision)

**Host:** Barcelona AI Innovation Hub (HP-related, 3D printer domain).

**Vision:** Build an **intelligent AI partner** that manages the complexity
of operating a 3D printer — predicting wear, simulating future state, and
giving the user an interface to query and act on it.

The challenge is intentionally open. We can play to our strengths (data,
AI, UX, physics, agents) and skip lightly through stages we care less about.

---

## 2. The Three Stages

The challenge is structured as three sequential phases. Each phase has a
**minimum bar** + **advanced extensions**. We can pick where to invest depth.

### Stage 1 — Modeling (the "brain")

Build a **degradation model** for printer components.

- A degradation model = a function: `inputs → health index of a component`.
- Inputs are external "input drivers" (e.g. usage, temperature, humidity, motion).
- Output is a health/wear score for that component over time.
- **Minimum:** model **one single component**.
- The printer has many parts; pick the most relevant ones.

**Advanced extensions for Stage 1:**
- External APIs as input drivers (weather, humidity, temperature, historical records).
- Replace the math formula with an **AI model** (regression / trained / pretrained).
- Multiple components, with **dependencies** — when component A breaks, it
  accelerates degradation of B (cascading failure).
- Closer-to-physics modeling for teams with physics expertise.

### Stage 2 — Simulation (the loop)

Take the Stage 1 model and **run it in a loop over time**, feeding the
previous state back into the next iteration.

- Each tick: previous health + current input drivers → next health.
- This is where we **generate our own data**. We control it. Generate as
  much as we need.
- The simulation produces the time-series data the dashboard / chatbot
  consumes.

**Advanced extensions for Stage 2:**
- **Autonomous agent** that influences inputs — e.g. triggers maintenance,
  changes operating conditions, and watches the health index recover.
- Agent that keeps the machine healthier for longer **by itself**.
- **Hybrid sim/real** — over time, ingest real sensor data and let the
  model recalibrate from ground truth instead of pure simulation.

### Stage 3 — User Experience / Interaction

Surface the data and the model to a real user.

- **Minimum:** a dashboard showing degradation over time. Could stop here.
- **Encouraged:** natural-language interaction (chatbot / voice / etc.).

**Critical UX constraint:** the chatbot must be **grounded**. It cannot
hallucinate temperatures or health values — it must read from the data.
This is the real-world AI integration challenge.

**Advanced extensions for Stage 3:**
- **Proactive / predictive** agent — anticipates failures before they
  happen and recommends actions (e.g. "lower temperature", "schedule
  maintenance on component X").
- Decision support — present the user with choice points.
- Any creative interface: website, chatbot, audio, something unexpected.

---

## 3. Hard Constraints & Notes

- **No data is provided.** This is intentional — we generate it ourselves
  via the simulator. Means we control distribution, edge cases, scenarios.
- **No CAD file.** Sim is **not** about machine physics (too complex).
  It's about **part-level degradation** driven by known characteristics
  (e.g. "this part degrades with motion / temperature").
- **Tech stack is free.** Any language, any framework.
- **AI is encouraged but not required.** The Barcelona AI Innovation Hub
  would love to see AI somewhere. No penalty if we skip it, but it is the
  hub's spirit. Surprise them, think outside the box.
- **Markdown briefing docs** will be dropped in Slack — they describe
  components, subsystems, degradation characteristics. We can use those
  or invent our own valid assumptions.

---

## 4. Key Examples From the Briefing

- **Environment matters:** running the printer in a hot/humid place
  breaks it down faster; in Finland (cold), much slower. Good demo angle.
- **Component-driven degradation:** each part has a known wear pattern
  (motion-driven, temp-driven, cycle-count-driven, humidity-driven, etc.).
- **Dependency example:** one component fails → load shifts → next
  component fails faster.

---

## 5. Deliverable Bar

- **Minimum to ship:**
  1. A working degradation model for ≥1 component.
  2. A simulation loop generating time-series data over time.
  3. A user dashboard visualizing degradation.
  4. Be able to **explain how the model works** to the judges.

- **What wins:** showing where our team's strength is, picking one stage
  to go deep on, and surprising the judges. Not penalized for going
  shallow on the stages we care less about.

---

## 6. Our Team

- **Daniel** (me).
- **Chris** — data engineer / CS background.
- **Mentor:** Nathan.
- **Stated interest:** data-heavy tracks.

Implication: we are well-positioned to go **deep on Stages 1 and 2**
(modeling + simulation + data + AI) and ship a clean-but-not-fancy
Stage 3 dashboard. A grounded chatbot on top of our generated data is a
natural high-leverage finishing move.

---

## 7. Open Questions / TODO

- [ ] Receive the Markdown briefing docs from Slack and integrate component-level details here.
- [ ] Decide which component(s) we model first.
- [ ] Decide whether degradation is math-based, regression, or learned (and on what data).
- [ ] Decide simulation tick rate and time horizon.
- [ ] Pick the dashboard stack (Next.js + chart lib? Streamlit? something else?).
- [ ] Decide if/how we wire a grounded chatbot (RAG over generated time series? tool-calling agent over an API?).
- [ ] Confirm submission format and judging criteria.

---

## 8. Architecture Sketch (working draft)

```
                ┌──────────────────────┐
input drivers ─▶│  Degradation Model   │──▶ component health (t)
(env, usage,    │  (math | ML | hybrid)│
 schedule, ...) └──────────────────────┘
                          │
                          ▼
                ┌──────────────────────┐
                │  Simulation Loop     │  ──▶  time-series store
                │  state(t+1) =        │
                │    f(state(t), x(t)) │
                └──────────────────────┘
                          │
                          ▼
                ┌──────────────────────┐
                │  Optional Agent      │  ──▶  modifies inputs
                │  (maintain / tune)   │       (close the loop)
                └──────────────────────┘
                          │
                          ▼
                ┌──────────────────────┐
                │  UX Layer            │
                │  - Dashboard         │
                │  - Grounded Chatbot  │  ──▶  user
                │  - Proactive alerts  │
                └──────────────────────┘
```

---

## 9. Changelog

- **2026-04-25** — Initial draft created from briefing transcript.
  Awaiting Markdown component docs from Slack to expand Stage 1 details.
