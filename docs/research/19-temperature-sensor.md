# Temperature Sensor — Bias-Drift + Noise-Floor Aging, Reference §3.4 Sensor Model

> Failure model for the **Temperature Sensor** component of the Thermal Control
> subsystem on the HP Metal Jet S100 digital twin. Doubles as the **reference
> implementation of the per-component sensor model** from `TRACK-CONTEXT.md
> §3.4` (true vs observed state). Subsystem C, component 2 of 2.
> Last updated: 2026-04-25.

---

## TL;DR

Model the temperature sensor as a **PT100-class RTD** with two failing
quantities: a slowly accumulating **bias `bias_C`** (signed offset, °C) and a
slowly growing **noise floor `noise_sigma_C`** (Gaussian σ on each reading).
Bias accumulates Arrhenius-fast under heater exposure (the sensor sits next to
the element it watches), noise grows sub-linearly with cumulative thermal
exposure (work-hardening of the lead alloy and connector oxidation). Health
Index is driven by `|bias_C|` against a ±5 °C tolerance, with a hard `FAILED`
gate at `|bias_C| > 5 °C` regardless of HI. The sensor is also the **reference
§3.4 layer**: each tick its true `bias_C` / `noise_sigma_C` map deterministic-
ally to an `observed_metrics["temperature_C"]` plus a `sensor_note ∈
{"ok","noisy","drift","stuck","absent"}`. A rare Poisson dropout produces
short stuck windows, and once `|bias_C|` exceeds the FAILED gate the sensor
goes permanently `absent` (catastrophic). Every other sensored component in
Phase 1 will reuse this exact shape.

---

## Background — sensor aging physics

Industrial temperature sensors are **not stable forever**. Two well-documented
mechanisms govern long-term behaviour:

- **Calibration drift (bias).** For Type-K thermocouples, drift can exceed
  10 °C after a few hundred hours at high temperatures, dominated by
  reversible crystallographic ordering below ~800 °C and irreversible
  oxidation/Seebeck-coefficient shift above (WIKA; Cambridge UTC; ScienceDirect
  long-term Nicrosil study). For PT100 RTDs, manufacturer specifications quote
  **≤ 0.02 °C/year at < 450 °C**, rising to **~0.3 °C/year at sustained 100 °C
  use** (HW-group; Sterling Sensors; Peak Sensors). In both cases the drift
  rate scales steeply with operating temperature — Arrhenius behaviour is the
  defensible first-order model.
- **Noise growth.** Connector oxidation, lead-wire work-hardening from
  thermal cycling, and humidity-driven leakage paths progressively raise the
  measurement noise floor. Less precisely quantified than bias in the
  literature, but uniformly described as a slow, monotone, sub-linear creep.

For the S100's curing/heating zone (heater nominal 150 °C, ambient 25–60 °C)
a PT100 in a sheath is the realistic choice; we calibrate the rates so that
under abusive scenarios the sensor reaches CRITICAL inside the 6-month
horizon, while a well-maintained sensor at nominal drivers stays FUNCTIONAL.

---

## Decision — as a component (own degradation)

### State (in `ComponentState.metrics`)

| Metric | Type | Range | Meaning |
| :--- | :--- | :--- | :--- |
| `bias_C` | float (signed) | nominal `[−5, +5] °C` | Slowly accumulating calibration offset |
| `noise_sigma_C` | float ≥ 0 | nominal `[0.05, 1.5] °C` | Gaussian σ on each observation |
| `last_calibrated_tick` | int | — | Tick of most recent `FIX` event |

### Tick update (compounded, deterministic core + small per-tick noise)

The sensor sits next to the heater, so it is exposed to roughly the heater's
effective temperature `T_sense ≈ T_amb + ΔT_duty` (the same field the heater
already computes; consume from `CouplingContext.factors["heater_T_eff_K"]`).

```
AF_sensor(t) = exp[ (E_a / k_B) · (1/T_ref − 1/T_sense(t)) ]
db/dt        = α_b · AF_sensor(t) · (1 + γ_H · humidity)
                      · (1 + γ_L · operational_load) / M
bias_C(t+dt)        = bias_C(t) + sign · db/dt · dt
noise_sigma_C(t+dt) = noise_sigma_C(t) + α_n · sqrt(AF_sensor) · dt
```

