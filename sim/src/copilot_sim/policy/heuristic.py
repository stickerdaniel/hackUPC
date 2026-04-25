"""Heuristic maintenance policy.

Reads `ObservedPrinterState` only — never the true state — so the §3.4
sensor-fault discipline holds (the policy can be fooled by a drifted
sensor exactly as a real operator would). Decision rules in priority
order, lifted from the plan + doc 09:

1. Any `observed_status is UNKNOWN` → `TROUBLESHOOT(component)`. The
   policy never acts blind on a missing sensor reading.
2. `observed_health_index < 0.20` → `REPLACE(component)`.
3. `observed_health_index < 0.45` → `FIX(component)`.
4. Monthly preventive `FIX` of the longest-unmaintained component when
   nothing else is firing.

`decide` returns at most one action per tick — the list shape leaves
room for a future LLM-as-policy that can issue concurrent actions
without changing the engine contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..components.registry import COMPONENT_IDS
from ..domain.enums import OperationalStatus, OperatorEventKind
from ..domain.events import MaintenanceAction
from ..domain.state import ObservedPrinterState

_UNHEALTHY_REPLACE = 0.20
_UNHEALTHY_FIX = 0.45
_PREVENTIVE_TICK_GAP = 4  # one simulated month at dt = 1 week


@dataclass(slots=True)
class HeuristicPolicy:
    last_action_tick: dict[str, int] = field(default_factory=dict)

    def decide(
        self,
        observed: ObservedPrinterState,
        tick: int,
    ) -> list[MaintenanceAction]:
        # Rule 1 — TROUBLESHOOT on any UNKNOWN observed_status.
        for cid in COMPONENT_IDS:
            oc = observed.components.get(cid)
            if oc is None:
                continue
            if oc.observed_status is OperationalStatus.UNKNOWN:
                return [self._action(cid, OperatorEventKind.TROUBLESHOOT)]

        # Rule 2 + 3 — REPLACE / FIX on low observed health.
        for cid in COMPONENT_IDS:
            oc = observed.components.get(cid)
            if oc is None:
                continue
            health = oc.observed_health_index
            if health is None:
                continue
            if health < _UNHEALTHY_REPLACE:
                return [self._action(cid, OperatorEventKind.REPLACE, tick=tick)]
            if health < _UNHEALTHY_FIX:
                return [self._action(cid, OperatorEventKind.FIX, tick=tick)]

        # Rule 4 — monthly preventive FIX of the longest-unmaintained.
        oldest = self._oldest_component(tick)
        if (
            oldest is not None
            and (tick - self.last_action_tick.get(oldest, 0)) >= _PREVENTIVE_TICK_GAP
        ):
            return [self._action(oldest, OperatorEventKind.FIX, tick=tick)]

        return []

    # --- internals ------------------------------------------------------
    def _action(
        self,
        component_id: str,
        kind: OperatorEventKind,
        tick: int | None = None,
    ) -> MaintenanceAction:
        if tick is not None:
            self.last_action_tick[component_id] = tick
        return MaintenanceAction(
            component_id=component_id,
            kind=kind,
            payload=MaintenanceAction.freeze_payload({}),
        )

    def _oldest_component(self, tick: int) -> str | None:
        if not self.last_action_tick:
            return COMPONENT_IDS[0]
        # All components without a record are tied at tick 0.
        gaps = {cid: tick - self.last_action_tick.get(cid, 0) for cid in COMPONENT_IDS}
        return max(gaps, key=lambda c: gaps[c])
