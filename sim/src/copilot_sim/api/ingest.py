"""HTTP client that mirrors persisted ticks to the Convex `/sim-ingest` endpoint.

Buffer ticks and POST them in batches (default 25) to amortize round-trips.
Each batch carries a monotonic `batchSeq` starting at 0. The Convex side dedupes
on retries (`batchSeq === lastIngestedBatchSeq` → no-op) and rejects gaps (any
other delta → ConvexError) so we can never silently lose an earlier batch.

On non-2xx: retry once with backoff. If that still fails, raise so the runner
fails the run loudly rather than accept a partial historian on the Convex side.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict
from typing import Any

import httpx

from ..components.registry import COMPONENT_IDS
from ..simulation.loop import TickPayload

log = logging.getLogger("copilot_sim.api.ingest")


def _component_true_to_dict(state) -> dict[str, Any]:
    return {
        "componentId": state.component_id,
        "healthIndex": float(state.health_index),
        "status": state.status.value if hasattr(state.status, "value") else str(state.status),
        "ageTicks": int(state.age_ticks),
        "metrics": {k: float(v) for k, v in dict(state.metrics).items()},
    }


def _component_observed_to_dict(obs) -> dict[str, Any]:
    status = obs.observed_status
    return {
        "componentId": obs.component_id,
        "observedHealthIndex": (
            None if obs.observed_health_index is None else float(obs.observed_health_index)
        ),
        "observedStatus": (
            None if status is None else (status.value if hasattr(status, "value") else str(status))
        ),
        "sensorNote": obs.sensor_note,
        "observedMetrics": {
            k: (None if v is None else float(v)) for k, v in dict(obs.observed_metrics).items()
        },
        "sensorHealth": {
            k: (None if v is None else float(v)) for k, v in dict(obs.sensor_health).items()
        },
    }


def _drivers_to_dict(d) -> dict[str, float]:
    raw = asdict(d)
    return {
        "temperatureStress": float(raw["temperature_stress"]),
        "humidityContamination": float(raw["humidity_contamination"]),
        "operationalLoad": float(raw["operational_load"]),
        "maintenanceLevel": float(raw["maintenance_level"]),
    }


def _env_to_dict(e) -> dict[str, float | int]:
    raw = asdict(e)
    return {
        "baseAmbientC": float(raw["base_ambient_C"]),
        "amplitudeC": float(raw["amplitude_C"]),
        "weeklyRuntimeHours": float(raw["weekly_runtime_hours"]),
        "vibrationLevel": float(raw["vibration_level"]),
        "cumulativeCleanings": int(raw["cumulative_cleanings"]),
        "hoursSinceMaintenance": float(raw["hours_since_maintenance"]),
        "startStopCycles": int(raw["start_stop_cycles"]),
    }


def _payload_to_dict(p: TickPayload) -> dict[str, Any]:
    components_true = [
        _component_true_to_dict(p.true_state.components[cid])
        for cid in COMPONENT_IDS
        if cid in p.true_state.components
    ]
    components_observed = [
        _component_observed_to_dict(p.observed.components[cid])
        for cid in COMPONENT_IDS
        if cid in p.observed.components
    ]
    env_events = [
        {
            "name": ev.name,
            "payload": {
                "duration": int(ev.duration),
                "outputTick": int(ev.output_tick),
                "disableHumanMaintenance": bool(ev.disable_human_maintenance),
            },
        }
        for ev in p.env_events
    ]
    operator_events = [
        {
            "kind": ev.kind.value if hasattr(ev.kind, "value") else str(ev.kind),
            "componentId": ev.component_id,
            "payload": {
                k: (float(v) if isinstance(v, int | float) else str(v))
                for k, v in dict(ev.payload).items()
            },
        }
        for ev in p.operator_events
    ]
    print_outcome = (
        p.true_state.print_outcome.value
        if hasattr(p.true_state.print_outcome, "value")
        else str(p.true_state.print_outcome)
    )
    return {
        "tick": int(p.tick),
        "simTimeS": float(p.sim_time_s),
        "tsIso": p.ts_iso,
        "drivers": _drivers_to_dict(p.drivers),
        "env": _env_to_dict(p.env),
        "couplingFactors": {k: float(v) for k, v in dict(p.coupling.factors).items()},
        "printOutcome": print_outcome,
        "componentsTrue": components_true,
        "componentsObserved": components_observed,
        "envEvents": env_events,
        "operatorEvents": operator_events,
    }


class IngestClient:
    def __init__(
        self,
        base_url: str,
        secret: str,
        run_id: str,
        *,
        batch_size: int = 25,
        timeout_s: float = 30.0,
    ) -> None:
        if not base_url:
            raise ValueError("ingest base_url is empty")
        if not secret:
            raise ValueError("ingest secret is empty")
        self.base_url = base_url.rstrip("/")
        self.secret = secret
        self.run_id = run_id
        self.batch_size = max(1, int(batch_size))
        self.timeout_s = float(timeout_s)
        self._batch_seq = 0
        self._buffer: list[dict[str, Any]] = []
        self._client = httpx.Client(timeout=self.timeout_s)

    def buffer_tick(self, payload: TickPayload) -> None:
        self._buffer.append(_payload_to_dict(payload))
        if len(self._buffer) >= self.batch_size:
            self.flush()

    def flush(self, force: bool = True) -> None:
        if not self._buffer:
            return
        if not force and len(self._buffer) < self.batch_size:
            return
        batch = self._buffer
        self._buffer = []
        body = {"runId": self.run_id, "batchSeq": self._batch_seq, "ticks": batch}
        self._post_with_retry(body)
        self._batch_seq += 1

    def close(self) -> None:
        try:
            self.flush(force=True)
        finally:
            self._client.close()

    def _post_with_retry(self, body: dict[str, Any]) -> None:
        attempts = 0
        last_err: Exception | None = None
        while attempts < 2:
            attempts += 1
            try:
                resp = self._client.post(
                    f"{self.base_url}",
                    headers={"x-sim-ingest-secret": self.secret},
                    json=body,
                )
                if 200 <= resp.status_code < 300:
                    return
                last_err = RuntimeError(
                    f"ingest non-2xx (attempt {attempts}): {resp.status_code} {resp.text[:300]}"
                )
                log.warning(str(last_err))
                if 400 <= resp.status_code < 500 and resp.status_code != 408:
                    # 4xx (other than timeout) is a contract bug; no retry helps.
                    break
            except (httpx.HTTPError, OSError) as err:
                last_err = err
                log.warning("ingest network error (attempt %d): %s", attempts, err)
            time.sleep(0.5 * attempts)
        raise RuntimeError(f"ingest failed after {attempts} attempts: {last_err}")
