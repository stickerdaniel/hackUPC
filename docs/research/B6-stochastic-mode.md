# B6 — Stochastic Mode: Chaos Injection for the Metal Jet S100 Simulator

**Phase:** 2 bonus  
**Owner:** Chris (sim loop)  
**Status:** Research complete — concrete spec below

---

## TL;DR

Layer stochasticity on top of the deterministic Phase 1 engine by (1) adding
per-driver Gaussian noise every tick and (2) injecting rare spike events drawn
from a Poisson process. Expose both via a single `chaos_level: 0..3` integer
in the run config. Use `numpy.random.default_rng(seed)` with `SeedSequence`
to keep everything reproducible. Write every spike to the existing historian
as a structured `chaos_event` row so the Phase 3 chatbot can cite it
verbatim.

---

## Background

The Phase 1 engine is fully deterministic: same inputs → same outputs. Phase 2
needs to wrap it in a loop that can optionally perturb the four driver values
before passing them in. Two complementary disturbance classes cover the
realistic failure space:

- **Continuous noise** — small, every-tick fluctuations in sensor readings and
  environmental conditions (Gaussian additive noise on each driver).
- **Discrete spikes** — rare, large, instantaneous shocks such as a
  contamination burst, a humidity surge, or a sudden drop in maintenance
  quality. These are memoryless and naturally modelled by a Poisson process,
  where inter-arrival times follow an exponential distribution with rate
  parameter λ (events per hour).

For binder jetting specifically, the real failure modes that motivate these
categories are: nozzle clogging from powder ingestion spikes, humidity swings
that alter binder imbibition, abrasive contamination events that accelerate
blade wear, and sudden lapses in maintenance discipline.

---

## Options Considered

| Approach | Pros | Cons |
|---|---|---|
| Pure Gaussian noise on all drivers | Simple, one parameter per driver | Cannot model sudden shocks; unrealistic tails |
| Poisson spike-only | Captures rare events clearly | Misses background jitter |
| Gaussian noise + Poisson spikes (chosen) | Realistic at both timescales | Slightly more parameters |
| Markov chain regime switching | Rich multi-state model | Overkill for a hackathon; hard to explain |
| Correlated noise (Ornstein-Uhlenbeck) | Physically motivated drift | Requires dt-dependent update; complexity cost high |

---

## Recommendation — Concrete Spec

### Noise model per driver

Apply additive zero-mean Gaussian noise every tick before calling the Phase 1
engine. Scale `σ` by `chaos_level` so level 0 means no perturbation.

| Driver | Physical unit | σ (level 1) | σ (level 2) | σ (level 3) |
|---|---|---|---|---|
| Temperature Stress | °C deviation | 0.5 | 1.5 | 3.0 |
| Humidity / Contamination | 0–1 index | 0.005 | 0.015 | 0.03 |
| Operational Load | cycles/tick | 0.01 | 0.03 | 0.06 |
| Maintenance Level | 0–1 coefficient | 0.002 | 0.006 | 0.012 |

Noise is clipped to the valid range of each driver after application.

### Spike rate λ (Poisson process)

Inter-arrival time for the next spike: `t_wait ~ Exponential(1/λ)`.
Generate via `rng.exponential(scale=1/lambda_hz)` where time is in hours.

| chaos_level | λ (spikes / hour) | Mean wait |
|---|---|---|
| 0 | 0 | no spikes |
| 1 | 0.02 | ~50 h |
| 2 | 0.1 | ~10 h |
| 3 | 0.5 | ~2 h |

Spike types (chosen uniformly at random from the applicable set):

| spike_type | Driver affected | Magnitude | Duration |
|---|---|---|---|
| contamination_burst | Humidity / Contamination | +0.15–0.30 | 1 tick |
| humidity_surge | Humidity / Contamination | +0.10–0.25 | 1–3 ticks |
| temp_shock | Temperature Stress | ±5–15 °C | 1 tick |
| maintenance_lapse | Maintenance Level | −0.10–0.25 | 1 tick |

### Seeding for reproducibility

```python
import numpy as np

def make_rng(seed: int | None) -> np.random.Generator:
    """
    Returns a reproducible Generator. Pass seed=None for OS entropy.
    Use SeedSequence.spawn to give each subsystem its own independent stream.
    """
    ss = np.random.SeedSequence(seed)
    noise_rng, spike_rng = [np.random.default_rng(s) for s in ss.spawn(2)]
    return noise_rng, spike_rng
```

Store the resolved integer seed in the run metadata row so any run can be
replayed exactly. Never use the legacy `np.random.seed()` global state.

### Config interface

```yaml
# run_config.yaml
simulation:
  seed: 42          # integer or null (OS entropy)
  chaos_level: 2    # 0 = deterministic, 1 = mild, 2 = moderate, 3 = severe
```

`chaos_level: 0` must be the default so Phase 1 correctness tests are
unaffected.

### Event log table addition

Add a `chaos_events` table (or append to the existing historian with
`event_type = "chaos"`):

| Column | Type | Example |
|---|---|---|
| run_id | TEXT | `run_20260425_001` |
| tick | INTEGER | `42` |
| sim_time_h | REAL | `42.0` |
| spike_type | TEXT | `contamination_burst` |
| driver_affected | TEXT | `humidity_contamination` |
| delta_applied | REAL | `0.22` |
| rng_seed | INTEGER | `42` |

This makes every Phase 3 response citable: "A contamination spike
(`delta=+0.22`) at t=42 h (tick 42, run run_20260425_001) triggered the
cascade."

---

## Open Questions

1. Should spikes persist for multiple ticks (exponential decay back to
   baseline) rather than single-tick impulses? More realistic but adds a
   "spike state" to carry between ticks.
2. Correlated spikes: should a `contamination_burst` simultaneously raise
   humidity and reduce maintenance level (because operators scramble)? Natural
   but needs a simple dependency matrix.
3. Driver noise should arguably be auto-correlated (not i.i.d. per tick).
   An Ornstein-Uhlenbeck process is the standard fix; defer unless time
   permits.
4. Should `chaos_level` be a continuous float `0.0..1.0` for finer control?
   The integer enum is simpler to demo.

---

## References

- NumPy SeedSequence and default_rng best practices:
  https://numpy.org/doc/stable/reference/random/bit_generators/generated/numpy.random.SeedSequence.html
- NumPy Random Generator (PCG64) reproducibility:
  https://www.plus2net.com/python/numpy-random-generator.php
- Poisson process inter-arrival time generation (exponential inverse-CDF):
  https://preshing.com/20111007/how-to-generate-random-timings-for-a-poisson-process/
- Binder saturation in metal binder jetting — practical constraints:
  https://www.pim-international.com/articles/saturation-in-metal-binder-jetting-simple-in-principle-complicated-in-practice/
- Nozzle clogging and inkjet AM failure modes:
  https://imagexpert.com/three-common-issues-with-inkjet-additive-manufacturing-and-how-to-address-them/
- Humidity and powder moisture effects on binder jetting:
  https://www.sciencedirect.com/article/pii/S1526612521006757
- Chaos engineering fault injection patterns (for nomenclature):
  https://www.matterai.so/guides/how-to-implement-chaos-engineering-building-resilient-systems-with-failure-injection
- Scientific Python RNG best practices blog:
  https://blog.scientific-python.org/numpy/numpy-rng/
