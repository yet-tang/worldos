from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import random
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .events import NewEvent
from .sqlite_store import SQLiteEventStore


WorldType = Literal["agrarian_town", "modern_community", "island_survival", "mars_colony", "custom"]
Era = Literal["primitive", "agrarian", "industrial", "modern", "future"]
ConflictType = Literal["resource_scarcity", "inequality", "external_threat", "disease", "power_struggle"]


class WorldConfig(BaseModel):
    """User-facing creation contract compiled into deterministic bootstrap events."""

    name: str = Field(min_length=1, max_length=80)
    world_type: WorldType = "agrarian_town"
    era: Era = "agrarian"
    population: int = Field(default=12, ge=1, le=200)
    location_count: int = Field(default=3, ge=1, le=20)
    resource_abundance: int = Field(default=55, ge=0, le=100)
    social_stability: int = Field(default=60, ge=0, le=100)
    conflicts: list[ConflictType] = Field(default_factory=list)
    seed: str = Field(default="worldos", min_length=1, max_length=120)

    @field_validator("name", "seed")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be blank")
        return cleaned

    @field_validator("conflicts")
    @classmethod
    def unique_conflicts(cls, value: list[ConflictType]) -> list[ConflictType]:
        return list(dict.fromkeys(value))


class WorldDescriptor(BaseModel):
    world_id: str
    name: str
    world_type: str
    era: str
    population: int
    location_count: int
    seed: str
    database_path: str
    created_at: str | None = None
    legacy: bool = False


@dataclass(frozen=True)
class WorldTemplate:
    location_names: tuple[str, ...]
    jobs: tuple[tuple[str, int], ...]
    default_era: Era
    starting_resource: str
    rumor: str


TEMPLATES: dict[str, WorldTemplate] = {
    "agrarian_town": WorldTemplate(
        location_names=("farm", "market", "homes", "temple", "workshop", "river", "east_gate", "granary"),
        jobs=(("food", 2), ("food", 1), ("wood", 2), ("cloth", 1), ("tools", 1), ("grain", 2)),
        default_era="agrarian",
        starting_resource="food",
        rumor="the old well may be running dry",
    ),
    "modern_community": WorldTemplate(
        location_names=("apartments", "office", "mall", "school", "clinic", "park", "station", "cafe"),
        jobs=(("credits", 2), ("food", 1), ("services", 2), ("goods", 1), ("knowledge", 1)),
        default_era="modern",
        starting_resource="food",
        rumor="a large employer may leave the district",
    ),
    "island_survival": WorldTemplate(
        location_names=("beach", "camp", "forest", "spring", "cliffs", "lagoon", "cave", "wreck"),
        jobs=(("food", 2), ("wood", 2), ("water", 2), ("tools", 1)),
        default_era="primitive",
        starting_resource="food",
        rumor="a storm may reach the island soon",
    ),
    "mars_colony": WorldTemplate(
        location_names=("habitat", "hydroponics", "reactor", "lab", "airlock", "mine", "medbay", "command"),
        jobs=(("food", 1), ("oxygen", 2), ("energy", 2), ("parts", 1), ("data", 1)),
        default_era="future",
        starting_resource="food",
        rumor="oxygen reserve telemetry may be inaccurate",
    ),
    "custom": WorldTemplate(
        location_names=("center", "north", "south", "east", "west", "commons", "workshop", "outpost"),
        jobs=(("food", 1), ("wood", 1), ("tools", 1), ("services", 1)),
        default_era="modern",
        starting_resource="food",
        rumor="something in the local balance is beginning to change",
    ),
}


def _stable_rng(seed: str) -> random.Random:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized[:32] or "world"


