# 09 — AI Maintenance Agent (Heuristic vs LLM-as-Policy vs RL)

> Phase 2 bonus: an agent that decides **when** to trigger maintenance to maximise uptime. This doc picks the approach, locks the env spec, and defines what a maintenance event does to the state.

## TL;DR

- **Primary: rule-based heuristic.** One screenful of code, deterministic, defensible, and the chart it produces ("no agent vs heuristic") is already a winning slide.
- **Stretch: LLM-as-policy** wired as a one-button A/B against the heuristic. Same simulator, same scenario, swap the `decide()` callable. Hits the "AI meets reality" theme without an RL training run.
- **Skip RL for the 36 h.** Gymnasium + PPO is realistic on paper but is a time sink (reward shaping, hyperparams, instability, sim-speed). We **do** specify the env so a judge asking "could you train an RL policy?" gets a precise answer, and so the same `Env` can wrap both the heuristic and the LLM for a fair comparison.
- **Maintenance effect: per-component reset rules** (full / partial / driver-only), aligned with doc 04's open question on reset semantics.

## Background — three approaches honestly compared

| Approach | Build cost (h) | Demo strength | Risk | Theme fit |
| :--- | :--- | :--- | :--- | :--- |
| **Heuristic** (e.g. `min(H) < 0.4 → maintain`) | 1–2 | High — instantly readable, easy to A/B against "no agent" | None | Low (it's just `if`) |
| **LLM-as-policy** (per-tick prompt → `do_nothing` / `maintain`, with a 1-sentence rationale) | 3–5 | Very high — agent **explains** each decision, plugs straight into the Phase 3 chatbot story | Latency + cost; needs a tick-rate cap (e.g. decide every N ticks, not every tick) | High |
| **RL (PPO/DQN on Gymnasium)** | 8–16+ | Impressive *if* it converges | Reward shaping, training stability, sim throughput, debug time. Easy to ship a policy that's worse than the heuristic and not realise it | Medium — judges have seen it before |

Two-person team, 36 h, Phase 3 is the strategic bet (see TRACK-CONTEXT §8). The agent should be a **slide and a chart**, not a research project.

## Decision

### Primary — Heuristic policy

```python
def decide(state, hours_since_maint) -> Action:
    h = state.health  # dict component -> [0, 1]
    if any(v < 0.40 for v in h.values()):       return MAINTAIN
    if hours_since_maint > 30 * 24 and min(h.values()) < 0.60:  return MAINTAIN
    return DO_NOTHING
```

Two rules: a **reactive** trigger on any DEGRADED component (matches the 0.40 status boundary in doc 04) and a **scheduled** trigger to capture the "preventive maintenance window" story. Both thresholds are config, not magic numbers.

### Stretch — LLM-as-policy

- Same signature: `decide(state, hours_since_maint) -> {action, rationale}`.
- Prompt: system message with the four drivers + the three component health values + hours-since-last-maint + the cost model (`+1/tick alive, −100/FAILED, −2/maintain`). Ask for JSON `{action: "do_nothing"|"maintain", reason: str}`.
- **Rate-limit:** call once per simulated *hour* (or every 10 ticks if `dt = 6 min`), cache the last decision in between. Otherwise a 6-month run = thousands of calls.
- The `reason` field is gold for Phase 3: every maintenance event in the historian carries a one-sentence justification, which the chatbot can quote verbatim with full grounding.

### Gymnasium env spec (locked, even if we don't train)

Confirming the user's proposal with three small refinements:

```python
class MetalJetMaintEnv(gym.Env):
    # observation: 5-vector of floats
    observation_space = Box(
        low=np.array([0, 0, 0, 0,    0  ], dtype=np.float32),
        high=np.array([1, 1, 1, 1e6, 1e5], dtype=np.float32),
    )
    # [h_blade, h_nozzle, h_heater, sim_hours, hours_since_last_maint]

    action_space = Discrete(2)  # 0 = do_nothing, 1 = maintain

    def step(self, action):
        ...
        return obs, reward, terminated, truncated, info
        # Gymnasium ≥0.26: terminated + truncated, not `done`.
```

Reward (kept close to the brief, with two tweaks):

| Term | Value | Why |
| :--- | :--- | :--- |
| Tick alive (all components > 0.15) | **+1** | Aligned with the FAILED threshold in doc 04 (≤ 0.15), not 0.10. Keeps a 1-step buffer. |
| Any component FAILED | **−100**, `terminated=True` | Big, terminal — RL needs a strong terminal signal. |
| Maintenance event | **−2** | As proposed. Discourages spamming. |
| Optional shaping | **+0.1 · min(health)** per tick | Densifies reward; turn off for a clean baseline. |

Episode: 180 simulated days (≈ matches Weibull η in doc 04), `dt = 1 h` ⇒ 4 320 steps. `truncated=True` at horizon.

### Maintenance effect model (per-component reset rules)

When `action = MAINTAIN` fires at tick `t`, mutate state as follows. This resolves doc 04's open question on reset semantics.

| Component | Driver damage `D` | Baseline age `t_eff` | Physical metric | Cost / downtime |
| :--- | :--- | :--- | :--- | :--- |
| **Recoater blade** | `D ← 0` (fresh blade) | `t_eff ← 0` | `thickness ← 0.95 · h0` (new blade, slight install play) | 1 maintenance unit; 2 h sim downtime |
| **Nozzle plate** | `D ← 0.2 · D` (clean cycle, 80% recovery) | unchanged | `clog% ← 0`, fatigue accumulator `× 0.5` | 1 unit; 1 h downtime |
| **Heating element** | `D ← 0.5 · D` | unchanged | `resistance_drift ← 0.5 · current_drift` | 1 unit; 1 h downtime (no field repair, only de-rating + recalibration) |

Two policy choices baked in:

1. **Blade is replaceable, heater is not.** Field-realistic. Heater "maintenance" is a calibration, not a swap, so `D` only halves.
2. **Maintenance is atomic across all three components.** Simpler than per-component actions, keeps `action_space = Discrete(2)`. A future stretch could expand to `Discrete(4)` (none / blade / nozzle / heater) but it's not needed for the demo chart.

### The killer demo chart

Same scenario (same seed, same drivers, same Weibull params), three runs overlaid:

1. **No agent** — never maintain. Shows natural failure timeline.
2. **Heuristic agent** — rules above.
3. **LLM agent** — stretch.

Plot: x = simulated days, y = `min(component_health)`, with FAILED markers as red Xs and maintenance events as small triangles on each line. Title: *"Same printer, three policies, three uptimes."* KPIs in the legend: `uptime_%`, `# maint events`, `# failures`, `total reward`.

Implementation: a single `run_scenario(seed, policy, drivers) -> DataFrame` function, called three times, written to the same SQLite historian with a `policy` column. Phase 3 chatbot can then answer "why did the LLM agent maintain on day 47?" by quoting the stored `rationale`.

## Why this fits our case

- **Reuses Phase 1+2 wholesale.** The agent is just another caller of the engine; no new physics.
- **Heuristic is unfailable.** Even if the LLM call breaks at demo time, the chart with two lines (no-agent vs heuristic) still tells the story.
- **LLM rationale → Phase 3 grounding.** Every maintenance event has a stored, citeable reason — straight into the Evidence Citation requirement.
- **Env spec is a credible answer to "did you consider RL?"** without committing the hours.
- **Aligns with doc 04 thresholds** (FAILED at 0.15, DEGRADED at 0.40) so the agent and the status enum tell the same story.

## References

1. Farama Foundation — *Gymnasium Env API* (observation/action spaces, `step` returns `(obs, reward, terminated, truncated, info)`). https://gymnasium.farama.org/api/env/
2. Farama Foundation — *Create a Custom Environment*. https://gymnasium.farama.org/introduction/create_custom_env/
3. *Deep-Reinforcement-Learning-Based Predictive Maintenance Model for Effective Resource Management in Industrial IoT* (PPO-LSTM, 53–65% improvement over baselines). https://ieeexplore.ieee.org/document/9528837/
4. *Predictive Maintenance using Deep Reinforcement Learning* (IEEE 2024). https://ieeexplore.ieee.org/document/10730350/
5. *An empirical study of the naïve REINFORCE algorithm for predictive maintenance* (Discover Applied Sciences, 2025). https://link.springer.com/article/10.1007/s42452-025-06613-1
6. *Reinforcement Learning for Autonomous Process Control in Industry 4.0* (Taylor & Francis, 2024). https://www.tandfonline.com/doi/full/10.1080/08839514.2024.2383101
7. Doc 04 in this repo — *Aging Baselines and Normalization Layer* (status thresholds, multiplicative composition, reset-semantics open question this doc closes). [`./04-aging-baselines-and-normalization.md`](./04-aging-baselines-and-normalization.md)

## Open questions

- **LLM cadence:** decide every sim-hour or only when any component crosses DEGRADED (0.75)? Event-triggered is cheaper and more defensible; per-hour is more "agentic" for the demo. Bias: event-triggered with a hard "at least once per 24 sim-hours" floor.
- **Per-component vs atomic maintenance:** keep `Discrete(2)` for the demo. If we have time, expand to `Discrete(4)` and let the LLM pick *which* component — much better story, +2 h work.
- **Cost asymmetry:** is `−100` the right failure cost? In real ops a FAILED nozzle vs FAILED heater have very different consequences (scrap part vs full furnace shutdown). Easy to extend `info["fail_cost"]` per component if a judge probes.
- **Stochastic drivers in scenario:** the comparison chart only means something if all three policies see *the same* driver trajectory. Lock the seed; document it in the run metadata.
- **RL fallback path:** if Phase 3 ships early (unlikely but), `stable-baselines3` PPO on this env is a ~2 h experiment. Document the result either way — even a non-converged PPO curve is a legitimate "we tried, here's why heuristic wins at this horizon" slide.