| Symbol | Meaning | Default |
| :--- | :--- | :--- |
| `E_a` | activation energy | `0.7 eV` (matches doc 03) |
| `T_ref` | reference temp | `423 K` (150 °C, sensor sees the heater field) |
| `α_b` | base bias rate at AF=1, M=1 | `1.0e-7 °C/s` (≈ 0.36 °C / 1000 h at AF=1, ≈ 3 °C / 1000 h at heater nominal) |
| `α_n` | noise growth rate | `2.0e-8 °C/s` (≈ 0.07 °C / 1000 h at AF=1) |
| `γ_H` | humidity coupling (corrosion of solder/connector) | `0.4` |
| `γ_L` | thermal-cycling coupling (load → on/off cycles) | `0.3` |
| `M` | maintenance multiplier | `0.5` (calibrated weekly) to `2.0` (neglected) |
| `sign` | bias direction | drawn at install from {−1, +1}; oxidation typically drives Seebeck output **down** for K-type, RTDs **up**; we randomise per-instance |

`α_b` is calibrated so that under abusive drivers (`AF_sensor ≈ 5`,
`humidity ≈ 0.7`, `M = 2`) the sensor reaches `|bias_C| = 5 °C` in
~3000–4000 h, well inside the 6-month (4380 h) horizon. Under nominal
(`AF_sensor ≈ 2`, `humidity ≈ 0.3`, `M = 0.7`) it stays under 1 °C across the
horizon — a clean separation that makes scenario-driven demos legible.

### Health index and status thresholds

```
HI_bias  = clip(1 − |bias_C| / 5.0, 0, 1)
HI_noise = clip(1 − (noise_sigma_C − 0.05) / 1.45, 0, 1)
HI       = 0.7 · HI_bias + 0.3 · HI_noise          # bias dominates
```

Standard thresholds: `HI ≥ 0.75` FUNCTIONAL, `≥ 0.40` DEGRADED, `≥ 0.15`
CRITICAL, else FAILED. **Hard-fail gate**: `|bias_C| > 5 °C` ⇒ `FAILED`
regardless of HI (matches the operator-trust failure mode — once the reading
is more than ±5 °C wrong it is unusable for control).

---

## Decision — as the §3.4 sensor model (reference layer)

Each tick the engine builds `ObservedComponentState` for **every sensored
component** by calling a shared helper parameterised by the sensor's
`(bias_C, noise_sigma_C, sensor_health)`. The temperature sensor *is* this
helper applied to itself:

```
# Inputs: true metric value, sensor true state, RNG
true_T          = heater.metrics["heater_T_eff_K"] - 273.15   # °C
bias            = self.metrics["bias_C"]
noise           = self.metrics["noise_sigma_C"]
dropout_active  = (rng.random() < p_dropout) or in_stuck_window

if catastrophic_fail:                                # |bias| > 5 °C
    observed = None
    note     = "absent"
elif dropout_active:                                 # rare Poisson
    observed = None
    note     = "stuck"                               # for K = 1..3 ticks
else:
    observed = true_T + bias + rng.normal(0, noise)
    note     = classify(bias, noise)                 # see below
```

### `sensor_note` classification

| Condition | `sensor_note` |
| :--- | :--- |
| `|bias| < 1 °C` and `noise < 0.3 °C` | `"ok"` |
| `noise ≥ 0.3 °C` and `|bias| < 1 °C` | `"noisy"` |
| `|bias| ≥ 1 °C` and `noise < 0.3 °C` | `"drift"` |
| both above thresholds | `"drift+noisy"` (mixed-tag — string-joined) |
| current tick in dropout window | `"stuck"` |
| post-catastrophic | `"absent"` |

### Dropout / stuck process

Poisson process with **`p_dropout = 5e-5 / tick`** (≈ one dropout every ~830 h
nominally), rate scales with `1 + (1 − HI)` so a degraded sensor drops out
more often. Stuck-window length `K` sampled from `Geometric(0.5)` capped at 3
ticks. During stuck, `observed_metrics["temperature_C"] = None`.

### `sensor_health` field

```
ObservedComponentState.sensor_health = {
    "temperature_C": HI                # the per-metric sensor health, 0..1
}
```

Per-metric (the sensor on the temperature reading), not per-sensor — this is
what the schema wants and is what generalises to multi-metric components
(e.g. a load cell exposing both force and temperature).

