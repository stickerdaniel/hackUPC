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

### Action vocabulary — three kinds, not binary

Per `domain.events.OperatorEventKind`, operator actions are **not** binary. The agent picks from three:

| Action | State change | Example |
| :--- | :--- | :--- |
| `TROUBLESHOOT` | none — only sets `last_inspected_tick` and writes an event row | sensor reads weird; operator inspects to confirm/refute fault |
| `FIX` | partial recovery (component-specific) | clean nozzle, calibrate sensor, re-grease rail |
| `REPLACE` | full reset (component-specific) | new blade, new wiper, new sensor element |

The action also targets a **specific component** (e.g. `FIX(component="blade")`), not the whole machine — so the policy's action space is `(action_kind, component_id)` plus a "do nothing" sentinel.

### Primary — Heuristic policy

```python
def decide(observed: ObservedPrinterState, hours_since_maint: dict[str, float]) -> Action | None:
    # Reactive: any component below DEGRADED gets a FIX (or REPLACE if CRITICAL/UNKNOWN).
    for cid, c in observed.components.items():
        h = c.observed_health_index
        if c.observed_status == OperationalStatus.UNKNOWN:
            return Action(TROUBLESHOOT, cid)         # diagnose first, don't act blind
        if h is not None and h < 0.15:
            return Action(REPLACE, cid)
        if h is not None and h < 0.40:
            return Action(FIX, cid)
    # Scheduled: monthly preventive FIX of the most-aged component.
    worst = min(hours_since_maint, key=hours_since_maint.get)
    if hours_since_maint[worst] > 30 * 24 and (observed.components[worst].observed_health_index or 1) < 0.60:
        return Action(FIX, worst)
    return None
```

Three rules in priority order: (1) **`TROUBLESHOOT` first when the sensor says `UNKNOWN`** — never act blind on an absent/stuck sensor (this is the §3.4 sensor-fault-vs-component-fault discipline encoded as policy); (2) **reactive `FIX` / `REPLACE`** based on *observed* health crossings (the policy only sees the observed view per §3.4); (3) **scheduled preventive `FIX`** on the longest-unmaintained component.

### Stretch — LLM-as-policy

- Same signature: `decide(observed: ObservedPrinterState, hours_since_maint) -> {action: Action | None, rationale: str}`.
- **Provider: OpenRouter** via the OpenAI-compatible `/chat/completions` endpoint. Hit it directly with `httpx` (already a dep) — no extra SDK. Model selection is one env var (`LLM_MODEL`), so the demo can A/B `google/gemma-4-31b-it`, `anthropic/claude-sonnet-4.6`, `openai/gpt-5`, etc. with no code changes. Default model: `google/gemma-4-31b-it` (cheap, native function calling, strong instruction-following).
- Prompt: system message with the four drivers, the six **observed** component states (health + status + sensor_note), hours-since-maint per component, the cost model, and the action vocabulary (`TROUBLESHOOT / FIX / REPLACE / null`). Ask for JSON `{action_kind, component_id, reason}` via `response_format: {"type": "json_object"}`.
- The LLM gets the §3.4 advantage: it can see `sensor_note: "drift"` on the heater and the temperature_sensor, conclude the fault is in the sensor not the heater, and emit `TROUBLESHOOT(sensor)` followed next tick by `REPLACE(sensor)` with the rationale stored to events.
- **Rate-limit:** call once per simulated *hour*, cache between. ~4380 calls per run, well under $1 on Gemma 4 31B; A/B against Sonnet 4.6 still under a few dollars.
- The `rationale` field is gold for the demo: every event in the historian carries a one-sentence justification queryable as a stored attribution.

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

### Maintenance effect model (per-component, per-action reset rules)

When `Action(kind, component_id)` fires at tick `t`, mutate the targeted component's state as follows. **`TROUBLESHOOT` never mutates state** — only writes an event row and sets `last_inspected_tick`. **`FIX` is partial**, **`REPLACE` is full**.

| Component | `FIX` (partial) | `REPLACE` (full) | Cost / downtime |
| :--- | :--- | :--- | :--- |
| **Blade** | n/a — blade is not field-repairable; FIX falls through to REPLACE | `D ← 0`, `t_eff ← 0`, `thickness ← 0.95·h0` | 2 h sim |
| **Rail** | `D_lube ← 0`, `D_corr ← 0.5·D_corr`, `D_pit` unchanged (permanent) | `D ← 0`, `t_eff ← 0`, `alignment_error ← 0` | 1 h FIX / 4 h REPLACE |
| **Nozzle** | clean cycle: `clog% ← clog% · (1 − cleaning.efficiency)`, `D_fatigue × 0.5` | full plate swap: `clog% ← 0`, `D ← 0`, `t_eff ← 0` | 1 h FIX / 3 h REPLACE |
| **Cleaning** | wiper-blade swap: `cumulative_cleanings ← 0`, `H_use ← 1.0`, `shelf_age ← 0` | full station: same as FIX (already a full reset of the wear path) | 0.5 h |
| **Heater** | de-rate + recalibrate: `D ← 0.5·D`, `drift_frac ← 0.5·drift_frac` | element swap: `R ← R_0`, `D ← 0`, `t_eff ← 0` | 1 h FIX / 4 h REPLACE |
| **Sensor** | calibrate: `bias_C ← 0`, `noise_sigma_C` unchanged (connector oxidation persists) | `bias_C ← 0`, `noise_sigma_C ← 0`, `t_eff ← 0`, redraw initial bias sign | 0.25 h FIX / 1 h REPLACE |

Notes baked into these rules:

1. **Blade and cleaning interface have no meaningful FIX** — they're consumables. The policy emits `REPLACE`; if it asks for `FIX` we route it to `REPLACE` and log a note.
2. **Rail pitting is permanent.** Even `REPLACE` is rare and expensive; `FIX` only addresses the lubricant + corrosion damage.
3. **Sensor `FIX` doesn't fix noise.** Connector oxidation/work-hardening is irreversible without replacement — calibration only zeros the bias offset.
4. **Maintenance writes one `OperatorEvent` row** per action via `domain.events.OperatorEvent`, with `kind ∈ {TROUBLESHOOT, FIX, REPLACE}` and the magnitude / rationale in `payload`.

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
