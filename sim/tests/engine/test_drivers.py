"""Smoke tests for DriverProfile + chaos overlay determinism."""

from __future__ import annotations

from copilot_sim.drivers_src.assembly import DriverProfile
from copilot_sim.drivers_src.chaos import ChaosOverlay
from copilot_sim.drivers_src.environment import Environment
from copilot_sim.drivers_src.generators import (
    MonotonicDutyLoad,
    OUHumidity,
    SinusoidalSeasonalTemp,
    StepMaintenance,
)


def _profile(*, chaos_enabled: bool, seed: int = 42, horizon: int = 260) -> DriverProfile:
    return DriverProfile(
        temperature_gen=SinusoidalSeasonalTemp(base=0.30, amplitude=0.10),
        humidity_gen=OUHumidity(mean=0.35, theta=0.05, sigma=0.04),
        load_gen=MonotonicDutyLoad(base=0.55),
        maintenance_gen=StepMaintenance(schedule=[{"tick": 0, "value": 0.7}]),
        base_environment=Environment(
            base_ambient_C=22.0,
            amplitude_C=8.0,
            weekly_runtime_hours=60.0,
            vibration_level=0.10,
            cumulative_cleanings=0,
            hours_since_maintenance=0.0,
            start_stop_cycles=0,
        ),
        chaos=ChaosOverlay(enabled=chaos_enabled, horizon_ticks=horizon),
        seed=seed,
    )


def test_drivers_in_unit_interval_over_horizon() -> None:
    profile = _profile(chaos_enabled=False)
    for tick in range(0, 260):
        drivers, _ = profile.sample(tick)
        assert 0.0 <= drivers.temperature_stress <= 1.0
        assert 0.0 <= drivers.humidity_contamination <= 1.0
        assert 0.0 <= drivers.operational_load <= 1.0
        assert 0.0 <= drivers.maintenance_level <= 1.0


def test_same_seed_same_driver_stream() -> None:
    a = _profile(chaos_enabled=True, seed=42)
    b = _profile(chaos_enabled=True, seed=42)
    a_stream = [a.sample(t)[0] for t in range(50)]
    b_stream = [b.sample(t)[0] for t in range(50)]
    assert a_stream == b_stream


def test_chaos_temp_spikes_only_increase_temperature() -> None:
    """Chaos overlay can raise temperature_stress but not lower it.

    Compare ticks WITH chaos to the same generator output WITHOUT chaos
    over the run; the chaos stream should never have a lower value than
    the no-chaos baseline at any tick.
    """
    no_chaos = _profile(chaos_enabled=False)
    yes_chaos = _profile(chaos_enabled=True)
    any_higher = False
    for tick in range(260):
        a, _ = no_chaos.sample(tick)
        b, _ = yes_chaos.sample(tick)
        if b.temperature_stress > a.temperature_stress + 1e-9:
            any_higher = True
        # Chaos never reduces temp below baseline (we only add positive spikes).
        assert b.temperature_stress >= a.temperature_stress - 1e-9
    assert any_higher, "chaos should fire at least once over a 5-year horizon"
