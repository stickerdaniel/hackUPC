# 23 — Improvement Roadmap

> Concrete realism upgrades, ranked by gain per hour. Each item names the file, the change, the realism gain, and the test impact.

---

## How to read this file

Tier 1 = quick wins (≤ 1 h total). Tier 2 = component-level upgrades. Tier 3 = stretch additions. Tier 4 = specified, not built.

Some Tier 1 items have already been applied in this session (see the **Status** column). The rest are queued for next development cycle.

---

## Tier 1 — Quick wins (≤ 1 h total, high realism gain per minute)

### B1.1 — Reconcile status thresholds — APPLIED

- **File**: `sim/src/copilot_sim/engine/aging.py:26-28`
- **Change**: `HEALTH_DEGRADED = 0.40`, `HEALTH_CRITICAL = 0.15` (match doc 04 + README).
- **Why**: removes the only doc/code inconsistency. Code was 5 pp more aggressive than docs.
- **Time**: 15 min
- **Status**: ✅ **applied in this session**.
- **Test impact**: smoke tests pass with the new thresholds (verified with `uv run pytest`).

### B1.2 — Wire `cleaning_efficiency` into nozzle FIX

- **File**: `sim/src/copilot_sim/components/nozzle.py:147`, `sim/src/copilot_sim/engine/engine.py:81-82` (apply_maintenance dispatch), `sim/src/copilot_sim/policy/heuristic.py:90-102` (action factory)
- **Change**: Pass `cleaning_efficiency` through `MaintenanceAction.payload`. Replace `cleaning_proxy = 0.7` with `payload.get("cleaning_efficiency", 0.7)`. The policy's `_action()` reads `observed.components["cleaning"].observed_health_index` and stuffs it in payload.
- **Why**: makes the cleaning↔nozzle pair a real two-way coupling at maintenance time. Worn cleaner → worse FIX recovery on nozzle.
- **Time**: 10 min
- **Status**: queued (skipped pre-pitch to avoid breaking tests on a fragile day).
- **Test impact**: `tests/engine/test_apply_maintenance.py` — add assertion that low cleaning_efficiency reduces clog recovery on nozzle FIX.

### B1.3 — Add explicit heater→sensor reverse arrow

- **File**: `sim/src/copilot_sim/components/sensor.py:93`
- **Change**: read `heater_drift_amp = 1.0 + 0.5 * coupling.factors.get("heater_drift_frac", 0.0)` and multiply into `bias_increment`.
- **Why**: closes the explicit sensor↔heater bidirectional loop the README claims. Currently the loop closes only indirectly through `temperature_stress_effective`.
- **Time**: 5 min
- **Status**: queued.
- **Test impact**: existing sensor smoke + driver-coverage tests — verify monotonicity in heater_drift still holds.

### B1.4 — Use `Environment.cumulative_cleanings` in cleaning step

- **File**: `sim/src/copilot_sim/components/cleaning.py:75`, `sim/src/copilot_sim/simulation/loop.py` (env update)
- **Change**: cleaning step reads `env.cumulative_cleanings` (already a field, currently unused) and increments based on real cleaning events, not a runtime-hours heuristic. The loop maintains the counter.
- **Why**: power-law wear-per-cycle is now driven by *actual cycles*, matching doc 18's intent.
- **Time**: 10 min
- **Status**: queued.
- **Test impact**: `tests/components/test_cleaning_smoke.py` — update to verify monotonic counter behavior.

### B1.5 — Enable chaos in one demo scenario — APPLIED

- **File**: `sim/scenarios/barcelona-with-chaos.yaml` (new, copy of barcelona-baseline.yaml).
- **Change**: Set `chaos.enabled: true`.
- **Why**: lets you claim Stochastic Realism bonus without modifying the deterministic baseline.
- **Time**: 1 min
- **Status**: ✅ **applied in this session**.
- **Test impact**: scenario validator already covers this (`test_loop.py`, `test_full_run.py`).

### B1.7 — Fix heater operating temperature — APPLIED

- **File**: `sim/src/copilot_sim/components/heater.py`
- **Change**: `SELF_HEATING_C` raised from 50 to 130 so operating temperature reaches ~150 °C (S100 binder cure) at full load. AF goes from ~0.003 to ~1 at full load, ~0.04 at typical load.
- **Why**: under the old constant, the heater's Arrhenius drift physics contributed almost nothing relative to the Weibull baseline at any realistic horizon. Pitch-time defense of "Arrhenius drift" was hollow because the visible decay was actually calendar aging.
- **Time**: 5 min
- **Status**: ✅ **applied in this session**. All 92 tests pass. Heater final health in barcelona-18mo dropped from 0.655 → 0.558.
- **Test impact**: none.

