from __future__ import annotations

import argparse
import json
from typing import Any

from .living_world import initialize_first_living_world, run_first_living_world


def _default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def main() -> None:
    parser = argparse.ArgumentParser(prog="worldos-living")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create the First Living World")
    init_parser.add_argument("--db", required=True)

    run_parser = subparsers.add_parser(
        "run", help="run, restart, branch, and inspect the First Living World"
    )
    run_parser.add_argument("--db", required=True)
    run_parser.add_argument("--ticks", type=int, default=10_000)
    run_parser.add_argument("--seed", default="first-living-world")
    run_parser.add_argument("--restart-at", type=int)
    run_parser.add_argument("--branch", default="living-world-alternate")

    args = parser.parse_args()
    if args.command == "init":
        initialize_first_living_world(args.db)
        result: Any = {"database_path": args.db, "initialized": True}
    else:
        result = run_first_living_world(
            args.db,
            ticks=args.ticks,
            world_seed=args.seed,
            restart_at=args.restart_at,
            branch_timeline_id=args.branch,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=_default))


if __name__ == "__main__":
    main()
