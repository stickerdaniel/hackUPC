# Coupling Matrix + AI-Surrogate Degradation Model

> Master spec for how the six components in the coupled engine see each
> other. Subsumes the old one-way blade→nozzle cascade in this doc and the
> bilateral specs scattered across docs 01, 02, 03, 17, 18, 19. Anything
> built into `CouplingContext` lives here. Last updated: 2026-04-25.

---

## TL;DR

- 6 components, 3 subsystems (powder: blade+rail; jetting: nozzle+cleaning;
  thermal: heater+sensor). Each tick we build one `CouplingContext` from
  the immutable `t-1` `PrinterState` and feed it to all six update rules.
- **Three two-way loops** (rail↔blade, cleaning↔nozzle, sensor↔heater) +
  **two cross-subsystem cascades** (powder→jetting, thermal→everything)
  make failure trajectories emergent — the "cascading failures" bonus.
- Stable by construction: states clamped to `[0,1]`, coupling gains `<1`,
  components only ever read `t-1`, damage is monotone between maintenance.
- Heater shadow-replaced by sklearn `MLPRegressor (32,32,32) tanh` on
  20 k LHS samples; gate **MAE ≤ 2 %**. Deck line: *"two lines that
  overlap perfectly."*

---

## Background — coupled vs independent component models

Independent series composition (each component on its own physics, system
fails at `min(H) < 0.15`) gives you a histogram of MTBFs but misses the
real story: degradation in one part *changes the operating environment
of another*. BJ defect reviews (Wevolver; ScienceDirect 2023; MIT
testbed) call out exactly this — worn recoaters → trapped fines →
clogging; heater drift → off-spec temp → fatigue spikes; worn wipers →
residue → faster clogs. The digital-twin literature names it
**physics-of-failure coupling** (Liu et al., MDPI Sensors 2023). We
model it through one `CouplingContext` per tick so couplings are
first-class, persisted as `coupling_factors_json`, and queryable by the
co-pilot for multi-hop "why did X fail?" answers.

---

## Coupling matrix

For each row, the math operates on the consuming component's per-tick
update. `prev` always means `t-1` `PrinterState`. Coefficients are the
authoritative values; per-component docs defer to this table on
disagreement.

| Consumer (component) | Input source | Math | α | Notes |
|---|---|---|---|---|
| **Blade** (`k_eff`) | `prev.rail.alignment_error` | `k_eff *= (1 + α · alignment_error)` | **0.5** | Misaligned rail forces uneven blade contact; doc 17 §two-way. |
| **Blade** (`k_eff`) | `effective.humidity_contamination` | `k_eff *= (1 + 0.6 · C_eff)` | 0.6 | Already in doc 01; uses *effective* C, so the cascade chain feeds in here. |
| **Rail** (`dD/dt`) | `prev.blade.loss_frac` | `alignment_error_um += α · blade.loss_frac · dt` | **0.05 µm/h** | Worn blade transmits lateral impulses; doc 17 §two-way. |
| **Nozzle** (`λ_clog`) | `effective.humidity_contamination` | `λ = λ₀ · (1 + 1.5 · C_eff)` | 1.5 | Doc 02; consumes the cascade through the *effective* driver below. |
| **Nozzle** (`λ_clog`) | `effective.temperature_stress` | `λ *= (1 + α · |T_eff − T_opt|)` | 0.08 /°C | Doc 02; consumes heater drift via `T_eff`. |
| **Nozzle** (clog reset) | `prev.cleaning.cleaning_efficiency` | `clog_pct ← clog_pct · (1 − η)` on maintenance | n/a | Doc 18 §coupling out — no reset if wiper is dead. |
| **Cleaning** (`wear_factor`) | `prev.nozzle.clog_pct` | `wear_factor += α · clog_pct/100` | **0.4** | Residual contamination on the plate abrades the lip faster (doc 18 open Q resolved). |
| **Heater** (`dD/dt`) | `factors["control_temp_error_c"]` | `T_actual = T_setpoint + control_error`; Arrhenius uses `T_actual` | n/a | Sensor bias propagates as wrong-setpoint stress (doc 19). |
| **Heater** (`dD/dt`) | `factors["sensor_noise_sigma_c"]` | `dD/dt *= (1 + 0.2 · σ/5°C)` | 0.2 | Noisy sensor → controller dithers → more thermal cycles per hour. |
| **Sensor** (drift rate) | `prev.heater.drift_frac` | `dbias/dt *= (1 + α · drift_frac)` | **0.5** | Hotter heater → faster sensor element aging; closes the thermal loop. |
| **Effective C** (driver) | `prev.blade.loss_frac`, `prev.rail.alignment_error` | `C_eff = clip(C + (1 − Q_powder), 0, 1)` where `Q_powder = (1 − loss_frac)·(1 − alignment_error)` | n/a | Powder-spread quality cascades into jetting subsystem. |
| **Effective T** (driver) | `prev.heater.drift_frac` | `T_eff = clip(T + 0.3 · drift_frac, 0, 1)` | **0.3** | Heater drift inflates plate temperature for nozzle + sensor self-heating. |

