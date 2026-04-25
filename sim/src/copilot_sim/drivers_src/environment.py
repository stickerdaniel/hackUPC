"""Loop-managed operating context that travels alongside the four `Drivers`.

The brief mandates four driver values; everything else the components want to
know about the running printer (per-scenario ambient temperature swing,
weekly runtime hours, vibration baseline, cumulative cleaning cycles, etc.)
lives here so the engine signature stays a pure function of
`(prev, drivers, env, dt)`.

`Environment` is mutable conceptually — `cumulative_cleanings` ticks up, the
maintenance loop resets `hours_since_maintenance` — but each `Engine.step`
call receives an immutable snapshot. The simulation loop owns the field
updates and creates a fresh `Environment` per tick.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Environment:
    # Per-scenario nominal ambient temperature in °C (e.g. 22 for Barcelona,
    # 32 for Phoenix). Used together with the temperature_stress driver to
    # derive the Kelvin temperature seen by the Arrhenius components.
    base_ambient_C: float
    # ± swing the per-tick temperature_stress driver maps onto: the
    # effective ambient seen by heater/sensor is
    # `base_ambient_C + amplitude_C · (2·temp_stress_eff - 1)`.
    amplitude_C: float
    # Hours of printer activity per simulated week. Drives Archard sliding
    # length, heater duty, nozzle firings and cleaning auto-cycles.
    weekly_runtime_hours: float
    # Constant vibration baseline (0..1). Adds to rail wear in v1.
    vibration_level: float
    # Cumulative count of wiper cleaning cycles since the last cleaning
    # reset. The cleaning component drives wear off this counter.
    cumulative_cleanings: int
    # Hours since the last maintenance event (FIX or REPLACE) of *any*
    # component. Used by the heuristic policy's monthly fallback rule.
    hours_since_maintenance: float
    # Cumulative on/off cycles of the heater since the last reset. Drives
    # Coffin-Manson thermal fatigue accumulation on the nozzle plate.
    start_stop_cycles: int
