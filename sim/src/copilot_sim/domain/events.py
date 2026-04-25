"""Operator-side events: maintenance actions injected into the engine, and the
events the historian persists for the operator-loop story (notice → diagnose
→ fix → resume) from `TRACK-CONTEXT.md §3.4`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .enums import OperatorEventKind


@dataclass(frozen=True, slots=True)
class MaintenanceAction:
    """A maintenance directive consumed by `Engine.apply_maintenance`."""

    component_id: str
    kind: OperatorEventKind  # TROUBLESHOOT (no state change), FIX (partial), REPLACE (full)
    payload: Mapping[str, float]  # action-specific knobs, e.g. {"recovery_fraction": 0.5}

    @staticmethod
    def freeze_payload(payload: Mapping[str, float]) -> Mapping[str, float]:
        return MappingProxyType(dict(payload))


@dataclass(frozen=True, slots=True)
class OperatorEvent:
    """One row written to the historian's `events` table."""

    tick: int
    sim_time_s: float
    kind: OperatorEventKind
    component_id: str | None  # None ⇒ global event (e.g. printer-wide reset)
    payload: Mapping[str, float | str]

    @staticmethod
    def freeze_payload(payload: Mapping[str, float | str]) -> Mapping[str, float | str]:
        return MappingProxyType(dict(payload))
