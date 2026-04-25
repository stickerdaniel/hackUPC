"""Smoke test for the copilot-sim CLI."""

from __future__ import annotations

from pathlib import Path

from copilot_sim.cli import main


def _scenario_root() -> Path:
    return Path(__file__).resolve().parents[2] / "scenarios"


def test_list_scenarios(capsys) -> None:
    rc = main(["list-scenarios"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "barcelona-baseline.yaml" in out
    assert "phoenix-aggressive.yaml" in out
    assert "chaos-stress-test.yaml" in out


def test_run_then_inspect(capsys, tmp_path: Path) -> None:
    """Cap the horizon by writing a derivative scenario YAML."""
    src = _scenario_root() / "barcelona-baseline.yaml"
    text = src.read_text()
    text = text.replace("horizon_ticks: 260", "horizon_ticks: 10")
    derived = tmp_path / "barcelona-tiny.yaml"
    derived.write_text(text)
    db_path = tmp_path / "historian.sqlite"

    rc = main(["run", str(derived), "--db-path", str(db_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "run_id:" in out
    assert "final tick: 10" in out

    rc = main(["inspect", "--db-path", str(db_path)])
    assert rc == 0
    inspect_out = capsys.readouterr().out
    assert "final component states:" in inspect_out
    assert "print outcome distribution:" in inspect_out