def make_world_id(config: WorldConfig) -> str:
    fingerprint = hashlib.sha256(
        json.dumps(config.model_dump(mode="json"), ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:8]
    return f"{_slug(config.name)}-{fingerprint}"


def compile_bootstrap_events(config: WorldConfig, *, world_id: str | None = None) -> list[NewEvent]:
    """Compile a WorldConfig into the canonical event-sourced bootstrap representation."""

    template = TEMPLATES[config.world_type]
    rng = _stable_rng(config.seed)
    world_id = world_id or make_world_id(config)

    location_names = list(template.location_names[: config.location_count])
    while len(location_names) < config.location_count:
        location_names.append(f"region-{len(location_names) + 1:02d}")

    events: list[NewEvent] = [
        NewEvent(
            tick=0,
            phase="bootstrap",
            event_type="world.created",
            payload={
                "flags": {
                    "world_id": world_id,
                    "world_name": config.name,
                    "world_type": config.world_type,
                    "era": config.era,
                    "scenario_version": 2,
                    "seed": config.seed,
                    "resource_abundance": config.resource_abundance,
                    "social_stability": config.social_stability,
                    "initial_conflicts": list(config.conflicts),
                    "locations": location_names,
                }
            },
        )
    ]

    for location_id in location_names:
        events.append(
            NewEvent(
                tick=0,
                phase="bootstrap",
                event_type="entity.created",
                subject_ids=(location_id,),
                payload={
                    "kind": "location",
                    "components": {
                        "name": location_id,
                        "identity": {"name": location_id},
                    },
                },
            )
        )

    base_inventory = 1 + round(config.resource_abundance / 20)
    base_wallet = 5 + round(config.resource_abundance / 5)
    stress = max(0, 100 - config.resource_abundance)
    instability = max(0, 100 - config.social_stability)

    actor_ids = [f"resident-{index:03d}" for index in range(1, config.population + 1)]
    components_by_actor: dict[str, dict[str, Any]] = {}
    for index, actor_id in enumerate(actor_ids):
        location_id = location_names[index % len(location_names)]
        resource, rate = template.jobs[index % len(template.jobs)]
        hunger = min(80, rng.randint(0, 12) + stress // 8)
        fatigue = min(70, rng.randint(0, 15) + instability // 12)
        inventory = {
            resource: max(1, base_inventory + rng.randint(0, 2)),
            template.starting_resource: max(1, base_inventory // 2 + 1),
        }
        components_by_actor[actor_id] = {
            "identity": {"name": f"Resident {index + 1}", "home": location_names[0]},
            "position": {"location_id": location_id},
            "health": {"current": 100, "maximum": 100},
            "needs": {"hunger": hunger, "fatigue": fatigue},
            "survival": {"hunger": hunger, "fatigue": fatigue},
            "metabolism": {"hunger_per_tick": 1, "fatigue_per_tick": 1},
            "inventory": inventory,
            "wallet": max(0, base_wallet + rng.randint(-3, 4)),
            "job": {"resource": resource, "rate": rate},
            "relationships": {},
            "rumors": [],
            "world_role": {"template": config.world_type, "era": config.era},
        }

    if actor_ids:
        components_by_actor[actor_ids[0]]["rumors"] = [template.rumor]

    # Seed a sparse social graph. High stability starts with more positive ties;
    # low stability creates weaker or negative ties without requiring a separate reducer.
    relationship_span = min(3, max(1, config.population - 1))
    for index, actor_id in enumerate(actor_ids):
        relationships: dict[str, int] = {}
        for offset in range(1, relationship_span + 1):
            if len(actor_ids) <= 1:
                break
            other = actor_ids[(index + offset) % len(actor_ids)]
            if other == actor_id:
                continue
            center = config.social_stability - 50
            relationships[other] = max(-50, min(50, center // 2 + rng.randint(-10, 10)))
        components_by_actor[actor_id]["relationships"] = relationships

    if "resource_scarcity" in config.conflicts and len(actor_ids) >= 2:
        seller, buyer = actor_ids[0], actor_ids[1]
        resource = template.starting_resource
        components_by_actor[seller]["trade_offer"] = {
            "buyer_id": buyer,
            "resource": resource,
            "quantity": 1,
            "price": max(1, 6 - config.resource_abundance // 25),
        }
    if ("inequality" in config.conflicts or "power_struggle" in config.conflicts) and len(actor_ids) >= 2:
        aggressor, target = actor_ids[0], actor_ids[-1]
        components_by_actor[aggressor]["conflict"] = {
            "target_id": target,
            "severity": max(10, 60 - config.social_stability // 2),
        }
    if "external_threat" in config.conflicts and actor_ids:
        components_by_actor[actor_ids[0]]["rumors"].append("an external threat has been reported near the boundary")
    if "disease" in config.conflicts and actor_ids:
        affected = actor_ids[: max(1, len(actor_ids) // 10)]
        for actor_id in affected:
            components_by_actor[actor_id]["health"] = {"current": 85, "maximum": 100}
            components_by_actor[actor_id]["condition"] = {"name": "initial_illness", "severity": 15}

    for actor_id in actor_ids:
        events.append(
            NewEvent(
                tick=0,
                phase="bootstrap",
                event_type="entity.created",
                subject_ids=(actor_id,),
                payload={"kind": "character", "components": components_by_actor[actor_id]},
            )
        )

    return events


class WorldCatalog:
    """Development-stage registry for multiple independent world databases."""

    def __init__(self, data_dir: str | Path, *, legacy_db_path: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.worlds_dir = self.data_dir / "worlds"
        self.catalog_path = self.worlds_dir / "catalog.json"
        self.legacy_db_path = Path(legacy_db_path) if legacy_db_path else self.data_dir / "world.db"

    def list_worlds(self) -> list[WorldDescriptor]:
        worlds = self._load_catalog()
        if self.legacy_db_path.exists() and not any(item.database_path == str(self.legacy_db_path) for item in worlds):
            worlds.insert(0, self._legacy_descriptor())
        return worlds

    def get(self, world_id: str) -> WorldDescriptor:
        for item in self.list_worlds():
            if item.world_id == world_id:
                return item
        raise KeyError(f"unknown world: {world_id}")

    def default_world(self) -> WorldDescriptor | None:
        worlds = self.list_worlds()
        return worlds[0] if worlds else None

    def create(self, config: WorldConfig) -> WorldDescriptor:
        self.worlds_dir.mkdir(parents=True, exist_ok=True)
        base_id = make_world_id(config)
        world_id = base_id
        suffix = 2
        existing = {item.world_id for item in self.list_worlds()}
        while world_id in existing:
            world_id = f"{base_id}-{suffix}"
            suffix += 1

        database_path = self.worlds_dir / f"{world_id}.db"
        if database_path.exists():
            raise FileExistsError(database_path)

        events = compile_bootstrap_events(config, world_id=world_id)
        try:
            with SQLiteEventStore(database_path) as store:
                store.append_batch("main", events, expected_sequence=0)
        except Exception:
            database_path.unlink(missing_ok=True)
            raise

        descriptor = WorldDescriptor(
            world_id=world_id,
            name=config.name,
            world_type=config.world_type,
            era=config.era,
            population=config.population,
            location_count=config.location_count,
            seed=config.seed,
            database_path=str(database_path),
            created_at=datetime.now(UTC).isoformat(),
        )
        worlds = self._load_catalog()
        worlds.append(descriptor)
        self._save_catalog(worlds)
        return descriptor

    def _load_catalog(self) -> list[WorldDescriptor]:
        if not self.catalog_path.exists():
            return []
        payload = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        return [WorldDescriptor.model_validate(item) for item in payload.get("worlds", [])]

    def _save_catalog(self, worlds: list[WorldDescriptor]) -> None:
        self.worlds_dir.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "worlds": [item.model_dump(mode="json") for item in worlds]}
        temporary = self.catalog_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.catalog_path)

    def _legacy_descriptor(self) -> WorldDescriptor:
        name = "First Living World"
        world_type = "legacy"
        era = "unknown"
        population = 0
        location_count = 0
        seed = "first-living-world"
        try:
            with SQLiteEventStore(self.legacy_db_path) as store:
                events = store.read("main")
                created = next((event for event in events if event.event_type == "world.created"), None)
                if created:
                    flags = created.payload.get("flags", {})
                    name = str(flags.get("world_name") or flags.get("name") or name)
                    world_type = str(flags.get("world_type") or world_type)
                    era = str(flags.get("era") or era)
                    seed = str(flags.get("seed") or seed)
                created_entities = [event for event in events if event.event_type == "entity.created"]
                population = sum(1 for event in created_entities if event.payload.get("kind") in {"human", "character"})
                location_count = sum(1 for event in created_entities if event.payload.get("kind") == "location")
        except Exception:
            pass
        return WorldDescriptor(
            world_id="first-living-world",
            name=name,
            world_type=world_type,
            era=era,
            population=population,
            location_count=location_count,
            seed=seed,
            database_path=str(self.legacy_db_path),
            legacy=True,
        )
