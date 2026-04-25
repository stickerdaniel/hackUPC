"""Pydantic request/response schemas for the sim API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    ok: bool
    version: str


class RunRequest(BaseModel):
    """Body of POST /runs.

    `run_id` is required and Convex-issued; Python never mints IDs in the
    HTTP path. `scenario` is a YAML filename under `sim/scenarios/` (e.g.
    "barcelona-baseline.yaml" or just "barcelona-baseline").
    """

    run_id: str = Field(min_length=1, max_length=128)
    scenario: str = Field(min_length=1)
    user_id: str | None = None
    seed: int | None = None
    horizon_ticks: int | None = Field(default=None, ge=1, le=10_000)
    dt_seconds: int | None = Field(default=None, ge=1)


class RunResponse(BaseModel):
    run_id: str
    status: Literal["completed"]
    tick_count: int
    elapsed_ms: int