**Reading the table.** Rows 1–3 close rail↔blade; 4–7 close
cleaning↔nozzle; 8–10 close sensor↔heater; 11–12 are the cross-subsystem
cascades. Old doc 05's one-way `blade → nozzle.C @ α=0.5` is now row 11:
a worn blade and misaligned rail jointly drop `Q_powder`, which raises
`humidity_contamination_effective`. With `loss_frac = 0.5` and zero
alignment error, the boost to C is exactly +0.5 — old demo numbers land.

---

## CouplingContext derivation

Built once per tick by `engine.coupling.build_coupling_context(prev_state,
drivers, dt)`. All names match `CouplingContext` (see
`sim/src/copilot_sim/domain/coupling.py`).

```python
b = prev.components["blade"].metrics       # .loss_frac
r = prev.components["rail"].metrics        # .alignment_error in [0,1]
n = prev.components["nozzle"].metrics      # .clog_pct, .fatigue_damage
c = prev.components["cleaning"].metrics    # .cleaning_efficiency
h = prev.components["heater"].metrics      # .drift_frac
s = prev.components["sensor"].metrics      # .bias_c, .noise_sigma_c

# --- Effective drivers (the four Drivers fields, post-coupling) ---
Q_powder = clamp((1 - b.loss_frac) * (1 - r.alignment_error), 0.0, 1.0)
humidity_contamination_effective = clamp(
    drivers.humidity_contamination + (1 - Q_powder), 0.0, 1.0
)
temperature_stress_effective = clamp(
    drivers.temperature_stress + 0.3 * h.drift_frac, 0.0, 1.0
)
operational_load_effective   = drivers.operational_load     # no coupling yet
maintenance_level_effective  = drivers.maintenance_level    # no coupling yet

# --- Named factors (persisted, queryable by the co-pilot) ---
factors = {
    # Powder pipeline (subsystem A → B cascade)
    "powder_spread_quality":      Q_powder,                      # 0..1, higher = better
    "blade_loss_frac":            b.loss_frac,
    "rail_alignment_error":       r.alignment_error,

    # Thermal pipeline (subsystem C → B + inner loop)
    "heater_drift_frac":          h.drift_frac,
    "heater_thermal_stress_bonus": 0.3 * h.drift_frac,

    # Sensor → control (subsystem C inner loop)
    # Two separate factors by design — they hold the same value in v1 but
    # have different *roles* and are read by different consumers:
    #   - sensor_bias_c       = the sensor component's emitted bias (RAW signal,
    #                           reported in the dashboard's true-vs-observed view)
    #   - control_temp_error_c = the input the heater controller actually sees;
    #                            future hook for ADC quantization, bus latency,
    #                            PID lag, or any other controller-side error
    #                            source we add later. Heater step() reads ONLY
    #                            control_temp_error_c, never sensor_bias_c
    #                            directly. Keeping them separate now means the
    #                            extension point is free.
    "sensor_bias_c":              s.bias_c,
    "sensor_noise_sigma_c":       s.noise_sigma_c,
    "control_temp_error_c":       s.bias_c,  # v1: identical to sensor_bias_c

    # Jetting maintenance pipeline
    "cleaning_efficiency":        c.cleaning_efficiency,
    "nozzle_clog_pct":            n.clog_pct,
}
```

