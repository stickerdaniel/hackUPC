"""Build the per-tick `CouplingContext` from the immutable `t-1` `PrinterState`.

This is the *only* place cross-component effects enter the engine. Every
component's `step()` reads coupling.*_effective drivers and `coupling.factors[…]`;
no component reads another component's metrics directly. That gives us
update-order independence by construction (`AGENTS.md § Simulation Modeling`)
and a single, queryable `coupling_factors_json` per tick on the historian
that the co-pilot can attribute degradation to upstream causes with.

Locked named factors (doc 05 §CouplingContext derivation):
  powder_spread_quality, blade_loss_frac, rail_alignment_error,
  heater_drift_frac, heater_thermal_stress_bonus, sensor_bias_c,
  sensor_noise_sigma_c, control_temp_error_c, cleaning_efficiency,
  nozzle_clog_pct.
"""

from __future__ import annotations

from ..domain.coupling import CouplingContext
from ..domain.drivers import Drivers
from ..domain.state import PrinterState
from ..drivers_src.environment import Environment
from .aging import clip01


def _metric(state: PrinterState, component_id: str, metric: str, default: float) -> float:
    """Safe metric read so the very first tick (where some metrics are not
    yet populated) does not crash the coupling builder.
    """
    component = state.components.get(component_id)
    if component is None:
        return default
    return float(component.metrics.get(metric, default))


def build_coupling_context(
    prev: PrinterState,
    drivers: Drivers,
    env: Environment,
    dt: float,  # noqa: ARG001 — kept in the contract for symmetry with step()
) -> CouplingContext:
    """Assemble the named factors and bump each raw driver into its
    `*_effective` form. Sub-unity gains everywhere keep the system bounded
    (doc 05 §stability).
    """
    # --- Pull prev component damage metrics. Defaults are the new-part values
    # so the first tick has zero cascade impact.
    blade_wear = clip01(_metric(prev, "blade", "wear_level", 0.0))
    rail_misalignment = clip01(_metric(prev, "rail", "misalignment", 0.0))
    nozzle_clog_pct = clip01(_metric(prev, "nozzle", "clog_pct", 0.0))
    cleaning_eff = clip01(_metric(prev, "cleaning", "cleaning_effectiveness", 1.0))
    heater_drift = _metric(prev, "heater", "resistance_drift", 0.0)
    sensor_bias = _metric(prev, "sensor", "bias_offset", 0.0)
    sensor_noise = _metric(prev, "sensor", "noise_sigma", 0.0)

    # Heater drift expressed as a [0,1] fraction so downstream coupling has a
    # bounded knob. 0.15 (≈ 15 % from nominal) is the failed-element anchor
    # in doc 04's normalization table.
    heater_drift_frac = clip01(heater_drift / 0.15)

    # Powder-spread quality: blade and rail are the two contributors. A new
    # printer scores 1.0; bad blade + bad rail can drop it well below 0.5.
    powder_spread_quality = clip01(1.0 - 0.6 * blade_wear - 0.3 * rail_misalignment)

    # The drifted-heater bonus that propagates into the nozzle's thermal
    # cycling — a drifted element overshoots its setpoint, so each layer
    # cure is hotter and steeper.
    heater_thermal_stress_bonus = 0.10 * heater_drift_frac

    # The sensor bias the controller actually trusts — heater closed-loop
    # drives toward (setpoint - control_temp_error_c). Sign convention from
    # the plan: sensor reads consistently low (+1), so a positive bias
    # makes the controller over-shoot.
    control_temp_error_c = sensor_bias

    # --- Effective drivers (raw + small sub-unity coupling bumps).
    temperature_stress_effective = clip01(
        drivers.temperature_stress + heater_thermal_stress_bonus + 0.05 * abs(control_temp_error_c)
    )
    # Blade wear contaminates the powder bed; degraded spread quality
    # leaves more residual powder; both feed contamination.
    humidity_contamination_effective = clip01(
        drivers.humidity_contamination + 0.20 * blade_wear + 0.10 * (1.0 - powder_spread_quality)
    )
    # Clogged nozzles force more passes per part — a load amplifier.
    operational_load_effective = clip01(drivers.operational_load + 0.15 * nozzle_clog_pct)
    maintenance_level_effective = clip01(drivers.maintenance_level)

    factors = {
        "powder_spread_quality": powder_spread_quality,
        "blade_loss_frac": blade_wear,
        "rail_alignment_error": rail_misalignment,
        "heater_drift_frac": heater_drift_frac,
        "heater_thermal_stress_bonus": heater_thermal_stress_bonus,
        "sensor_bias_c": sensor_bias,
        "sensor_noise_sigma_c": sensor_noise,
        "control_temp_error_c": control_temp_error_c,
        "cleaning_efficiency": cleaning_eff,
        "nozzle_clog_pct": nozzle_clog_pct,
    }

    return CouplingContext(
        temperature_stress_effective=temperature_stress_effective,
        humidity_contamination_effective=humidity_contamination_effective,
        operational_load_effective=operational_load_effective,
        maintenance_level_effective=maintenance_level_effective,
        factors=CouplingContext.freeze_factors(factors),
    )


def ambient_temperature_C_effective(env: Environment, coupling: CouplingContext) -> float:
    """Heater/sensor Arrhenius components consume this derived ambient.

    Implements the plan's audit equation:
        T_eff = base_ambient_C + amplitude_C · (2·temp_stress_eff − 1)

    so the brief's `temperature_stress` Driver flows through directly into
    the Kelvin temperature the Arrhenius AF sees. The driver-coverage test
    asserts a strict monotone effect on the heater and sensor metrics.
    """
    return env.base_ambient_C + env.amplitude_C * (
        2.0 * coupling.temperature_stress_effective - 1.0
    )