### `observed_health_index` and `observed_status`

For the sensor's own observed view (a sensor introspecting itself is
philosophically odd; we expose a conservative summary):

- If `sensor_note == "absent"` → `observed_health_index = None`,
  `observed_status = OperationalStatus.UNKNOWN`.
- Else → `observed_health_index = HI` (sensor is self-aware to a degree, and
  a calibration check against a reference is what `FIX` represents),
  `observed_status` from the standard thresholds.

For *other* components consuming this sensor, their observed view is
recomputed from `observed_metrics`; if `temperature_C is None` for a heater
metric, the heater's `observed_status` collapses to `UNKNOWN` for that tick.

---

## Coupling out — `CouplingContext.factors`

The temperature sensor publishes two factors every tick. The heater (doc 03)
reads them and recomputes its **believed** temperature, which is what the
control loop defends against:

| Factor name | Type | Used by | Effect |
| :--- | :--- | :--- | :--- |
| `sensor_bias_c` | signed float, °C | Heater control | Adds to controller's input |
| `sensor_noise_sigma_c` | float ≥ 0, °C | Heater control | Stochastic per-tick noise on input |

### Heater consumption math

```
T_believed     = T_actual + sensor_bias_c + N(0, sensor_noise_sigma_c)
control_error  = T_setpoint − T_believed                   # what the PID sees
T_actual_next  = plant_response(T_actual, control_error)   # what physics does
```

If `sensor_bias_c < 0` (sensor under-reads), the controller pushes more power
to "warm up" the (already hot) heater → `T_actual` overshoots → heater's
Arrhenius `AF` rises → faster drift. **This is the §1 feedback loop** the
brief explicitly asks us to model: sensor degradation accelerates heater
degradation, heater degradation increases sensor exposure, both fail faster
together.

---

## Maintenance semantics

We use the existing `OperatorEventKind` enum (`domain/events.py`) without
extension, distinguishing three actions on this component:

| Event | Effect on true state | Effect on observed state |
| :--- | :--- | :--- |
| `TROUBLESHOOT` | No state change. Sets `last_inspected_tick` (component metadata). Operator confirms reading vs. plant reality. | `sensor_note` flagged `"ok"` for this tick (operator-vouched). |
| `FIX` (calibration) | `bias_C ← 0`. `noise_sigma_C` **unchanged** (calibration removes offset, not connector oxidation). `last_calibrated_tick ← t`. | Recomputed normally next tick. |
| `REPLACE` | `bias_C ← 0`, `noise_sigma_C ← 0.05` (datasheet floor), `age_ticks ← 0`. New random `sign` drawn for next instance's bias direction. | Recomputed normally next tick. |

Mirrors real practice: a **calibration check** (annual, cheap) zeros bias but
cannot un-corrode a connector; a **sensor swap** (replacement, expensive) is
the only path to a fresh noise floor.

---

## Why this fits our case

1. **Closes the heater ↔ sensor loop.** Doc 03's heater consumes
   `sensor_bias_c`; the sensor consumes the heater's `T_eff_K`. Both
   components fail together under abusive drivers — a textbook cascading-
   failure narrative the brief rewards.
2. **Reference §3.4 layer.** The mapping `(true, bias, noise) → (observed,
   note)` plus the dropout/absent/UNKNOWN rules generalise verbatim to every
   other sensored component (blade load-cell, nozzle clog%, etc.). One helper,
   six components.
3. **Two independent metrics** mean two failure modes the co-pilot can
   distinguish in Phase 3: "sensor is biased" vs "sensor is noisy" vs
   "sensor dropped out". Distinct `sensor_note` values give the chatbot
   crisp diagnostic vocabulary.
4. **Hard-fail gate** keeps the model legible: a CRITICAL sensor still
   produces readings, but a FAILED sensor goes `absent`, which forces the
   operator into a `REPLACE` decision rather than a `FIX` — clean demo arc.
5. **Physically grounded.** Arrhenius for drift matches the doc-03 frame
   used for the heater itself (same `E_a`, same `T_ref`); PT100 ≤ 0.02 °C/yr
   spec is the "well-maintained" boundary; thermocouple 10 °C / few-hundred-h
   under abuse is the "neglected" boundary. Real numbers, not invented.

---

