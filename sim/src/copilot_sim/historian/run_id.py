"""Run-id minting. Format: `{scenario}-{profile}-{seed}-{utc_yyyymmddHHMMSS}`."""

from __future__ import annotations

from datetime import UTC, datetime


def mint_run_id(scenario: str, profile: str, seed: int) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"{scenario}-{profile}-{seed}-{stamp}"
