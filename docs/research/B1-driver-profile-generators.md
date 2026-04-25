# B1 Driver Profile Generators

## TL;DR

Use a sinusoidal day/night cycle for temperature stress, an Ornstein-Uhlenbeck (OU) process for humidity drift, a clipped random walk for operational load, and a deterministic sawtooth with additive noise for maintenance level. All four are pure NumPy, seeded for determinism, and parameterized so Barcelona and Phoenix produce visibly distinct traces.

## Background

The simulator needs four scalar drivers at each tick (e.g., 1 tick = 1 minute or 1 hour). Drivers must be:

- Realistic enough to motivate the failure-probability engine.
- Simple enough to implement in under an hour.
- Parameterizable so different deployment sites look different.
- Reproducible via a fixed RNG seed.

## Options Considered

| Driver | Considered | Rejected because |
|---|---|---|
| Temperature | Sinusoidal, AR(1), real data replay | AR(1) has no physical interpretability; real data replay adds I/O complexity |
| Humidity | OU process, AR(1), Beta-distributed draws | AR(1) lacks mean reversion guarantee; Beta draws are i.i.d. (no autocorrelation) |
| Operational load | Clipped random walk, Beta-distributed, fixed schedule | Fixed schedule is not stochastic; Beta draws again i.i.d. |
| Maintenance | Sawtooth reset, exponential decay, step function | Step function has no degradation gradient; exponential decay is fine but sawtooth is more readable |
| Contamination spikes | Poisson inter-arrival + additive pulse | Bernoulli per-tick is equivalent for low rates and simpler; chosen as optional overlay |

## Recommendation

### Driver 1 — Temperature Stress (sinusoidal)

**Formula:**

```
T(t) = mu_T + A_T * sin(2*pi*t / P + phi) + epsilon
```

where `t` is tick index, `P` = ticks per day, `phi` = phase offset (peak at ~14:00), `epsilon ~ N(0, sigma_T)`.

**NumPy snippet:**

```python
rng = np.random.default_rng(seed)
t = np.arange(n_ticks)
T = mu_T + A_T * np.sin(2 * np.pi * t / ticks_per_day + phi) \
    + rng.normal(0, sigma_T, n_ticks)
T = np.clip(T, 0, 100)
```

**Defaults:**

| Parameter | Barcelona | Phoenix |
|---|---|---|
| `mu_T` | 22 C | 36 C |
| `A_T` (amplitude) | 6 C | 12 C |
| `sigma_T` (noise) | 1.0 | 1.5 |
| `phi` | `-pi/2` (peak noon) | `-pi/2` |
| `ticks_per_day` | 1440 (1 min ticks) | 1440 |

### Driver 2 — Humidity (Ornstein-Uhlenbeck)

**Formula (exact discrete update):**

```
H(t+dt) = mu_H + (H(t) - mu_H) * exp(-theta*dt)
           + sigma_H * sqrt(1 - exp(-2*theta*dt)) * N(0,1)
```

The exact update avoids Euler drift for large `dt`.

**NumPy snippet:**

```python
decay = np.exp(-theta * dt)
noise_scale = sigma_H * np.sqrt(1 - decay**2)
H = np.empty(n_ticks)
H[0] = mu_H
for i in range(1, n_ticks):
    H[i] = mu_H + (H[i-1] - mu_H) * decay \
           + noise_scale * rng.standard_normal()
H = np.clip(H, 0, 100)
```

**Defaults:**

| Parameter | Barcelona | Phoenix |
|---|---|---|
| `mu_H` (long-run mean %) | 70 | 28 |
| `theta` (reversion speed) | 0.05 | 0.05 |
| `sigma_H` (volatility) | 5.0 | 4.0 |
| `dt` | 1.0 | 1.0 |

### Driver 3 — Operational Load (clipped random walk)

**Formula:**

```
L(t) = clip(L(t-1) + epsilon, L_min, L_max)
epsilon ~ N(0, sigma_L)
```

**NumPy snippet:**

```python
steps = rng.normal(0, sigma_L, n_ticks)
L = np.empty(n_ticks)
L[0] = L0
for i in range(1, n_ticks):
    L[i] = np.clip(L[i-1] + steps[i], L_min, L_max)
```

