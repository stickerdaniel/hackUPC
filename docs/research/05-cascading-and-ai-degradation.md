# Cross-Component Cascade + AI-Surrogate Degradation Model

## TL;DR

Two cheap Phase-1 bonuses that buy real "Complexity & Innovation" points.

1. **Cascade link (recommended):** when the recoater blade's `loss_frac > 0.4` (i.e. status ≥ CRITICAL, health < 0.3), inject `cascade_C = 0.5 · loss_frac` into the nozzle plate's effective contamination driver: `C_nozzle_eff = clamp(C_input + 0.5 · loss_frac, 0, 1)`. A worn blade drags metal fines and uneven layers into the bed; the printhead immediately feels it as a higher clog hazard. The hook is already foreshadowed at the bottom of `01-recoater-blade-archard.md`.
2. **AI surrogate:** replace the analytic Arrhenius/electrical-degradation function for the **Heating Elements** with a small **sklearn `MLPRegressor`** (3 hidden layers, 32 units, `tanh`) trained on **20 000 synthetic samples** generated from the analytic formula itself. Train/val/test = 70/15/15. Acceptance gate: **≤ 2 % MAE on health-delta vs. analytic** over the test set.
3. **Pitch line for the deck:** *"One of our three components is no longer a hand-written formula — it is a learned regressor that matches the physics within 2 % and runs in microseconds. The twin's brain is partly analytic, partly learned, and the loop doesn't care which."*

## Background

**Cascading failures** are well-documented in binder jetting. Reviews of BJ defect taxonomies show that uneven powder spreading from a worn recoater produces local density gradients and trapped fines, and that **smaller particles and contaminated powder are a primary cause of printhead nozzle clogging** (Wevolver BJ guide; ScienceDirect BJ defects review; MIT lab-scale BJ testbed). One-way coupling — blade health drives a contamination-like input to the nozzle — is the cleanest, judge-defensible version. Two-way coupling (nozzle clog feeding back to blade) exists in reality but adds little demo value and risks oscillation in a 36-hour build.

**Surrogate / data-driven degradation models** are a standard move in the predictive-maintenance literature: train a small NN on physics-generated data, ship the NN, keep the formula as ground truth (arXiv 2401.06821 *Surrogate Neural Networks for Aircraft Predictive Maintenance*; PMC *Predicting System Degradation with a Guided NN*; Nature Comms *PINN for Li-ion battery degradation*). A 3-layer MLP on a smooth Arrhenius-shaped manifold is over-spec'd in the best way: it will fit, and we can prove parity with one chart.

## Decision

### 1. Cascade link spec — Blade → Nozzle (one-way)

| Item | Value |
|---|---|
| Trigger | `blade.loss_frac > 0.4` (equivalent to blade `HI < 0.2`, status ≥ CRITICAL) |
| Below trigger | linear ramp `cascade_C = 0.5 · loss_frac` already active from `loss_frac = 0` (so the cascade is *continuous*, the threshold is only how we describe it in the deck) |
| Driver patched | nozzle plate's contamination input only |
| Formula | `C_nozzle_eff = min(1.0, C_driver + 0.5 · blade.loss_frac)` |
| Wiring | applied in the Phase-1 step function **after** the blade update and **before** the nozzle update; deterministic, no extra state. |

**Worked numbers.** A nominal blade at 6 months sits at `loss_frac ≈ 0.4` → adds `+0.20` to the nozzle's `C`, roughly the difference between "clean lab" and "dusty shop". A failed blade (`loss_frac = 0.5`) caps the cascade at `+0.25`. The nozzle still survives a fresh blade and still fails fast under a worn one — exactly the story the demo needs to tell.

**Alternative (in case the blade→nozzle link feels too on-the-nose):** **heating-element resistance ↑ → temperature stress driver ↑ → nozzle thermal fatigue + remaining heaters age faster.** Spec: `T_stress_eff = T_stress + 0.3 · (1 − heater.HI)`. Same shape (one-way, single multiplier, single threshold), different physics story (a burnt-out heater forces neighbours to overshoot to hold setpoint). Pick this one if a judge already pushed back on the blade story.

### 2. AI surrogate spec — Heating Elements

