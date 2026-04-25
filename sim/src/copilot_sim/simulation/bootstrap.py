"""Helpers to bootstrap engine + initial state from a scenario config."""

from __future__ import annotations

from ..domain.state import PrinterState
from ..engine.engine import Engine, initial_state
from .scenarios import ScenarioConfig


def bootstrap_engine(config: ScenarioConfig) -> tuple[Engine, PrinterState]:
    return Engine(scenario_seed=config.run.seed), initial_state()
