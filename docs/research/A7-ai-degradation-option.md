# A7 — AI-Degradation Option: Learned Surrogate for One Component

## TL;DR

**Yes, do it.** Replace the Heating Elements analytic formula with a tiny
sklearn `MLPRegressor` trained on ~2 000 synthetic samples generated from
that same formula plus injected noise. Use a **delta-learning** framing:
the model learns the _residual_ between the analytic baseline and a
"real-world-dirty" variant, so the formula stays defensible but the ML
layer adds measurable accuracy. Takes ~1–2 hours of implementation, zero
real data, and gives judges a live "AI vs. physics" toggle in the demo.

---

## Background

**Delta-learning (learned residual):** train an ML model on
`y_target - y_analytic` rather than on `y_target` directly. The analytic
baseline handles the large-scale trend; the learner corrects systematic
deviations (non-linearities, interaction effects, noise-bias). This
pattern is well-established in computational chemistry surrogate work
(MLatom/KREG) and is directly applicable here: our analytic formula is the
"low-fidelity" baseline; the ML residual mimics the "high-fidelity"
(noisier, more realistic) behavior.

**Why PINNs are overkill here:** PINNs embed PDEs as soft constraints in
the loss and require careful collocation-point selection and long training.
For a 24-hour hackathon with four scalar drivers, an MLP or GBR fit in
seconds and achieves the same demo effect with zero training risk.

---

## Options Considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| PINN (physics loss in training) | Scientifically rigorous | Hours to tune, no pre-made data | Reject |
| `GradientBoostingRegressor` (sklearn) | Interpretable feature importances, robust | Slow to train on many trees, no easy online update | Second choice |
| `MLPRegressor` (sklearn, 2 hidden layers) | Fast, smooth interpolation, matches analytic curve well, natural for noisy regression | Slightly black-box | **Recommended** |
| Pure analytic formula (no ML) | Simple, deterministic | No "AI inside" story for judges | Baseline only |

**Best candidate component: Heating Elements (Thermal Control subsystem).**

Reasons:
- The analytic model is a clean Arrhenius/exponential-decay scalar:
  `R(t) = R0 * exp(k * T_stress * load)`. Easy to generate dense
  synthetic data over the 4-driver hypercube.
- Electrical resistance drift is a single continuous output — ideal
  regression target.
- Nozzle clogging involves discrete events (clogs/unclogging) — harder
  to surrogate cleanly. Blade wear is nearly linear, so ML adds little.
- A "resistance prediction" plot (analytic vs. ML) is visually clear in
  60 seconds.

---

## Recommendation — Concrete Plan

### Training data generation

Sample ~2 000 points uniformly over the driver hypercube
`(T_stress, humidity, load, maintenance)`, evaluate the analytic
`R_analytic(x)`, add structured noise that grows with temperature stress
to simulate measurement/aging spread, and record
`delta = R_noisy - R_analytic`. Train the MLP on `delta`.

At inference: `R_predicted(x) = R_analytic(x) + mlp.predict([x])`.

### ~30-line pseudocode sketch

```python
import numpy as np
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

# --- 1. Analytic formula (Arrhenius-inspired) ---
R0, k = 10.0, 0.003          # baseline resistance Ω, degradation rate

def r_analytic(T_stress, humidity, load, maintenance):
    return R0 * np.exp(k * T_stress * load * (1 + 0.2 * humidity) / (maintenance + 0.1))

# --- 2. Synthetic data generation ---
rng = np.random.default_rng(42)
N = 2000
X = rng.uniform([0, 0, 0, 0.1], [50, 1, 5000, 1.0], size=(N, 4))
R_analytic_vals = r_analytic(*X.T)
noise = rng.normal(0, 0.05 * R_analytic_vals * (1 + X[:, 0] / 50))
delta = noise                 # learned residual = realistic deviation

# --- 3. Train tiny MLP on the residual ---
surrogate = make_pipeline(
    StandardScaler(),
    MLPRegressor(hidden_layer_sizes=(32, 16), max_iter=500, random_state=42)
)
surrogate.fit(X, delta)

# --- 4. Inference: analytic baseline + learned correction ---
def r_predicted(T_stress, humidity, load, maintenance):
    x = np.array([[T_stress, humidity, load, maintenance]])
    return r_analytic(T_stress, humidity, load, maintenance) + surrogate.predict(x)[0]
```

### Making it visible in the 60-second demo

1. **Toggle switch in the UI / CLI flag** `--heater-model [analytic|ai]`.
   Run the simulation twice; show diverging resistance curves on the
   same chart. Judges see the AI making different (more pessimistic,
   realistic) predictions.
2. **Feature-importance bar chart** from a companion
   `GradientBoostingRegressor` trained on the same data — shows that
   `T_stress` and `load` dominate, which is physically intuitive and
   immediately credible.
3. **Training provenance slide**: one bullet — "2 000 synthetic samples
   from Arrhenius formula + noise, trained in <1 s." Judges see AI
   without black-box mystery.

---

## Open Questions

1. Should the MLP be re-trained each simulation run (fresh scenario) or
   trained once and persisted? Persisting is safer for the demo.
2. Is adding a Weibull-shaped noise term (instead of Gaussian) more
   physically realistic for resistance drift? Probably yes but low
   priority.
3. Do we expose `surrogate.predict` uncertainty (e.g., with
   `MLPRegressor` ensemble bootstrap) to give the chatbot a confidence
   score? Nice-to-have for Phase 3.

---

## References

- MLatom delta-learning tutorial: https://mlatom.com/how-to-construct-and-use-delta-learning-models/
- sklearn `MLPRegressor` docs: https://scikit-learn.org/stable/modules/generated/sklearn.neural_network.MLPRegressor.html
- AllAboutCircuits — Arrhenius resistor aging: https://www.allaboutcircuits.com/technical-articles/using-the-arrhenius-equation-to-predict-aging-of-electronic-components/
- "Deep learning for model correction of dynamical systems with data scarcity": https://arxiv.org/html/2410.17913
- PINNs as surrogate models overview (Shuai Guo, Medium): https://shuaiguo.medium.com/using-physics-informed-neural-networks-as-surrogate-models-from-promise-to-practicality-3ff13c1320fc
- sklearn `GradientBoostingRegressor` docs: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.GradientBoostingRegressor.html