| Item | Value |
|---|---|
| Component replaced | Heating Elements (Arrhenius-driven electrical degradation) |
| Model class | **sklearn `MLPRegressor`** — Option B |
| Architecture | hidden layers `(32, 32, 32)`, activation `tanh`, solver `adam`, `max_iter=2000`, `random_state=42` |
| Inputs (features) | `[prev_HI, prev_resistance_norm, T_stress, humidity, load, maintenance, dt]` (7 features) |
| Output (target) | `Δresistance_norm` per tick (regress the *delta*, not the absolute state — easier to fit, keeps the loop's prev-state contract) |
| Persistence | `joblib.dump` to `models/heater_surrogate.joblib`, loaded once at sim start |

**Why MLPRegressor, not Linear/Poly, not LSTM:**
- Arrhenius is `exp(−Ea/RT)` — a polynomial regressor needs degree ≥ 4 with cross-terms to fit cleanly and explodes in feature count. Linear is a non-starter.
- An LSTM is overkill: the analytic formula is **Markovian** (next state depends only on prev state + drivers), so we don't need a recurrent hidden state. LSTM would also burn a half-day on PyTorch plumbing.
- A 3-layer MLP fits a 7-D smooth manifold in seconds on a laptop CPU, ships as one `.joblib`, and a judge with an ML background instantly recognises it as the right tool.

### 3. Training-data generation

- **Sampler:** Latin Hypercube over the 6-D driver/state cube `[T_stress, humidity, load, maintenance] ∈ [0,1]⁴`, `prev_HI ∈ [0,1]`, `prev_resistance_norm ∈ [1.0, 1.6]`, `dt = 1 h` fixed.
- **Volume:** **20 000 samples**. Cheap (analytic formula evaluation is sub-millisecond), and enough to crush a 32×32×32 MLP.
- **Splits:** **70 % train / 15 % val / 15 % test**, fixed seed 42.
- **Targets:** call the analytic Arrhenius function once per sample to produce `Δresistance_norm`. Standardise inputs with `StandardScaler` (saved alongside the model).
- **Acceptance gate:** test-set **MAE ≤ 2 %** of full health range, **R² ≥ 0.99**. If we miss, fall back to analytic for the heater (the cascade alone is still a bonus point).
- **Ablation chart for the deck:** plot analytic vs. surrogate health curves over a 6-month run on the same drivers; visually indistinguishable lines = the slide writes itself.

## Why this fits our case

Phase 1's evaluation explicitly lists *Complexity & Innovation* and *Systemic Interaction* as bonus pillars, and the brief itself names "cascading failures" and "AI degradation model" as advanced ideas (`TRACK-CONTEXT.md` §4 Phase 1 bonuses). The cascade gives us the *systemic* story — three components stop being independent — and the surrogate gives us the *innovation* story without forcing us to invent new physics. Both are additive on top of the existing analytic engine: if either misbehaves we delete one line and the demo still runs. They also feed Phase 3 directly: the chatbot can answer "why did the nozzle clog so fast?" with "blade health dropped to 0.28 at t=…, which raised effective contamination to 0.62" — a multi-hop, fully grounded answer that judges will reward.

## References

- *Binder Jetting: A Comprehensive Guide* — <https://www.wevolver.com/article/binder-jetting>
- *Review of types, formation mechanisms, effects, and elimination methods of binder-jetting 3D-printing defects*, ScienceDirect 2023 — <https://www.sciencedirect.com/science/article/pii/S2238785423028193>
- *A laboratory-scale binder jet AM testbed*, MIT / PMC — <https://pmc.ncbi.nlm.nih.gov/articles/PMC8216295/>
- *Surrogate Neural Networks Local Stability for Aircraft Predictive Maintenance*, arXiv 2401.06821 — <https://arxiv.org/abs/2401.06821>
- *Predicting System Degradation with a Guided Neural Network Approach*, PMC — <https://pmc.ncbi.nlm.nih.gov/articles/PMC10385234/>
- *Physics-informed neural network for lithium-ion battery degradation*, Nature Communications 2024 — <https://www.nature.com/articles/s41467-024-48779-z>
- *Deep learning models for predictive maintenance: a survey*, arXiv 2010.03207 — <https://arxiv.org/pdf/2010.03207>
- sklearn `MLPRegressor` docs — <https://scikit-learn.org/stable/modules/generated/sklearn.neural_network.MLPRegressor.html>
- Internal: `docs/research/01-recoater-blade-archard.md` (cascade hook already noted at end of file)

## Open questions

- **Cascade coefficient (0.5):** chosen so a fully-failed blade adds at most +0.25 to nozzle `C`. We should sweep `α ∈ {0.3, 0.5, 0.8}` once the nozzle model is in and pick the value that gives a visible-but-not-instant nozzle response.
- **Threshold vs. continuous:** spec uses a continuous ramp and a *narrative* threshold at `loss_frac = 0.4`. If a judge prefers a hard switch (cleaner story), gate the term with `if loss_frac > 0.3 else 0` — costs one line.
- **Surrogate retrain budget:** 20 000 samples + 32×32×32 MLP trains in <30 s on a laptop. We can afford to retrain inside the demo if drivers ranges change; worth scripting as a `make train-heater` target.
- **Do we surrogate-replace one component or *add* a surrogate alongside the analytic?** Current decision: replace, so the loop genuinely depends on the learned model. Safer fallback: keep analytic as default, switch via a CLI flag `--heater-model={analytic,nn}` so we can toggle live in the demo.
- **Two-way cascade (nozzle clog → blade load):** explicitly out of scope for v1. Revisit only if Phase 1 finishes a full day early.
- **PINN upgrade path:** if we somehow end up with spare time, frame the MLP loss as `MSE(Δ) + λ · |dHI/dt + k·exp(−Ea/RT)|` to make it a tiny PINN. Pure deck candy, do not start before everything else ships.
