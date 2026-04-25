"""Smoke test: SimulationLoop runs a short horizon end-to-end."""

from __future__ import annotations

from pathlib import Path

from copilot_sim.historian.connection import open_db
from copilot_sim.historian.run_id import mint_run_id
from copilot_sim.historian.writer import HistorianWriter
from copilot_sim.policy.heuristic import HeuristicPolicy
from copilot_sim.simulation.bootstrap import bootstrap_engine
from copilot_sim.simulation.loop import SimulationLoop
from copilot_sim.simulation.scenarios import build_driver_profile, load_scenario


def _scenario_root() -> Path:
    return Path(__file__).resolve().parents[2] / "scenarios"


def test_load_three_scenarios() -> None:
    for name in ("barcelona-baseline", "phoenix-aggressive", "chaos-stress-test"):
        cfg = load_scenario(_scenario_root() / f"{name}.yaml")
        assert cfg.run.horizon_ticks > 0


def test_loop_runs_short_horizon(tmp_path: Path) -> None:
    cfg = load_scenario(_scenario_root() / "barcelona-baseline.yaml")
    # Cap horizon for the smoke run.
    cfg = cfg.model_copy(update={"run": cfg.run.model_copy(update={"horizon_ticks": 20})})

    profile = build_driver_profile(cfg)
    engine, state = bootstrap_engine(cfg)
    db_path = tmp_path / "historian.sqlite"
    conn = open_db(db_path)
    run_id = mint_run_id(cfg.run.scenario, cfg.run.profile, cfg.run.seed)
    writer = HistorianWriter(conn, run_id, flush_every=10)
    writer.write_run(
        scenario=cfg.run.scenario,
        profile=cfg.run.profile,
        dt_seconds=cfg.run.dt_seconds,
        seed=cfg.run.seed,
        horizon_ticks=cfg.run.horizon_ticks,
    )

    loop = SimulationLoop(
        engine=engine,
        profile=profile,
        policy=HeuristicPolicy(),
        writer=writer,
        horizon_ticks=cfg.run.horizon_ticks,
        dt_seconds=cfg.run.dt_seconds,
    )
    final_state = loop.run(state)
    conn.close()

    assert final_state.tick == 20
    assert db_path.exists()
