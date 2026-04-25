# B7 — AI Maintenance Agent

**Track:** Phase 2 bonus — autonomous maintenance scheduling
**Last updated:** 2026-04-25

---

## TL;DR

Use a **hand-coded heuristic policy**. Threshold health vectors against
per-component cutoffs; fire `run_maintenance` when any component crosses
its critical threshold. Takes ~30 LoC, zero extra dependencies, and
produces a clean side-by-side demo against a no-maintenance baseline.
LLM-as-policy adds latency with no decision-quality benefit here. RL is
too slow to train in 24 h and does not demo well without a training
curve.

---

## Background

The simulation loop already computes a health vector `h = [h_blade,
h_nozzle, h_heater]` ∈ [0, 1]³ every tick. The `Maintenance Level`
driver is already a first-class input to the degradation model; calling
maintenance simply resets it to 1.0 and partially restores health
indices. The agent therefore only needs to decide: given the current
health vector at tick t, call maintenance now or wait?

Framed as RL: observation = h, action ∈ {0 = do_nothing, 1 =
run_maintenance}, reward = uptime (binary: is any component FAILED?).
Episode ends when the first component reaches FAILED, or at a fixed
horizon (e.g. 2000 ticks).

---

## Options considered

| Criterion | Heuristic thresholds | LLM-as-policy | Tiny RL (gymnasium) |
|---|---|---|---|
| **Implementation time** | ~30 min | ~60 min | 3–6 h (env + training) |
| **Dependencies** | None | Anthropic SDK (already in stack) | gymnasium, stable-baselines3 |
| **Decision quality** | Good (domain-tuned) | Good (but opaque) | Potentially best, unreliable to train in time |
| **Latency per tick** | <1 ms | 500–2000 ms | <1 ms (after training) |
| **Demo clarity** | Transparent, explainable | Black-box | Requires training-curve plot |
| **Risk** | Very low | Medium (API cost, prompt tuning) | High (may not converge) |
| **Judges see AI** | Moderate | High | High (if it works) |
| **Integrates with Phase 3 chatbot** | Yes (trivial) | Yes (same LLM call) | Yes (policy file) |

---

## Recommendation

**Use the heuristic policy.** It is predictable, explainable, and the
demo contrast with a no-maintenance baseline is visually compelling even
without an ML model behind it.

To satisfy "judges reward visible AI": wrap the heuristic inside a thin
`MaintenanceAgent` class with an `explain()` method that generates a
one-sentence rationale string (can call the LLM to narrate the decision
after the fact). This gives the AI-visible narrative without putting the
LLM in the decision-critical path.

### Concrete policy spec

Thresholds (tunable; set conservatively so maintenance fires before
CRITICAL):

```
TRIGGER  if min(h) < 0.40          # any component below 40 % health
COOLDOWN 200 ticks                  # never maintain twice inside window
RECOVERY +0.35 to each h_i, capped at 1.0
```

### Pseudocode (~20 LoC)

```python
THRESHOLD = 0.40      # fire maintenance below this health
COOLDOWN  = 200       # ticks between maintenance events

class MaintenanceAgent:
    def __init__(self):
        self.ticks_since_last = COOLDOWN  # start ready

    def act(self, health_vector: list[float]) -> str:
        self.ticks_since_last += 1
        if (min(health_vector) < THRESHOLD
                and self.ticks_since_last >= COOLDOWN):
            self.ticks_since_last = 0
            return "run_maintenance"
        return "do_nothing"

    def explain(self, health_vector: list[float], action: str) -> str:
        worst = min(health_vector)
        return (f"Action={action}. Worst component health={worst:.2f}. "
                f"Threshold={THRESHOLD}. "
                f"Cooldown remaining={max(0, COOLDOWN - self.ticks_since_last)}.")
```

In the simulation loop, at each tick:
1. Get `health_vector` from Phase 1 output.
2. Call `agent.act(health_vector)` → action.
3. If `"run_maintenance"`: set `maintenance_level = 1.0`, apply health
   recovery formula, log event to historian with `run_id` and tick.
4. Record action + rationale in historian for Phase 3 chatbot to cite.

### Demo setup

Run **two scenarios** with identical seed and drivers:

- `run_id = "baseline"`: no agent, `maintenance_level` constant at 0.5.
- `run_id = "agent"`: `MaintenanceAgent` active.

Plot both health curves on the same time axis. Mark agent maintenance
events as vertical lines. Expected result: agent run lasts 30–60 %
longer before first FAILED component. This is the "AI saves uptime"
visual.

---

## Open questions

1. Should maintenance cost a tick of downtime (reward penalty)? If yes,
   the heuristic threshold may need tuning to avoid over-maintaining.
2. Cooldown length — 200 ticks is a guess; calibrate after seeing how
   fast the fastest-degrading component drops.
3. If time allows post-core-build: add an LLM narrator call in the Phase
   3 chatbot that explains *why* the agent fired at a given tick, citing
   the historian row. Zero risk, high judge visibility.

---

## References

- Gymnasium basic usage: https://gymnasium.farama.org/introduction/basic_usage/
- Anthropic — Building effective agents: https://www.anthropic.com/research/building-effective-agents
- DataHeadHunters — Threshold-based predictive maintenance in Python: https://dataheadhunters.com/academy/how-to-use-python-for-predictive-maintenance-in-manufacturing/
- DataCamp — Reinforcement learning with Gymnasium: https://www.datacamp.com/tutorial/reinforcement-learning-with-gymnasium
- OpenAI — A practical guide to building agents (PDF): https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf
