# Driver Profiles, Time Step, and Chaos Mode

## TL;DR

For Phase 2 we drive the Phase 1 engine on a **fixed `dt = 1` simulated week** for **multi-year horizons** (default 5 years → 260 ticks). Each of the four drivers gets the simplest viable generator at weekly granularity: **seasonal-only sinusoid** for Temperature (day/night collapsed into the weekly average), an **Ornstein–Uhlenbeck** mean-reverter for Humidity/Contamination, a **monotonic cumulative + weekly duty-cycle** signal for Operational Load, and a **step function** for Maintenance Level. A **stochastic chaos layer** (Poisson-timed thermal events, contamination batches, missed maintenance weeks) sits on top, gated by a `chaos: bool` config flag. Every random draw goes through a single `numpy.random.default_rng(seed)` so runs are bit-exact reproducible.

> **Driver schema is locked at 4** — `Drivers(temperature_stress, humidity_contamination, operational_load, maintenance_level)`, exactly as the brief specifies and as already implemented in `sim/src/copilot_sim/domain/drivers.py`. We do **not** split `humidity_contamination` into separate humidity vs powder_contamination drivers; powder contamination cascades in via the coupling matrix (doc 05) by adjusting `humidity_contamination_effective`, not by adding a 5th driver.

> **Loop-managed state fields** that the engine reads but the driver generator does NOT produce: `continuous_runtime_hours`, `cycles_since_start`, `hours_since_maintenance`. These are owned by the simulation loop and are derived from tick count + the operator-event stream. They live on `PrinterState` (or a sibling object) per the §3.4 implementation notes, not in `Drivers`.

## Background

Phase 2 wraps the deterministic Phase 1 logic engine in a time-advancing loop and persists every `(t, drivers, state)` tuple to a SQLite historian. The loop needs to *generate* the four input drivers at each tick because we don't have a real S100 telemetry stream. The drivers must be (a) physically plausible enough to drive realistic component degradation, (b) cheap to compute (we'll run thousands of ticks live during the demo), and (c) seedable for reproducible "what-if" demos to the HP judges.

## Decision

### Per-driver generators

| Driver | Generator | Parameter recommendation |
| :--- | :--- | :--- |
| **Temperature Stress (°C)** | `T(t) = T_mean + A_day·sin(2π·t/24) + A_year·sin(2π·t/8760) + N(0, σ_T)` | `T_mean=22`, `A_day=3`, `A_year=5`, `σ_T=0.4` |
| **Humidity / Contamination (0–1)** | Ornstein–Uhlenbeck SDE: `dX = θ(μ − X)dt + σ dW`, clipped to `[0,1]` | `μ=0.35`, `θ=0.05 hr⁻¹` (≈20 hr reversion), `σ=0.04`, `X₀=0.35` |
| **Operational Load** | `cum_hours += dt · duty(t)` with weekly duty-cycle (`ON` Mon–Fri 06:00–22:00, else `OFF`) | ~80 print hours/week; expose `cum_hours` and `cum_cycles` |
| **Maintenance Level (0–1)** | Right-continuous step function: decays linearly `−0.0003/hr`, jumps to `1.0` at scheduled events | Scheduled service every **720 hr** (~monthly); decay floor `0.2` |

### Time step and horizon

- **`dt = 1` simulated week (= 168 sim-hours = 604,800 s).**
- **Horizon = multiple years** (default working assumption: 5 years → 260 ticks; revise once we settle the exact horizon with the team).
- Justification: real component MTBFs sit in the months-to-years band, so year-scale horizons let us tell the wear story honestly without compressing the failure curves. Generating hourly drivers over multi-year horizons is impractical (43,800+ values per driver per year); weekly granularity is hand-authorable or trivially derivable from monthly climatology. The chart still has 260+ dots over 5 years — smooth enough for the dashboard.
- **What we lose vs hourly**: day/night thermal cycling and sub-week chaos events (a 3-hour temperature spike). We accept this — chaos events at this scale are reframed as "a contaminated powder batch arrives this week" or "HVAC was out for 2 days" (a fraction of a tick).
- **What we keep**: month-scale dynamics (maintenance every ~4 weeks → 4 ticks between resets, enough to show rising-degradation slopes), seasonal weather (52 ticks/year), multi-year cumulative wear.
- **`dt` stays configurable** in case we want a "fast-forward" demo mode (`dt = 4 weeks` → ~65 ticks for 5 years) or a "fine-grain Phase-1 unit-test" mode (`dt = 1 day`).

