from __future__ import annotations

import argparse
from pathlib import Path

from .world_creator import WorldCatalog, WorldConfig


def main() -> None:
    parser = argparse.ArgumentParser(prog="worldos-create")
    parser.add_argument("--data-dir", default="./data", help="Directory containing WorldOS world databases")
    parser.add_argument("--name", required=True)
    parser.add_argument(
        "--type",
        dest="world_type",
        choices=("agrarian_town", "modern_community", "island_survival", "mars_colony", "custom"),
        default="agrarian_town",
    )
    parser.add_argument("--era", choices=("primitive", "agrarian", "industrial", "modern", "future"), default="agrarian")
    parser.add_argument("--population", type=int, default=12)
    parser.add_argument("--locations", dest="location_count", type=int, default=3)
    parser.add_argument("--resources", dest="resource_abundance", type=int, default=55)
    parser.add_argument("--stability", dest="social_stability", type=int, default=60)
    parser.add_argument("--conflict", dest="conflicts", action="append", default=[])
    parser.add_argument("--seed", default="worldos")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    catalog = WorldCatalog(data_dir, legacy_db_path=data_dir / "world.db")
    config = WorldConfig(
        name=args.name,
        world_type=args.world_type,
        era=args.era,
        population=args.population,
        location_count=args.location_count,
        resource_abundance=args.resource_abundance,
        social_stability=args.social_stability,
        conflicts=args.conflicts,
        seed=args.seed,
    )
    world = catalog.create(config)
    print(world.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
