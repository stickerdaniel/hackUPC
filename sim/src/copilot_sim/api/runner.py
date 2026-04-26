"""Synchronous run dispatcher used by POST /runs.

This is the API-side mirror of `cli._cmd_run`: it loads a scenario YAML,
applies optional overrides from the request, runs the existing
`SimulationLoop` to completion, and returns the result. It deliberately
reuses everything from the CLI path so behaviour stays identical between
`copilot-sim run` and the HTTP service.

Convex owns `run_id`. Unlike the CLI, the runner does NOT call
`mint_run_id`; the caller-supplied ID flows straight into
`HistorianWriter`.
"""

from __future__ import annotations

import contextlib
import logging
import os
import time
from pathlib import Path

from ..historian.connection import open_db
from ..historian.writer import HistorianWriter
from ..policy.heuristic import HeuristicPolicy
from ..simulation.bootstrap import bootstrap_engine
from ..simulation.loop import SimulationLoop
from ..simulation.scenarios import build_driver_profile, load_scenario
from .ingest import IngestClient
from .schemas import RunRequest, RunResponse

log = logging.getLogger("copilot_sim.api.runner")


def _scenarios_dir() -> Path:
    # `cli.py` does `parents[2]` from `src/copilot_sim/cli.py`, which lands
    # at `sim/scenarios/`. Same target from `src/copilot_sim/api/runner.py`
    # is `parents[3]` because we're one directory deeper.
    return Path(__file__).resolve().parents[3] / "scenarios"


def _resolve_scenario(name: str) -> Path:
    candidate = Path(name)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    base = _scenarios_dir()
    for fname in (name, f"{name}.yaml" if not name.endswith(".yaml") else name):
        path = base / fname
        if path.exists():
            return path
    raise FileNotFoundError(f"scenario not found: {name} (looked in {base})")


def run_scenario_sync(req: RunRequest) -> RunResponse:
    """Build the engine + loop from `req`, run it to completion."""
    scenario_path = _resolve_scenario(req.scenario)
    config = load_scenario(scenario_path)

    # Apply request overrides on top of the YAML's run section.
    run_overrides: dict[str, object] = {}
    if req.seed is not None:
        run_overrides["seed"] = int(req.seed)
    if req.horizon_ticks is not None:
        run_overrides["horizon_ticks"] = int(req.horizon_ticks)
    if req.dt_seconds is not None:
        run_overrides["dt_seconds"] = int(req.dt_seconds)
    if run_overrides:
        config = config.model_copy(update={"run": config.run.model_copy(update=run_overrides)})

    # Capture the resolved (post-override) config so the API response can
    # echo it back to Convex. Pydantic mode="json" produces a fully
    # JSON-serialisable dict including every nested driver kind+params.
    resolved_config = config.model_dump(mode="json")

    profile = build_driver_profile(config)
    engine, state = bootstrap_engine(config)

    # Historian path: env override (mounted volume in Docker) wins over the
    # scenario YAML default so containers write to /data, not the image layer.
    db_path = Path(os.environ.get("HISTORIAN_PATH") or config.historian.path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = open_db(db_path)

    ingest_url = os.environ.get("CONVEX_INGEST_URL")
    ingest_secret = os.environ.get("SIM_INGEST_SECRET")
    ingest_client: IngestClient | None = None
    if ingest_url and ingest_secret:
        ingest_client = IngestClient(base_url=ingest_url, secret=ingest_secret, run_id=req.run_id)
    else:
        log.warning(
            "Convex ingest disabled (CONVEX_INGEST_URL and SIM_INGEST_SECRET not set); "
            "run will only land in SQLite"
        )

    try:
        writer = HistorianWriter(conn, req.run_id, flush_every=50)
        writer.write_run(
            scenario=config.run.scenario,
            profile=config.run.profile,
            dt_seconds=config.run.dt_seconds,
            seed=config.run.seed,
            horizon_ticks=config.run.horizon_ticks,
            notes=f"api user_id={req.user_id or ''}",
        )

        policy = HeuristicPolicy() if config.policy.kind == "heuristic" else None
        loop = SimulationLoop(
            engine=engine,
            profile=profile,
            policy=policy,
            writer=writer,
            horizon_ticks=config.run.horizon_ticks,
            dt_seconds=config.run.dt_seconds,
            on_tick_persisted=(ingest_client.buffer_tick if ingest_client else None),
        )

        t0 = time.monotonic()
        loop.run(state)
        if ingest_client is not None:
            ingest_client.close()
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        return RunResponse(
            run_id=req.run_id,
            status="completed",
            tick_count=config.run.horizon_ticks,
            elapsed_ms=elapsed_ms,
            resolved_config=resolved_config,
        )
    finally:
        if ingest_client is not None:
            with contextlib.suppress(Exception):
                ingest_client.close()
        conn.close()


__all__ = ["run_scenario_sync"]