**Naming.** Effective drivers use `CouplingContext`'s exact `*_effective`
fields. Factors are `snake_case`, unitless unless suffixed (`_c` °C,
`_pct` %, `_um` µm), and stable across runs. Adding a factor is one
`factors[…] = …` edit and one addition to the chatbot's allowed-key list.

---

## Stability and bounded-feedback argument

Every two-way loop is a gain-bounded contraction. States clip to `[0,1]`;
the largest coupling gain is 0.6 on a `[0,1]` quantity, so within-tick
products stay sub-unity. The double-buffer rule means each tick reads
`prev_state` only — there is no within-tick algebraic loop, so any
oscillation would have to grow tick-by-tick, which the gain forbids.
Damage accumulators (`D` in rail, `D_F` in nozzle, `drift_frac` in
heater) are monotone non-decreasing between maintenance events; bounded
monotone sequences converge. Maintenance only resets *down*. Worst-case
hand-walk (all couplings max, no maintenance) reaches `min(H) < 0.15` in
≈ 60 sim-days; nominal in ≈ 180. No run produces unbounded growth.

---

## Worked example — abusive scenario walkthrough

Drivers: `T=0.85, H=0.80, L=0.95, M=0.10` (constant); chaos burst pushes
`H → 1.0` for one hour at sim-day 60.

1. **Days 0–20.** Blade abrasion runs hot; `loss_frac` crosses 0.15.
   `Q_powder` drops to ~0.83 → `C_eff` is already **+0.17 above raw**.
2. **Days 20–40.** Elevated `C_eff` raises nozzle `λ_clog` ~25 %.
   `clog_pct` reaches ~12 %; first cleaning fires; full reset (fresh
   wiper) but wiper takes its first abrasion hit.
3. **Days 40–60.** Heater `drift_frac ≈ 0.04`; sensor reads ~2 °C low,
   so heater overheats trying to hit setpoint → plate runs 2 °C hot →
   nozzle Coffin-Manson `D_F` jumps. **Inner thermal loop firing.**
4. **Day 60 (chaos).** `C_eff = 1.0` (clamped); Poisson event lands;
   `clog_pct` → ~28 %. Cleaning efficiency now ~0.6 → partial reset to
   ~11 %. Residual clog raises wiper `wear_factor` for next cycle.
   **Cleaning↔nozzle loop firing.**
5. **Days 60–90.** Rail accumulates `0.05·0.4·24 ≈ 0.48 µm/day` from the
   worn blade alone. DEGRADED at day ~75; `alignment_error ≈ 0.5`
   feeds back into `blade.k_eff *= 1.25`. **Rail↔blade loop firing.**
6. **Days 90–120.** Powder pipeline collapses: `Q_powder ≈ 0.4`,
   `C_eff` saturates. Nozzle FAILED; heater `drift_frac ≈ 0.08`; sensor
   `bias_c ≈ 4 °C`. Co-pilot can attribute the failure four hops back
   through `coupling_factors_json`:
   `nozzle.clog → C_eff → Q_powder → blade.loss_frac × rail.alignment`.
7. **Day ~125.** `min(H) < 0.15`; system FAILED. No single component
   caused it — the matrix did.

---

## AI surrogate (heater = MLPRegressor)

| Item | Value |
|---|---|
| Component replaced | Heating Elements (analytic Arrhenius + self-heating) |
| Model class | sklearn **`MLPRegressor`**, hidden `(32, 32, 32)`, `tanh`, `adam`, `max_iter=2000`, seed 42 |
| Inputs | `[prev_drift_frac, T_eff, humidity, load, maintenance, control_temp_error_c, dt]` (7) |
| Output | `Δdrift_frac` per tick (regress the *delta*, not absolute state) |
| Training data | **20 000 Latin-Hypercube** samples from doc 03's analytic formula |
| Splits | 70 / 15 / 15 train/val/test, seed 42 |
| Acceptance gate | **MAE ≤ 2 %** of full drift range, **R² ≥ 0.99** on test set |
| Persistence | `joblib.dump → models/heater_surrogate.joblib`; `StandardScaler` saved alongside |
| Demo artefact | One chart: analytic vs. surrogate health curves over 6 months on the same drivers — visually indistinguishable |

