"""Bearer-token auth dependency for the sim API."""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException, status


def require_bearer(authorization: str | None = Header(default=None)) -> None:
    expected = os.environ.get("SIM_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SIM_API_KEY not configured",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    presented = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        )
