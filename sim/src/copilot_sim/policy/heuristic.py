"""Heuristic maintenance policy.

Reads `ObservedPrinterState` only — never the true state — so the §3.4
sensor-fault discipline holds (the policy can be fooled by a drifted
sensor exactly as a real operator would). Decision rules in priority
order, lifted from the plan + doc 09:

1. Any `observed_status is UNKNOWN` → `TROUBLESHOOT(component)`. The
   policy never acts blind on a missing sensor reading.
2. Among components with `observed_health_index < 0.45`, pick the
   **lowest-health** one and emit `REPLACE` (if `< 0.20`) or `FIX`
   (otherwise). Ties broken by `COMPONENT_IDS` order so the policy
   stays deterministic.
3. Monthly preventive `FIX` of the longest-unmaintained component when
   nothing else is firing.

The "worst-first" tie-break in rule 2 fixes a fairness issue the
fixed-iteration earlier draft had: nozzle (which decays fastest)
would always win the FIX queue even when rail or heater were
materially worse, because the fixed walk picked the first match.
Sorting by health makes the policy's event log a fair triage signal.

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

        # Rule 2 — REPLACE / FIX on lowest observed health. Worst-first
        # triage with deterministic tie-break by registry order.
        candidates: list[tuple[float, int, str]] = []
        for index, cid in enumerate(COMPONENT_IDS):
            oc = observed.components.get(cid)
            if oc is None:
                continue
            health = oc.observed_health_index
            if health is None:
                continue
            if health < _UNHEALTHY_FIX:
                candidates.append((float(health), index, cid))
        if candidates:
            candidates.sort()  # (health asc, registry_index asc, cid asc)
            health, _, cid = candidates[0]
            kind = (
                OperatorEventKind.REPLACE if health < _UNHEALTHY_REPLACE else OperatorEventKind.FIX
            )
            return [self._action(cid, kind, tick=tick)]

        # Rule 3 — monthly preventive FIX of the longest-unmaintained.
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