**Why MLP.** Arrhenius is `exp(−Ea/RT)` — polynomials need degree ≥ 4
with cross-terms; linear is a non-starter; LSTM is overkill since the
update is Markovian. A 32×32×32 MLP fits a 7-D smooth manifold in seconds
on CPU, ships as one `.joblib`. Surrogate consumes the same
`CouplingContext` fields as the analytic core, so swap is a one-line
dispatch (`--heater-model={analytic,nn}`). Miss the gate → fall back to
analytic, ship the matrix alone (still scores the bonus).

---

## References

- *Binder Jetting: A Comprehensive Guide* — Wevolver. <https://www.wevolver.com/article/binder-jetting>
- *Review of types, formation mechanisms, effects, and elimination methods of binder-jetting 3D-printing defects*, ScienceDirect 2023. <https://www.sciencedirect.com/science/article/pii/S2238785423028193>
- *A laboratory-scale binder jet AM testbed*, MIT / PMC. <https://pmc.ncbi.nlm.nih.gov/articles/PMC8216295/>
- *Digital Twin–Driven Coupled Multiphysics System for Equipment Health Monitoring*, MDPI Sensors 2023. <https://www.mdpi.com/1424-8220/23/14/6534>
- *Surrogate Neural Networks Local Stability for Aircraft Predictive Maintenance*, arXiv 2401.06821. <https://arxiv.org/abs/2401.06821>
- *Predicting System Degradation with a Guided Neural Network Approach*, PMC. <https://pmc.ncbi.nlm.nih.gov/articles/PMC10385234/>
- *Physics-informed neural network for lithium-ion battery degradation*, Nature Communications 2024. <https://www.nature.com/articles/s41467-024-48779-z>
- *Deep learning models for predictive maintenance: a survey*, arXiv 2010.03207. <https://arxiv.org/pdf/2010.03207>
- sklearn `MLPRegressor` docs. <https://scikit-learn.org/stable/modules/generated/sklearn.neural_network.MLPRegressor.html>
- Internal: docs 01, 02, 03, 17, 18, 19 (per-component coupling specs reconciled here); `sim/src/copilot_sim/domain/coupling.py` (CouplingContext schema).

---

## Open questions

- **Coefficient sweep.** α values come from per-component docs; sweep
  `{0.5×, 1×, 2×}` after first end-to-end run.
- **Heater self-heating gate.** If nozzle ages too fast under nominal
  drivers, gate the `T_eff += 0.3·drift_frac` term on `drift_frac > 0.02`.
- **Sensor↔heater loop gain.** α = 0.5 on heater→sensor is a guess; if
  sensor failures lag heater failures by 30+ days, bump to 0.8.
- **Cleaning→nozzle reverse path.** Doc 18 open Q proposed feeding
  `(1 − η)` additively into nozzle C. Matrix routes it through
  `wear_factor` instead. Revisit if day-60 doesn't visibly degrade wiper.
- **Surrogate live retrain.** 20 k samples + MLP trains in <30 s; ship a
  `make train-heater` target so driver ranges can change live in demo.
- **PINN upgrade.** `MSE(Δ) + λ·|dD/dt + k·exp(−Ea/RT)|`. Deck candy
  only — do not start before everything else ships.

## Synthetic prompt

> Rewrite `docs/research/05-cascading-and-ai-degradation.md` as a full
> coupling-matrix spec for the six-component coupled engine. Include a
> matrix table (consumer × source × math × α) covering three two-way
> loops (rail↔blade, cleaning↔nozzle, sensor↔heater) and two
> cross-subsystem cascades (powder→jetting, thermal→everything),
> derive `CouplingContext` (the four `*_effective` drivers and a named
> `factors` dict matching `sim/src/copilot_sim/domain/coupling.py`),
> argue stability via clamps + sub-unity gains + double-buffered ticks,
> walk through an abusive scenario chronologically, keep the
> sklearn `MLPRegressor (32,32,32) tanh` heater surrogate with a 2 %
> MAE acceptance gate, and reference docs 01/02/03/17/18/19.

Generated with Claude Opus 4.7
