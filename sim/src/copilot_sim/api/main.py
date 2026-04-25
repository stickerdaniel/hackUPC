"""FastAPI app entry point for the copilot-sim service."""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, HTTPException, status

from copilot_sim import __version__

from .auth import require_bearer
from .runner import run_scenario_sync
from .schemas import HealthResponse, RunRequest, RunResponse

log = logging.getLogger("copilot_sim.api")

app = FastAPI(
    title="copilot-sim",
    version=__version__,
    description="HTTP API for the HP Metal Jet S100 digital twin.",
)


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(ok=True, version=__version__)


@app.post(
    "/runs",
    response_model=RunResponse,
    dependencies=[Depends(require_bearer)],
)
def post_run(req: RunRequest) -> RunResponse:
    log.info("POST /runs run_id=%s scenario=%s", req.run_id, req.scenario)
    try:
        return run_scenario_sync(req)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