**Defaults:** `L0 = 0.5`, `sigma_L = 0.02`, `L_min = 0.1`, `L_max = 1.0`. Same across sites (load is schedule-driven, not climate-driven).

### Driver 4 — Maintenance Level (sawtooth degradation)

**Formula:**

```
M(t) = 1 - (t mod T_maint) / T_maint + epsilon
```

Starts near 1.0 (fresh), decays linearly to ~0, then resets.

**NumPy snippet:**

```python
t = np.arange(n_ticks)
M = 1.0 - (t % T_maint) / T_maint \
    + rng.normal(0, 0.01, n_ticks)
M = np.clip(M, 0, 1)
```

**Defaults:** `T_maint = 10080` (7 days * 1440 min). Same across sites.

### Optional overlay — Contamination Spikes (Poisson)

Draw spike times via inter-arrival sampling, then add a pulse of height `spike_amp` with exponential decay:

```python
n_spikes = rng.poisson(lam * n_ticks)
spike_times = rng.integers(0, n_ticks, n_spikes)
for s in spike_times:
    width = rng.integers(5, 30)
    L[s:s+width] = np.clip(L[s:s+width] + spike_amp, 0, 1)
```

**Defaults:** `lam = 2e-4` events/tick (~0.3/day), `spike_amp = 0.25`.

## Seeding for Determinism

```python
rng = np.random.default_rng(seed=42)  # pass to all generators
```

Pass the same `rng` object through all drivers so one seed controls all stochasticity. For reproducible multi-run sweeps, use `np.random.default_rng(seed + run_id)`.

## Barcelona vs Phoenix — Visible Differences

- Temperature: Phoenix amplitude doubles (12 vs 6 C) and mean is 14 C higher — the curve hits the stress threshold far more often.
- Humidity: Phoenix mean is 28% vs Barcelona 70% — the OU process oscillates around a completely different baseline; stress thresholds set at e.g. >80% or <20% will fire in different cities.
- Load and maintenance are site-agnostic by design, keeping the demo contrast focused on climate.

## Open Questions

1. Should ticks be minutes or hours? Minutes give smoother sinusoids but longer arrays (525k/year); hours may suffice for a 60-sec demo.
2. Is the contamination spike overlay a separate driver or a modifier on operational load?
3. Should humidity and temperature be correlated (e.g., Mediterranean: cool nights are humid)? A shared OU noise term could handle this but adds complexity.

## References

- [Ornstein-Uhlenbeck Simulation with Python — QuantStart](https://www.quantstart.com/articles/ornstein-uhlenbeck-simulation-with-python/)
- [Ornstein-Uhlenbeck process — Wikipedia](https://en.wikipedia.org/wiki/Ornstein%E2%80%93Uhlenbeck_process)
- [Stochastic Processes Simulation: The OU Process — Towards Data Science](https://towardsdatascience.com/stochastic-processes-simulation-the-ornstein-uhlenbeck-process-e8bff820f3/)
- [numpy.random.poisson — NumPy v2.4 Manual](https://numpy.org/doc/stable/reference/random/generated/numpy.random.poisson.html)
- [Poisson Process Simulation and Analysis in Python — Medium](https://medium.com/@abhash-rai/poisson-process-simulation-and-analysis-in-python-e62f69d1fdd0)
- [scipy.signal.sawtooth — SciPy docs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sawtooth.html)
- [Simple timeseries generation in Python with mockseries — Medium](https://medium.com/@cdecatheu/simple-timeseries-generation-in-python-with-mockseries-d6b214111814)
- [Barcelona Humidity by Month — weather-and-climate.com](https://weather-and-climate.com/average-monthly-Humidity-perc,barcelona,Spain)
- [Phoenix (AZ) Humidity by Month — weather-and-climate.com](https://weather-and-climate.com/average-monthly-Humidity-perc,phoenix,United-States-of-America)
- [Climate of Barcelona — Wikipedia](https://en.wikipedia.org/wiki/Climate_of_Barcelona)
- [Climate of Phoenix — Wikipedia](https://en.wikipedia.org/wiki/Climate_of_Phoenix)