### B1.8 — Fix sensor operating temperature — APPLIED

- **File**: `sim/src/copilot_sim/components/sensor.py`
- **Change**: `operating_K` now uses `ambient_C + SELF_HEATING_C * load_eff` (mirroring heater) instead of just `ambient_C`. Same `SELF_HEATING_C = 130`. AF goes from ~0.0004 to ~0.04 at typical Barcelona load, ~1.5 at Phoenix high-load.
- **Why**: a PT100 RTD measuring the binder cure zone is mounted near the heater, not in ambient air. The old code modeled the sensor as if it lived in the room. With the fix, the §3.4 sensor-fault story fires in 18 months under hot conditions (Phoenix shows sensor DEGRADED at tick 77 with bias 0.77 °C; it appears as a top-3 cascade factor in nozzle FAILED attribution). Barcelona still shows stable sensor behaviour — the climate-driven what-if story is intact.
- **Time**: 5 min
- **Status**: ✅ **applied in this session**. All 92 tests pass.
- **Test impact**: none.

### B1.9 — Add 18-month scenarios — APPLIED

- **Files**: `sim/scenarios/barcelona-18mo.yaml` (new), `sim/scenarios/phoenix-18mo.yaml` (new).
- **Change**: 78-tick versions of the baseline scenarios (5-year was visually busy; 18 months reads as one full failure cycle per component for the demo).
- **Time**: 5 min
- **Status**: ✅ **applied in this session**.

### B1.6 — Add nozzle→cleaning reverse arrow

- **File**: `sim/src/copilot_sim/components/cleaning.py:80-82`
- **Change**: in `step()`, add `nozzle_load_amp = 1.0 + 0.4 * coupling.factors.get("nozzle_clog_pct", 0.0)` and multiply into `wiper_increment` (clogged nozzles → wiper does more work).
- **Why**: closes the cleaning↔nozzle two-way loop. Makes the printhead pair a real feedback system.
- **Time**: 15 min
- **Status**: queued.
- **Test impact**: `test_cleaning_smoke.py` driver coverage.

**Tier 1 total ≈ 56 min**. Two of six applied in this session (B1.1 + B1.5). After applying all six, the README's "3 two-way loops" claim is **actually true in code**.

---

## Tier 2 — Component-level upgrades (2–4 h each)

### B2.1 — Multi-mechanism nozzle clog model

- **File**: `sim/src/copilot_sim/components/nozzle.py`
- **Change**: Split the single Poisson clog process into three independent processes:
  - `λ_binder = λ_b·(1 + 4·humid_eff)·(2 − cleaning_efficiency)` (binder ingress)
  - `λ_powder = λ_p·(1 + 2·(1 − powder_spread_quality))` (powder migration; reads the new factor)
  - `λ_evap = λ_e·(1 + 0.5·temp_eff)` (binder evaporation in idle nozzles)
  - Total clog increment = sum of three Poisson draws, each with its own per-event severity.
- **Why**: matches the literature on inkjet failure modes. Each mechanism responds to a different driver, exposing more *Systemic Interaction*. The Microelectronics Reliability 2004 paper explicitly enumerates these three.
- **Time**: 3 h
- **Realism gain**: large — defensible to judges who know the field.
- **Test impact**: regenerate Poisson event-count fixtures.

### B2.2 — Add per-nozzle redundancy + drop-detector observable

- **File**: `sim/src/copilot_sim/components/nozzle.py`, `sim/src/copilot_sim/sensors/factories.py`
- **Change**: Add `nozzles_failed_pct ∈ [0,1]` as a separate metric. Each clog event has a small probability of permanently killing a nozzle (vs reversibly clogging it). The printhead is FAILED at `nozzles_failed_pct ≥ 0.05` (5 % dead, matching HP whitepaper redundancy).
- Add `OpticalDropDetector` sensor model that exposes `nozzles_failed_pct` as the observed metric — this is HP's actual service-station signal.
- **Why**: matches HP's published architecture (4× redundancy + optical drop detection). Real demo differentiator.
- **Time**: 4 h
- **Realism gain**: huge. Lets you say "HP's own service signal is in our model" with a citation.

### B2.3 — Bidirectional rail↔blade coupling via shared mechanical load