## References

1. **WIKA — Aging and Drift in Type K Thermocouples.** Practical reliability
   guide; quantifies drift mechanisms (oxidation, ordering) and rates.
   <https://blog.wika.com/us/knowhow/aging-and-drift-in-type-k-thermocouples/>
2. **Cambridge University — Thermocouple Drift (UTC materials science).**
   Distinguishes reversible crystallographic ordering (< 800 °C) from
   irreversible Seebeck shift; foundational for the bias-rate model.
   <https://www.msm.cam.ac.uk/utc/thermocouple/pages/Drift.html>
3. **Bentley & Morgan — Long-term drift in mineral-insulated Nicrosil-sheathed
   type K thermocouples.** Sensors & Actuators A, 1990. Quantitative drift
   data over thousands of hours; supports Arrhenius framing.
   <https://www.sciencedirect.com/science/article/pii/0924424790800435>
4. **HW-group — Sensor Accuracy over Time.** Operational stability numbers
   for PT100 RTDs: ≤ 0.02 °C/yr below 450 °C, ~0.3 °C/yr at sustained
   100 °C. Source for our well-maintained boundary.
   <https://www.hw-group.com/support/sensor-accuracy-over-time>
5. **HGS Industrial — RTD Sensor Stability or Drift Guide.** Construction-
   dependent stability characteristics (wire-wound vs flat film) and
   environmental factors that drive long-term drift.
   <https://www.hgsind.com/blog/rtd-sensor-stability-or-drift>
6. **Peak Sensors — What Is a Thermocouple Drift?** Plain-language summary
   of drift causes (vibration, thermal cycling, oxidation) used to motivate
   the load- and humidity-coupling terms.
   <https://peaksensors.com/what-is/what-is-a-thermocouple-drift/>
7. **Electronics Cooling — Environmental Effects on Thermocouples (2025).**
   Modern review of mechanical, chemical, and humidity-driven failure
   pathways; supports the `γ_H` corrosion-of-solder term.
   <https://www.electronics-cooling.com/2025/01/tech-brief-environmental-effects-on-thermocouples/>

---

## Open questions

- **PT100 vs Type-K choice.** We model PT100 numbers (more stable, the right
  choice for a 150 °C zone). If HP S100 documentation reveals a thermocouple,
  we triple `α_b` and keep everything else.
- **Bias sign distribution.** Currently random ±1 at install. Real RTDs drift
  positive (Pt oxide → higher R → higher T-reading); thermocouples often
  drift negative. If we commit to PT100, force `sign = +1`.
- **Dropout rate calibration.** `p_dropout = 5e-5/tick` is a guess. A real
  field rate of "one stuck reading per ~month at nominal" would be a useful
  number to ground this in; for the demo it gives ~5–8 dropout events over
  a 6-month run, which feels right.
- **Per-metric `sensor_health` granularity.** We expose one entry
  (`"temperature_C"`). For multi-metric sensors (a future load cell on the
  blade), the helper signature is the same but the dict has multiple keys —
  worth capturing in the engine helper signature now.
- **Should `TROUBLESHOOT` partially restore trust?** Currently no state
  change. Argument for: a fresh inspection is a calibration check and
  effectively zeros bias for `last_inspected_tick`-window. We default no
  to keep the three event kinds clearly distinct; revisit if Phase 3 needs
  a finer-grained operator action.

## Synthetic prompt

> Add `docs/research/19-temperature-sensor.md` modelling the temperature
> sensor as both a Phase-1 component (failing on `bias_C` Arrhenius drift +
> sub-linear `noise_sigma_C` growth, hard-fail at `|bias| > 5 °C`) and the
> reference §3.4 sensor model (mapping true → observed via bias + Gaussian
> noise + Poisson stuck dropouts → catastrophic absent, with `sensor_note`
> classification). Couple out via `CouplingContext.factors["sensor_bias_c"]`
> and `["sensor_noise_sigma_c"]` consumed by the heater control loop to
> close the heater ↔ sensor feedback. Distinguish TROUBLESHOOT (no state
> change), FIX (zero bias only), REPLACE (zero both, age=0). Cite ≥2 real
> sources on thermocouple/RTD drift; follow the existing TL;DR / Background
> / Decision / Why this fits / References / Open questions structure.

Generated with Claude Opus 4.7
