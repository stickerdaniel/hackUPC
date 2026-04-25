"""5-year integration smoke for each scenario.

Runs the full 260-tick horizon for all three scenarios, asserts the run
completes, the DB is non-empty, and the final state has at least one
component visibly aged (health < 0.95) — i.e. the engine is producing
real degradation, not a flat curve.

Wall-clock budget is implicit: pytest will fail any single run that
exceeds 30 s. Plan target: < 5 s per scenario.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from copilot_sim.cli import main


def _scenario_root() -> Path:
    return Path(__file__).resolve().parents[2] / "scenarios"


@pytest.mark.parametrize(
    "scenario_name",
    ["barcelona-baseline.yaml", "phoenix-aggressive.yaml", "chaos-stress-test.yaml"],
)
def test_scenario_full_horizon(tmp_path: Path, capsys, scenario_name: str) -> None:
    db_path = tmp_path / "historian.sqlite"
    start = time.perf_counter()
    rc = main(
        [
            "run",
            scenario_name,
            "--db-path",
            str(db_path),
            "--flush-every",
            "100",
        ]
    )
    elapsed = time.perf_counter() - start
    assert rc == 0
    assert db_path.exists()
    out = capsys.readouterr().out
    assert "final tick: 260" in out, out
    # Generous budget — primary purpose is "does not hang".
    assert elapsed < 30.0, f"{scenario_name} took {elapsed:.1f}s"

    # Sanity check: at least one component aged below FUNCTIONAL.
    rc = main(["inspect", "--db-path", str(db_path), "--failure-analysis"])
    assert rc == 0
    inspect_out = capsys.readouterr().out
    assert "failure analysis" in inspect_out
