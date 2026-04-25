"""Aging math + RNG plumbing shared by every component step.

These helpers are intentionally tiny and free of any cross-component
dependencies so that components, the engine, sensors and tests can pull from
them without import cycles. Everything here is deterministic and side-effect
free.

The Weibull baseline + multiplicative composition rule, the
`(1 − 0.8·M)` maintenance damper and the `0.75 / 0.45 / 0.20` status
thresholds are locked in `docs/research/04-aging-baselines-and-normalization.md`
and the plan at `~/.claude/plans/distributed-splashing-turtle.md`.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np

from ..domain.enums import OperationalStatus

# Status thresholds. `>= 0.75 / >= 0.40 / >= 0.15 / < 0.15` per docs/research/04
# and the README. We keep them as module constants so the test suite can
# import the same numbers (no magic literals duplicated in tests).
HEALTH_FUNCTIONAL = 0.75
HEALTH_DEGRADED = 0.40
HEALTH_CRITICAL = 0.15

# Weeks per simulated tick. The plan locked dt = 1 simulated week.
WEEKS_PER_TICK = 1.0

# Strength of the maintenance damper at maintenance_level == 1. With M=1 the
# damper is `(1 - 0.8) = 0.2`, i.e. a well-maintained machine still ages but
# at one-fifth the rate of a fully neglected one.
MAINTENANCE_DAMPER_STRENGTH = 0.8


def clip01(x: float) -> float:
    """Clamp a value to the [0, 1] interval. Used for every health and
    metric-derived quantity that has a hard physical range.
    """
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return x


def maintenance_damper(maintenance_level_effective: float) -> float:
    """Return `(1 - 0.8·M)` clamped to [0.2, 1.0].

    Multiplied into every component damage increment so that good maintenance
    slows aging without ever fully arresting it. Centralising the formula in
    one place lets a lint sweep grep for direct reads of
    `maintenance_level_effective` outside this module and flag duplication.
    """
    m = clip01(maintenance_level_effective)
    return 1.0 - MAINTENANCE_DAMPER_STRENGTH * m


def weibull_baseline(age_ticks: int, eta_weeks: float, beta: float) -> float:
    """Reliability function `R(t) = exp(-(t/eta)^beta)`.

    `t` is in weeks (`age_ticks · WEEKS_PER_TICK`). Returns a value in
    `[0, 1]` representing the probability the part has not yet hit its
    characteristic-life damage from baseline aging alone (i.e. the
    "no-driver" lifetime curve). Multiplied with the driver-damage term
    `(1 - D)` per the doc-04 composition rule.
    """
    if eta_weeks <= 0:
        return 0.0
    t_weeks = age_ticks * WEEKS_PER_TICK
    return math.exp(-((t_weeks / eta_weeks) ** beta))


def status_from_health(health_index: float) -> OperationalStatus:
    """Map a true health index in `[0, 1]` to the four-step status enum.

    Strict-`<` everywhere so the boundary case (`0.75`, `0.45`, `0.20`) lands
    in the *better* bucket. Frozen by tests so a refactor cannot silently
    move the cliff.
    """
    if health_index >= HEALTH_FUNCTIONAL:
        return OperationalStatus.FUNCTIONAL
    if health_index >= HEALTH_DEGRADED:
        return OperationalStatus.DEGRADED
    if health_index >= HEALTH_CRITICAL:
        return OperationalStatus.CRITICAL
    return OperationalStatus.FAILED


def _component_id_digest(component_id: str) -> int:
    """Stable, process-independent uint64 digest of a component id.

    Python's built-in `hash(str)` is salted by `PYTHONHASHSEED`, so it would
    give different RNG streams across processes — exactly the determinism
    bug the plan calls out. `blake2b` digest is bit-stable across machines,
    Python versions, and import order.
    """
    return int.from_bytes(
        hashlib.blake2b(component_id.encode("utf-8"), digest_size=8).digest(),
        byteorder="big",
        signed=False,
    )


def derive_component_rng(scenario_seed: int, tick: int, component_id: str) -> np.random.Generator:
    """Return a per-component, per-tick `numpy` Generator.

    Sole sanctioned way for component step functions to obtain randomness.
    Two properties hold by construction:

    1. Same `(scenario_seed, tick, component_id)` ⇒ identical Generator
       state regardless of iteration order, parallelism, or process
       restarts.
    2. Different components at the same tick get statistically independent
       streams (the 64-bit blake2b digest is the third entropy axis).

    `engine/test_rng_determinism.py` enforces both invariants.
    """
    return np.random.default_rng(
        (int(scenario_seed), int(tick), _component_id_digest(component_id))
    )