### Chaos / stochastic layer (Phase 2 bonus pattern C)

Overlaid on the deterministic profile when `config.chaos=True`. All draws share the seeded RNG.

| Event | Process | Magnitude | Effect |
| :--- | :--- | :--- | :--- |
| **Temp spike** (HVAC fault) | Poisson, `λ = 2 / month` | `ΔT ~ N(8, 2) °C`, decays `exp(−t/6 hr)` | added to `T(t)` |
| **Contamination burst** (powder lot change, door opened) | Poisson, `λ = 3 / month` | step `+ U(0.15, 0.35)`, OU absorbs it back | added to `X(t)`, then re-clipped |
| **Skipped maintenance** | Bernoulli `p = 0.1` per scheduled event | event ignored | maintenance step skipped |
| **Sensor noise** (optional) | additive `N(0, σ_sensor)` per driver | small | for Phase 3 grounding stress test |

Poisson arrivals are generated up-front for the whole horizon via cumulative `rng.exponential(1/λ)` interarrival times — standard pattern, O(events) not O(ticks). OU is integrated with **Euler–Maruyama**: `X[i] = X[i-1] + θ(μ − X[i-1])·dt + σ·√dt·rng.standard_normal()`.

### Determinism

Single config field `seed: int = 42`. Loop creates `rng = np.random.default_rng(seed)` once and threads it through every generator + chaos call. Same seed + same config ⇒ byte-identical historian. Different scenarios get different seeds (`seed=42` "nominal", `seed=7` "rough lot", `seed=999` "HVAC failure week").

## Why this fits our case

- **Cheap to demo.** All four generators are vectorisable; the whole 4380-tick driver matrix can be precomputed in <50 ms, leaving the loop budget for the Phase 1 engine and SQLite writes.
- **Physically defensible.** Sinusoidal daily/annual temperature is what real factory HVAC data looks like; OU is the textbook model for bounded, mean-reverting environmental noise (humidity, contamination); Poisson is the standard for rare independent shocks. We can defend each choice in 30 seconds to the HP judges.
- **Cascade-friendly.** A contamination burst → blade wears faster (Phase 1 Archard) → contaminates powder more → nozzle clogs faster. The chaos layer is what makes the Phase 1 cascading-failure bonus *visible* in the historian timeline.
- **Phase-3-friendly.** Seeded scenarios let the LLM agent answer "what happened around hour 1832?" with grounded SQLite queries instead of hallucinating.

## References

- [IPython Cookbook 13.4 — Simulating an SDE (Ornstein–Uhlenbeck, Euler–Maruyama in NumPy)](https://ipython-books.github.io/134-simulating-a-stochastic-differential-equation/)
- [Poisson Process Simulation and Analysis in Python — Abhash Rai, Medium](https://medium.com/@abhash-rai/poisson-process-simulation-and-analysis-in-python-e62f69d1fdd0)

## Open questions

- **Live weather API instead of synthetic temperature?** Open-Meteo is free and flagged as a Phase 1 bonus in the brief. Trade-off: realism vs. reproducibility. Proposal: keep synthetic as default, add an `OpenMeteoDriver` adapter behind the same interface for the "wow" demo run.
- **Should Operational Load expose a stochastic job-length distribution** (e.g. lognormal print-job hours) instead of a flat duty cycle? Probably yes if we want the failure curves to look less "stripey" in the Phase 3 plots.
- **Chaos calibration.** `λ = 2 spikes/month` is a guess. After the first end-to-end run we should tune so that ~1 in 3 seeds produces a `CRITICAL` event within the 6-month horizon — otherwise the demo is boring or apocalyptic.
- **OU clipping bias.** Naive `np.clip` to `[0,1]` distorts the stationary distribution near the bounds. For 36 hr we accept the bias; document it.