- **File**: `sim/src/copilot_sim/engine/coupling.py`, `sim/src/copilot_sim/components/blade.py`, `sim/src/copilot_sim/components/rail.py`
- **Change**: Add coupling factor `carriage_friction = 0.5·rail_friction + 0.3·blade_edge_roughness`. Both blade and rail step functions read it: blade gets `(1 + 0.3·carriage_friction)` on its `k_amplifier`; rail gets `(1 + 0.2·carriage_friction)` on its `damage_increment`. Plus add `coupling.factors["carriage_friction"]` for attribution queries.
- **Why**: makes the recoating pair a real bidirectional loop (currently they only meet through the shared `powder_spread_quality` output sink).
- **Time**: 3 h
- **Realism gain**: moderate. Most complex component pair; hardest to defend without something like this.

### B2.4 — Sensor sign randomization + 1/f noise

- **File**: `sim/src/copilot_sim/components/sensor.py`
- **Change**: Bias sign chosen at `initial_state()` from a Bernoulli(0.5) draw using a config-seeded RNG (so it's deterministic per scenario but varied across seeds). 1/f noise component added: `noise_sigma_eff = noise_sigma × (1 + 0.3·sin(2π·age/52))`.
- **Why**: real PT100 RTDs drift either sign; pure-Gaussian noise is unrealistic. Subtle but adds defensibility.
- **Time**: 2 h
- **Realism gain**: small but tightens the "we know our sensors" answer.

### B2.5 — Heater catastrophic burnout mode

- **File**: `sim/src/copilot_sim/components/heater.py`
- **Change**: Add Bernoulli per-tick burnout probability `p_burnout = 0.001·max(0, drift − 0.05)²` (only kicks in past 5 % drift; quadratic in excess). On a positive draw, instantly set drift to 0.15 (FAILED). Resets only via `REPLACE`.
- **Why**: real heating elements fail suddenly via hot-spot oxidation breakthrough, not always smoothly. Standard reliability literature distinguishes "drift to spec limit" from "catastrophic burnout".
- **Time**: 2 h
- **Realism gain**: moderate. Makes the heater a more interesting component for the demo.

### B2.6 — Train and integrate the AI surrogate

- **File**: `sim/src/copilot_sim/engine/surrogate.py` (new), `sim/src/copilot_sim/components/heater.py`, `sim/src/copilot_sim/cli.py`, `scripts/train_surrogate.py` (new)
- **Change**: Train sklearn `MLPRegressor((32,32,32), tanh)` on 20k Latin-Hypercube samples of `(temp_eff, humid_eff, load_eff, age, prev_drift) → drift_increment`. Joblib-dump to `data/surrogate.joblib`. Add `--heater-model={analytic,nn}` to the CLI. Acceptance gate: MAE ≤ 2 % vs analytic on a held-out test set.
- **Why**: the *AI-Powered Degradation Model* bonus from stage-1.md. Demo deck slide: "two lines that overlap perfectly".
- **Time**: 4 h
- **Realism gain**: it's a *bonus*, not realism per se — but it directly hits a stage-1 evaluation pillar.

---

## Tier 3 — Stretch additions (multi-hour, polish or differentiation)

### B3.1 — Live weather adapter

- **File**: `sim/src/copilot_sim/drivers_src/weather.py` (new), `sim/src/copilot_sim/simulation/scenarios.py` (driver registry)
- **Change**: Implement `OpenMeteoDriver` reading cached JSON from `data/weather/{barcelona,phoenix}.json`. Subclass of `DriverGenerator`. Maps real `temperature_2m` and `relative_humidity_2m` to `temperature_stress` and `humidity_contamination` via min-max normalization. Add `kind: open_meteo_archive` to YAML schema.
- **Why**: the Live Weather bonus from stage-1.md is researched but not built. With cached JSON in-repo, the demo never depends on the network.
- **Time**: 4 h
- **Realism gain**: large for the demo — you can say "real Barcelona weather, not a sin curve".

### B3.2 — Thermal mass / first-order delay on heater

- **File**: `sim/src/copilot_sim/components/heater.py`
- **Change**: Add `effective_operating_C` state metric. Per tick: `effective_operating_C ← effective_operating_C + α·(target_operating_C − effective_operating_C)`, α = 0.3.
- **Why**: real heaters have minutes-scale lag responding to ambient changes. Currently instant.
- **Time**: 2 h
- **Realism gain**: small at dt=1 week granularity; matters more if dt drops to hours.

### B3.3 — RUL forecasting table in historian

- **File**: `sim/src/copilot_sim/historian/schema.sql`, `sim/src/copilot_sim/historian/writer.py`, `sim/src/copilot_sim/components/*.py`
- **Change**: Add `predictions` table. Each component step emits a `remaining_ticks_to_FAILED` estimate based on current health trajectory (linear extrapolation or analytical Weibull inverse). Loop writes to `predictions(run_id, tick, component_id, remaining_ticks, confidence_band)`.
- **Why**: a true "predictive maintenance" twin produces forecasts, not just current state. Strong differentiator for the deck.
- **Time**: 3 h
- **Realism gain**: large for the *intelligence* dimension, less for *physics*.

### B3.4 — Chaos calibration sweep + auto-tune

- **File**: `scripts/calibrate_chaos.py` (new)
- **Change**: Run the simulator across 200 seeds with chaos enabled. Tune `temp_spike_lambda_per_year` etc. so exactly ~33 % of seeds hit CRITICAL inside 6 months (matches README's stated calibration target).
- **Why**: the README claims calibration but doesn't show the sweep. Doing it makes the bonus pillar more defensible.
- **Time**: 3 h

### B3.5 — Diurnal temperature cycle

- **File**: `sim/src/copilot_sim/drivers_src/generators.py`
- **Change**: Currently `SinusoidalSeasonalTemp` only has yearly cycle + weekly wobble. Add a diurnal sub-cycle. At dt = 1 week this washes out, but with a finer dt it would matter.
- **Time**: 1 h

### B3.6 — Material-mode selector for cleaning

- **File**: `sim/src/copilot_sim/components/cleaning.py`, scenario YAML
- **Change**: Per-scenario `material_mode: rubber | polymer` parameter that switches between two power-law exponent values. Different curves expose more variability for what-if scenarios.
- **Time**: 2 h

---

## Tier 4 — Specified, not built (out of scope for this iteration)

### LLM-as-policy

`docs/research/09-maintenance-agent.md` specifies a stretch path: same `decide()` signature, but the body calls an OpenRouter model via `httpx`. Rationale stored in event payload. Default model `google/gemma-4-31b-it`, A/B against `anthropic/claude-sonnet-4.6`.

### RL maintenance agent

Doc 09 specifies a `MetalJetMaintEnv(gym.Env)` with `Box([0,0,0,0,0], [1,1,1,1e6,1e5])` observation, `Discrete(2)` action, and a reward of `+1 alive / -100 fail / -2 maintenance`. Skipped explicitly for the 36-h hackathon — the env spec exists so a judge asking "could you train an RL policy?" gets a precise answer.

### Phase 3 — Chatbot, voice, frontend

Deferred per `TRACK-CONTEXT.md §8`. Research preserved in `docs/research/10-13.md`. The simulator's historian schema (especially `coupling_factors_json` + `events`) is **already shaped to support the Phase 3 chatbot's grounded-RAG queries** when that work resumes.

---

## Suggested execution order

If the team has another full development day:

1. **Apply remaining Tier 1** (4 items × ~10 min ≈ 40 min). Closes the documented-not-implemented cascades. Single highest-leverage bucket.
2. **Tier 2.1 — Multi-mechanism nozzle clog** (3 h). Best realism gain per hour for a single component.
3. **Tier 2.6 — AI surrogate training** (4 h). Hits the *AI-Powered Degradation* bonus pillar.
4. **Tier 3.1 — Live weather adapter** (4 h). Hits the *Live Environmental Data* bonus pillar.
5. **Tier 2.2 — Per-nozzle redundancy + drop detector** (4 h). Matches HP's published architecture exactly.

Total ≈ 16 hours of work to close every documented realism gap and add three bonus-pillar wins.

If only 1 hour is available: apply remaining Tier 1 (~40 min) and call it done — the README claims become true in code, the cleaning↔nozzle pair becomes adaptive, and chaos demo is enabled.

---

## Cross-references

- Per-component realism notes that motivate each item: each file in [`components/`](components/).
- The audit that identified these gaps: [`22-realism-audit.md`](22-realism-audit.md).
- Research backing: `docs/research/22-printer-lifetime-research.md` for parameter anchors, `docs/research/05-cascading-and-ai-degradation.md` for the AI surrogate spec, `docs/research/07-weather-api.md` for the live weather plan, `docs/research/09-maintenance-agent.md` for the LLM/RL specs.
