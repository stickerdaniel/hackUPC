"""Driver-coverage matrix — every component reacts to all four drivers.

For each (component, driver) pair: varying the driver from 0 → 1 with the
other three held neutral changes the per-tick metric increment in the
expected direction. Three stressors (temperature_stress,
humidity_contamination, operational_load) → strictly larger damage; the
maintenance_level damper → strictly smaller damage.

We compare the *primary damage metric* per component because that's the
metric every component path moves monotonically. The hot-environment
cell for heater + sensor uses an Arrhenius-friendly Environment so the
AF responds visibly to the driver.
"""

from __future__ import annotations

import pytest

from copilot_sim.components import blade, cleaning, heater, nozzle, rail, sensor
from copilot_sim.domain.coupling import CouplingContext
from copilot_sim.domain.drivers import Drivers
from copilot_sim.drivers_src.environment import Environment

from ..components._helpers import make_rng

_PRIMARY_METRIC = {
    "blade": "wear_level",
    "rail": "misalignment",
    "nozzle": "thermal_fatigue",
    "cleaning": "wiper_wear",
    "heater": "resistance_drift",
    "sensor": "bias_offset",
}

_STEPS = {
    "blade": blade.step,
    "rail": rail.step,
    "nozzle": nozzle.step,
    "cleaning": cleaning.step,
    "heater": heater.step,
    "sensor": sensor.step,
}

_INITIALS = {
    "blade": blade.initial_state,
    "rail": rail.initial_state,
    "nozzle": nozzle.initial_state,
    "cleaning": cleaning.initial_state,
    "heater": heater.initial_state,
    "sensor": sensor.initial_state,
}


def _hot_env() -> Environment:
    """Hot in-zone env so the heater/sensor Arrhenius responds visibly."""
    return Environment(
        base_ambient_C=150.0,
        amplitude_C=0.0,
        weekly_runtime_hours=80.0,
        vibration_level=0.10,
        cumulative_cleanings=0,
        hours_since_maintenance=0.0,
        start_stop_cycles=0,
    )


def _coupling(drivers: Drivers) -> CouplingContext:
    factors = {
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
    return CouplingContext(
        temperature_stress_effective=drivers.temperature_stress,
        humidity_contamination_effective=drivers.humidity_contamination,
        operational_load_effective=drivers.operational_load,
        maintenance_level_effective=drivers.maintenance_level,
        factors=CouplingContext.freeze_factors(factors),
    )


def _step_once(component_id: str, drivers: Drivers, env: Environment) -> float:
    step_fn = _STEPS[component_id]
    initial = _INITIALS[component_id]()
    rng = make_rng(component_id)
    new = step_fn(initial, _coupling(drivers), drivers, env, dt=1.0, rng=rng)
    return float(new.metrics[_PRIMARY_METRIC[component_id]])


def _baseline(component_id: str) -> float:
    """Initial value of the primary metric (sensor's noise_sigma is non-zero)."""
    return float(_INITIALS[component_id]().metrics[_PRIMARY_METRIC[component_id]])


@pytest.mark.parametrize(
    "component_id,driver,direction",
    [
        # Temperature stress — three stressors plus heater/sensor Arrhenius.
        ("blade", "temperature_stress", "up"),
        ("rail", "temperature_stress", "up"),
        ("nozzle", "temperature_stress", "up"),
        ("cleaning", "temperature_stress", "up"),
        ("heater", "temperature_stress", "up"),
        ("sensor", "temperature_stress", "up"),
        # Humidity / contamination.
        ("blade", "humidity_contamination", "up"),
        ("rail", "humidity_contamination", "up"),
        ("nozzle", "humidity_contamination", "up"),
        ("cleaning", "humidity_contamination", "up"),
        ("heater", "humidity_contamination", "up"),
        ("sensor", "humidity_contamination", "up"),
        # Operational load.
        ("blade", "operational_load", "up"),
        ("rail", "operational_load", "up"),
        ("nozzle", "operational_load", "up"),
        ("cleaning", "operational_load", "up"),
        ("heater", "operational_load", "up"),
        ("sensor", "operational_load", "up"),
        # Maintenance level — damper, so direction flips.
        ("blade", "maintenance_level", "down"),
        ("rail", "maintenance_level", "down"),
        ("nozzle", "maintenance_level", "down"),
        ("cleaning", "maintenance_level", "down"),
        ("heater", "maintenance_level", "down"),
        ("sensor", "maintenance_level", "down"),
    ],
)
def test_driver_changes_primary_metric_in_expected_direction(
    component_id: str, driver: str, direction: str
) -> None:
    env = _hot_env()
    base = {
        "temperature_stress": 0.30,
        "humidity_contamination": 0.30,
        "operational_load": 0.50,
        "maintenance_level": 0.30,
    }

    low = dict(base)
    low[driver] = 0.0
    high = dict(base)
    high[driver] = 1.0

    low_metric = _step_once(component_id, Drivers(**low), env)
    high_metric = _step_once(component_id, Drivers(**high), env)

    baseline = _baseline(component_id)
    low_delta = low_metric - baseline
    high_delta = high_metric - baseline

    if direction == "up":
        assert high_delta > low_delta, (
            f"{component_id}: increasing {driver} should increase damage; "
            f"got low_delta={low_delta:.6f}, high_delta={high_delta:.6f}"
        )
    else:
        assert high_delta < low_delta, (
            f"{component_id}: increasing maintenance_level should decrease damage; "
            f"got low_delta={low_delta:.6f}, high_delta={high_delta:.6f}"
        )
