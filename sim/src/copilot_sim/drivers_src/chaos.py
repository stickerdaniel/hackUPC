"""Chaos overlay — driver-layer Poisson and Bernoulli events.

Plan: pre-roll all chaos arrivals at scenario-load time using a dedicated
RNG, NOT per-tick sampling. That way the chaos schedule is stable across
process restarts even if the per-component RNGs evolve.

Three event types:

- `temp_spike_lambda_per_year` — Poisson hits to `temperature_stress`.
- `contamination_burst_lambda_per_year` — Poisson hits to
  `humidity_contamination`.
- `skipped_maintenance_p` — Bernoulli per-tick zeroing of
  `maintenance_level`.

The overlay is disabled by default; enabling it preserves the seasonal /
OU / duty backbone and only adds spikes on selected ticks.
"""

from __future__ import annotations

from collections.abc import Set
from dataclasses import dataclass, field

import numpy as np


@dataclass(slots=True)
class ChaosOverlay:
    enabled: bool = False
    horizon_ticks: int = 0
    temp_spike_lambda_per_year: float = 4.0
    contamination_burst_lambda_per_year: float = 6.0
    skipped_maintenance_p: float = 0.10
    weeks_per_year: float = 52.0

    temp_spike_ticks: Set[int] = field(default_factory=frozenset)
    contamination_burst_ticks: Set[int] = field(default_factory=frozenset)
    skipped_maintenance_ticks: Set[int] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.enabled or self.horizon_ticks <= 0:
            return
        # Resolve a stable inner RNG independent of per-tick component RNGs.
        # Caller is expected to seed via `roll(seed)` before the run starts.

    def roll(self, seed: int) -> None:
        """Pre-roll Poisson and Bernoulli arrivals into immutable tick sets."""
        if not self.enabled:
            return
        rng = np.random.default_rng((int(seed), 0xC4_A0_5E))  # constant tag

        years = max(self.horizon_ticks / self.weeks_per_year, 0.0)
        temp_count = int(rng.poisson(self.temp_spike_lambda_per_year * years))
        contam_count = int(rng.poisson(self.contamination_burst_lambda_per_year * years))

        all_ticks = np.arange(self.horizon_ticks)
        temp_ticks = (
            rng.choice(all_ticks, size=min(temp_count, self.horizon_ticks), replace=False)
            if temp_count > 0
            else np.array([], dtype=int)
        )
        contam_ticks = (
            rng.choice(all_ticks, size=min(contam_count, self.horizon_ticks), replace=False)
            if contam_count > 0
            else np.array([], dtype=int)
        )
        skip_mask = rng.random(self.horizon_ticks) < self.skipped_maintenance_p
        skipped_ticks = np.flatnonzero(skip_mask)

        self.temp_spike_ticks = frozenset(int(t) for t in temp_ticks)
        self.contamination_burst_ticks = frozenset(int(t) for t in contam_ticks)
        self.skipped_maintenance_ticks = frozenset(int(t) for t in skipped_ticks)

    def apply(
        self,
        tick: int,
        temperature_stress: float,
        humidity_contamination: float,
        maintenance_level: float,
    ) -> tuple[float, float, float]:
        if not self.enabled:
            return temperature_stress, humidity_contamination, maintenance_level
        t = float(temperature_stress)
        h = float(humidity_contamination)
        m = float(maintenance_level)
        if tick in self.temp_spike_ticks:
            t = min(1.0, t + 0.30)
        if tick in self.contamination_burst_ticks:
            h = min(1.0, h + 0.40)
        if tick in self.skipped_maintenance_ticks:
            m = 0.0
        return t, h, m
