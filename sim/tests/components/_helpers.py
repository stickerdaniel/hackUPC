"""Shared test helpers for the six component smoke tests.

The plan locks three universal assertions per component (health bounds,
status monotone-forward, per-metric expected direction). Centralising them
here keeps the per-component test files terse and prevents drift between
"the plan said this metric goes up" and what the test actually checks.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

import numpy as np

from copilot_sim.domain.coupling import CouplingContext
from copilot_sim.domain.drivers import Drivers
from copilot_sim.domain.enums import OperationalStatus
from copilot_sim.domain.state import ComponentState
from copilot_sim.drivers_src.environment import Environment

Direction = Literal["non_decreasing", "non_increasing"]

NON_DECREASING: Direction = "non_decreasing"
NON_INCREASING: Direction = "non_increasing"

# Per-component direction table, lifted verbatim from the plan
# (`distributed-splashing-turtle.md` §Implementation order).
EXPECTED_METRIC_DIRECTIONS: Mapping[str, Mapping[str, Direction]] = {
    "blade": {"wear_level": NON_DECREASING, "edge_roughness": NON_DECREASING},
    "rail": {"misalignment": NON_DECREASING, "friction_level": NON_DECREASING},
    "nozzle": {"clog_pct": NON_DECREASING, "thermal_fatigue": NON_DECREASING},
    "cleaning": {
        "wiper_wear": NON_DECREASING,
        "residue_saturation": NON_DECREASING,
        "cleaning_effectiveness": NON_INCREASING,
    },
    "heater": {"resistance_drift": NON_DECREASING, "power_draw": NON_DECREASING},
    "sensor": {
        "bias_offset": NON_DECREASING,  # sign convention: +1 (reads consistently low)
        "noise_sigma": NON_DECREASING,
        "reading_accuracy": NON_INCREASING,
    },
}


# Status order for the monotone-forward assertion.
_STATUS_ORDER: Mapping[OperationalStatus, int] = {
    OperationalStatus.FUNCTIONAL: 0,
    OperationalStatus.DEGRADED: 1,
    OperationalStatus.CRITICAL: 2,
    OperationalStatus.FAILED: 3,
}


def assert_health_in_bounds(state: ComponentState) -> None:
    assert 0.0 <= state.health_index <= 1.0, (
        f"{state.component_id}: health {state.health_index} out of [0, 1]"
    )


def assert_status_monotone_forward(prev: ComponentState, curr: ComponentState) -> None:
    assert _STATUS_ORDER[curr.status] >= _STATUS_ORDER[prev.status], (
        f"{curr.component_id}: status went backwards {prev.status.value} -> {curr.status.value}"
    )


def assert_metrics_in_expected_direction(
    prev: ComponentState, curr: ComponentState, component_id: str
) -> None:
    """For each metric in EXPECTED_METRIC_DIRECTIONS[component_id], assert it
    moved in the expected direction (allowing ties to absorb numeric noise).
    """
    table = EXPECTED_METRIC_DIRECTIONS[component_id]
    for metric, direction in table.items():
        prev_val = prev.metrics.get(metric)
        curr_val = curr.metrics.get(metric)
        assert prev_val is not None and curr_val is not None, (
            f"{component_id}: metric {metric!r} missing from state"
        )
        if direction == "non_decreasing":
            assert curr_val >= prev_val - 1e-12, (
                f"{component_id}: {metric} decreased {prev_val} -> {curr_val}"
            )
        else:
            assert curr_val <= prev_val + 1e-12, (
                f"{component_id}: {metric} increased {prev_val} -> {curr_val}"
            )


def neutral_environment() -> Environment:
    """A vanilla Environment for unit tests — Barcelona-ish defaults."""
    return Environment(
        base_ambient_C=22.0,
        amplitude_C=8.0,
        weekly_runtime_hours=60.0,
        vibration_level=0.10,
        cumulative_cleanings=0,
        hours_since_maintenance=0.0,
        start_stop_cycles=0,
    )


def neutral_drivers(
    *,
    temperature_stress: float = 0.30,
    humidity_contamination: float = 0.30,
    operational_load: float = 0.50,
    maintenance_level: float = 0.0,
) -> Drivers:
    """No-maintenance baseline so smoke tests see real aging."""
    return Drivers(
        temperature_stress=temperature_stress,
        humidity_contamination=humidity_contamination,
        operational_load=operational_load,
        maintenance_level=maintenance_level,
    )


def neutral_coupling(
    drivers: Drivers, factors: Mapping[str, float] | None = None
) -> CouplingContext:
    """Bypass build_coupling_context so component tests run in isolation.

    Effective drivers == raw drivers, no cross-component damage. The
    component-coverage test in engine/test_driver_coverage.py exercises
    the real coupling path; component smoke tests don't need it.
    """
    base_factors = {
        "powder_spread_quality": 1.0,
        "blade_loss_frac": 0.0,
        "rail_alignment_error": 0.0,
        "heater_drift_frac": 0.0,
        "heater_thermal_stress_bonus": 0.0,
        "sensor_bias_c": 0.0,
        "sensor_noise_sigma_c": 0.0,
        "control_temp_error_c": 0.0,
        "cleaning_efficiency": 1.0,
        "nozzle_clog_pct": 0.0,
    }
    if factors:
        base_factors.update(factors)
    return CouplingContext(
        temperature_stress_effective=drivers.temperature_stress,
        humidity_contamination_effective=drivers.humidity_contamination,
        operational_load_effective=drivers.operational_load,
        maintenance_level_effective=drivers.maintenance_level,
        factors=CouplingContext.freeze_factors(base_factors),
    )


def make_rng(component_id: str, seed: int = 0) -> np.random.Generator:
    """Deterministic per-test RNG — tests use the same digest path as the
    engine but without depending on the engine.aging helper directly,
    so test imports stay tight.
    """
    import hashlib

    digest = int.from_bytes(hashlib.blake2b(component_id.encode(), digest_size=8).digest(), "big")
    return np.random.default_rng((seed, 0, digest))
