"""`copilot-sim` command-line entry point.

Three subcommands:

- `run <scenario.yaml>` — load the scenario, build the engine + driver
  profile + heuristic policy, run the loop, write to the historian,
  and print the resulting `run_id`.
- `list-scenarios` — print each YAML found under `sim/scenarios/`.
- `inspect <run_id>` — print final state, status transitions, and the
  print-outcome distribution. `--failure-analysis` lands in A19.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from .historian import reader
from .historian.connection import open_db
from .historian.run_id import mint_run_id
from .historian.writer import HistorianWriter, list_run_ids
from .policy.heuristic import HeuristicPolicy
from .simulation.bootstrap import bootstrap_engine
from .simulation.loop import SimulationLoop
from .simulation.scenarios import build_driver_profile, load_scenario


def _scenarios_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "scenarios"


def _cmd_list_scenarios(_args: argparse.Namespace) -> int:
    scenarios = sorted(_scenarios_dir().glob("*.yaml"))
    if not scenarios:
        print("No scenarios found in", _scenarios_dir())
        return 1
    for path in scenarios:
        print(path.name)
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    scenario_path = Path(args.scenario)
    if not scenario_path.exists():
        # Support bare filenames relative to sim/scenarios/.
        candidate = _scenarios_dir() / scenario_path.name
        if candidate.exists():
            scenario_path = candidate
        else:
            print(f"scenario file not found: {args.scenario}", file=sys.stderr)
            return 2

    config = load_scenario(scenario_path)
    profile = build_driver_profile(config)
    engine, state = bootstrap_engine(config)

    db_path = Path(args.db_path or config.historian.path)
    conn = open_db(db_path)
    run_id = mint_run_id(config.run.scenario, config.run.profile, config.run.seed)
    writer = HistorianWriter(conn, run_id, flush_every=args.flush_every)
    writer.write_run(
        scenario=config.run.scenario,
        profile=config.run.profile,
        dt_seconds=config.run.dt_seconds,
        seed=config.run.seed,
        horizon_ticks=config.run.horizon_ticks,
        notes=args.notes or "",
    )

    policy = HeuristicPolicy() if config.policy.kind == "heuristic" else None
    loop = SimulationLoop(
        engine=engine,
        profile=profile,
        policy=policy,
        writer=writer,
        horizon_ticks=config.run.horizon_ticks,
        dt_seconds=config.run.dt_seconds,
    )
    loop.run(state)
    # Read the summary back from the historian rather than the in-memory
    # post-maintenance state. The historian's last tick row is the
    # pre-maintenance state, which is what `inspect` and the dashboard
    # both show — one source of truth across CLI surfaces.
    final_rows = reader.fetch_final_component_states(conn, run_id)
    outcomes = reader.fetch_print_outcome_distribution(conn, run_id)
    event_count = reader.fetch_event_count(conn, run_id)
    env_event_count = reader.fetch_environmental_event_count(conn, run_id)
    final_tick = final_rows[0]["tick"] if final_rows else config.run.horizon_ticks
    conn.close()

    print(f"run_id: {run_id}")
    print(f"final tick: {final_tick}")
    print(
        "print outcomes: "
        f"OK={outcomes.get('OK', 0)} "
        f"QUALITY_DEGRADED={outcomes.get('QUALITY_DEGRADED', 0)} "
        f"HALTED={outcomes.get('HALTED', 0)}"
    )
    print(f"events: {event_count}")
    if env_event_count:
        print(f"environmental events: {env_event_count}")
    return 0


def _print_failure_analysis(conn: sqlite3.Connection, run_id: str) -> None:
    """Per-component first DEGRADED / CRITICAL / FAILED tick + the top
    three coupling factors at each transition.

    Reads everything from the historian — no engine re-run, no
    fabrication. The caller has already printed the run header.
    """
    from .components.registry import COMPONENT_IDS

    rows = reader.fetch_status_transitions(conn, run_id)
    by_component: dict[str, dict[str, int]] = {cid: {} for cid in COMPONENT_IDS}
    for row in rows:
        cid = row["component_id"]
        if cid not in by_component:
            by_component[cid] = {}
        by_component[cid].setdefault(row["status"], int(row["first_tick"]))

    print("failure analysis (per-component first transitions):")
    for cid in COMPONENT_IDS:
        transitions = by_component.get(cid, {})
        first_degraded = transitions.get("DEGRADED")
        first_critical = transitions.get("CRITICAL")
        first_failed = transitions.get("FAILED")
        line = (
            f"  {cid:<10}  "
            f"DEGRADED={_fmt_tick(first_degraded)}  "
            f"CRITICAL={_fmt_tick(first_critical)}  "
            f"FAILED={_fmt_tick(first_failed)}"
        )
        print(line)
        for label, tick_value in (
            ("at-DEGRADED", first_degraded),
            ("at-CRITICAL", first_critical),
            ("at-FAILED", first_failed),
        ):
            if tick_value is None:
                continue
            factors = reader.fetch_coupling_factors_at(conn, run_id, tick_value)
            top = sorted(factors.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]
            if top:
                top_str = ", ".join(f"{k}={v:.3f}" for k, v in top)
                print(f"      {label} (tick {tick_value}): {top_str}")


def _fmt_tick(t: int | None) -> str:
    return "never" if t is None else f"t={t}"


def _cmd_inspect(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path or "data/historian.sqlite")
    if not db_path.exists():
        print(f"historian DB not found: {db_path}", file=sys.stderr)
        return 2
    conn: sqlite3.Connection = open_db(db_path)
    try:
        if args.run_id is None:
            ids = list(list_run_ids(conn))
            if not ids:
                print("no runs in historian")
                return 1
            run_id = ids[0]
        else:
            run_id = args.run_id

        run = reader.fetch_run(conn, run_id)
        if run is None:
            print(f"run_id not found: {run_id}", file=sys.stderr)
            return 2
        print(f"run_id: {run['run_id']}")
        print(f"scenario: {run['scenario']} (profile {run['profile']})")
        print(f"seed: {run['seed']}, horizon_ticks: {run['horizon_ticks']}")
        print()
        print("final component states:")
        for row in reader.fetch_final_component_states(conn, run_id):
            print(
                f"  {row['component_id']:<10}  "
                f"health={row['health_index']:.3f}  "
                f"status={row['status']:<10}  "
                f"age_ticks={row['age_ticks']}"
            )
        print()
        outcomes = reader.fetch_print_outcome_distribution(conn, run_id)
        print("print outcome distribution:")
        for kind, count in sorted(outcomes.items()):
            print(f"  {kind:<18}  {count}")
        print()
        print(f"events: {reader.fetch_event_count(conn, run_id)}")
        env_event_count = reader.fetch_environmental_event_count(conn, run_id)
        if env_event_count:
            print(f"environmental events: {env_event_count}")
        if args.failure_analysis:
            print()
            _print_failure_analysis(conn, run_id)
        return 0
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="copilot-sim",
        description="HP Metal Jet S100 digital twin — simulation engine.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run a scenario end-to-end into the historian")
    p_run.add_argument("scenario", help="path to a scenario YAML or just its filename")
    p_run.add_argument("--db-path", help="override the historian DB path")
    p_run.add_argument("--flush-every", type=int, default=50)
    p_run.add_argument("--notes", default="")
    p_run.set_defaults(func=_cmd_run)

    p_list = sub.add_parser("list-scenarios", help="list scenarios under sim/scenarios/")
    p_list.set_defaults(func=_cmd_list_scenarios)

    p_inspect = sub.add_parser("inspect", help="print summary for a run_id")
    p_inspect.add_argument("run_id", nargs="?", help="run id (default: most recent)")
    p_inspect.add_argument("--db-path", help="override the historian DB path")
    p_inspect.add_argument(
        "--failure-analysis",
        action="store_true",
        help="add per-component first transition tick + top coupling factors",
    )
    p_inspect.set_defaults(func=_cmd_inspect)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
