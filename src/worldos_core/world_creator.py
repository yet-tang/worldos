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
        location_names=("农田", "集市", "民居", "寺庙", "工坊", "河畔", "东门", "粮仓"),
        jobs=(("food", 2), ("food", 1), ("wood", 2), ("cloth", 1), ("tools", 1), ("grain", 2)),
        default_era="agrarian", starting_resource="food", rumor="老井的水位可能正在下降",
    ),
    "modern_community": WorldTemplate(
        location_names=("公寓", "写字楼", "商场", "学校", "诊所", "公园", "车站", "咖啡馆"),
        jobs=(("credits", 2), ("food", 1), ("services", 2), ("goods", 1), ("knowledge", 1)),
        default_era="modern", starting_resource="food", rumor="社区里最大的雇主可能准备搬离这里",
    ),
    "island_survival": WorldTemplate(
        location_names=("海滩", "营地", "森林", "泉眼", "悬崖", "泻湖", "山洞", "沉船"),
        jobs=(("food", 2), ("wood", 2), ("water", 2), ("tools", 1)),
        default_era="primitive", starting_resource="food", rumor="一场风暴可能很快抵达这座岛",
    ),
    "mars_colony": WorldTemplate(
        location_names=("居住舱", "水培舱", "反应堆", "实验室", "气闸舱", "矿区", "医疗舱", "指挥中心"),
        jobs=(("food", 1), ("oxygen", 2), ("energy", 2), ("parts", 1), ("data", 1)),
        default_era="future", starting_resource="food", rumor="氧气储备的遥测数据可能并不准确",
    ),
    "custom": WorldTemplate(
        location_names=("中心区", "北区", "南区", "东区", "西区", "公共区", "工坊", "前哨站"),
        jobs=(("food", 1), ("wood", 1), ("tools", 1), ("services", 1)),
        default_era="modern", starting_resource="food", rumor="当地原本稳定的平衡正在悄悄发生变化",
    ),
}

_SURNAMES = ("沈", "顾", "林", "陆", "陈", "周", "江", "许", "苏", "宋", "叶", "唐", "谢", "温", "秦", "程", "方", "何", "韩", "赵")
_GIVEN_FIRST = ("清", "明", "知", "景", "书", "若", "安", "云", "言", "时")
_GIVEN_SECOND = ("和", "川", "远", "宁", "舟", "禾", "夏", "秋", "衡", "月")


def _stable_rng(seed: str) -> random.Random:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized[:32] or "world"


def make_world_id(config: WorldConfig) -> str:
    fingerprint = hashlib.sha256(json.dumps(config.model_dump(mode="json"), ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:8]
    return f"{_slug(config.name)}-{fingerprint}"


def bootstrap_identity(config: WorldConfig) -> str:
    """Stable experiment identity: same creation inputs produce the same bootstrap state."""
    canonical = json.dumps(config.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _chinese_actor_name(index: int, seed: str) -> str:
    digest = hashlib.sha256(f"{seed}:{index}".encode("utf-8")).digest()
    return f"{_SURNAMES[digest[0] % len(_SURNAMES)]}{_GIVEN_FIRST[digest[1] % len(_GIVEN_FIRST)]}{_GIVEN_SECOND[digest[2] % len(_GIVEN_SECOND)]}"


def compile_bootstrap_events(config: WorldConfig, *, world_id: str | None = None) -> list[NewEvent]:
    """Compile config into bootstrap events whose physical state is independent of catalog suffixes."""
    template = TEMPLATES[config.world_type]
    rng = _stable_rng(config.seed)
    storage_world_id = world_id or make_world_id(config)
    experiment_id = bootstrap_identity(config)

    location_names = list(template.location_names[: config.location_count])
    while len(location_names) < config.location_count:
        location_names.append(f"区域{len(location_names) + 1:02d}")

    events: list[NewEvent] = [NewEvent(tick=0, phase="bootstrap", event_type="world.created", payload={"flags": {
        # world_id is intentionally a deterministic simulation identity. The catalog descriptor/database
        # remains the storage identity, so duplicate worlds can coexist without contaminating canonical state.
        "world_id": f"sim-{experiment_id[:16]}", "world_name": config.name, "world_type": config.world_type,
        "era": config.era, "scenario_version": 4, "seed": config.seed, "bootstrap_identity": experiment_id,
        "resource_abundance": config.resource_abundance, "social_stability": config.social_stability,
        "initial_conflicts": list(config.conflicts), "locations": location_names,
    }})]

    for location_id in location_names:
        events.append(NewEvent(tick=0, phase="bootstrap", event_type="entity.created", subject_ids=(location_id,), payload={"kind": "location", "components": {"name": location_id, "identity": {"name": location_id}}}))

    base_inventory = 1 + round(config.resource_abundance / 20)
    base_wallet = 5 + round(config.resource_abundance / 5)
    stress = max(0, 100 - config.resource_abundance)
    instability = max(0, 100 - config.social_stability)
    actor_ids = [f"人物-{index:03d}" for index in range(1, config.population + 1)]
    components_by_actor: dict[str, dict[str, Any]] = {}
    for index, actor_id in enumerate(actor_ids):
        location_id = location_names[index % len(location_names)]
        resource, rate = template.jobs[index % len(template.jobs)]
        hunger = min(80, rng.randint(0, 12) + stress // 8)
        fatigue = min(70, rng.randint(0, 15) + instability // 12)
        inventory = {resource: max(1, base_inventory + rng.randint(0, 2)), template.starting_resource: max(1, base_inventory // 2 + 1)}
        components_by_actor[actor_id] = {
            "identity": {"name": _chinese_actor_name(index + 1, config.seed), "home": location_names[0]},
            "position": {"location_id": location_id}, "health": {"current": 100, "maximum": 100},
            "needs": {"hunger": hunger, "fatigue": fatigue}, "survival": {"hunger": hunger, "fatigue": fatigue},
            "metabolism": {"hunger_per_tick": 1, "fatigue_per_tick": 1}, "inventory": inventory,
            "wallet": max(0, base_wallet + rng.randint(-3, 4)), "job": {"resource": resource, "rate": rate},
            "relationships": {}, "rumors": [], "world_role": {"template": config.world_type, "era": config.era},
        }
    if actor_ids:
        components_by_actor[actor_ids[0]]["rumors"] = [template.rumor]

    relationship_span = min(3, max(1, config.population - 1))
    for index, actor_id in enumerate(actor_ids):
        relationships: dict[str, int] = {}
        for offset in range(1, relationship_span + 1):
            if len(actor_ids) <= 1: break
            other = actor_ids[(index + offset) % len(actor_ids)]
            if other == actor_id: continue
            center = config.social_stability - 50
            relationships[other] = max(-50, min(50, center // 2 + rng.randint(-10, 10)))
        components_by_actor[actor_id]["relationships"] = relationships

    if "resource_scarcity" in config.conflicts and len(actor_ids) >= 2:
        seller, buyer = actor_ids[0], actor_ids[1]
        components_by_actor[seller]["trade_offer"] = {"buyer_id": buyer, "resource": template.starting_resource, "quantity": 1, "price": max(1, 6 - config.resource_abundance // 25)}
    if ("inequality" in config.conflicts or "power_struggle" in config.conflicts) and len(actor_ids) >= 2:
        components_by_actor[actor_ids[0]]["conflict"] = {"target_id": actor_ids[-1], "severity": max(10, 60 - config.social_stability // 2)}
    if "external_threat" in config.conflicts and actor_ids:
        components_by_actor[actor_ids[0]]["rumors"].append("边界附近出现了外部威胁的消息")
    if "disease" in config.conflicts and actor_ids:
        for actor_id in actor_ids[: max(1, len(actor_ids) // 10)]:
            components_by_actor[actor_id]["health"] = {"current": 85, "maximum": 100}
            components_by_actor[actor_id]["condition"] = {"name": "初始疾病", "severity": 15}
    for actor_id in actor_ids:
        events.append(NewEvent(tick=0, phase="bootstrap", event_type="entity.created", subject_ids=(actor_id,), payload={"kind": "character", "components": components_by_actor[actor_id]}))
    return events


class WorldCatalog:
    """Development-stage registry for multiple independent world databases."""
    def __init__(self, data_dir: str | Path, *, legacy_db_path: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir); self.worlds_dir = self.data_dir / "worlds"; self.catalog_path = self.worlds_dir / "catalog.json"
        self.legacy_db_path = Path(legacy_db_path) if legacy_db_path else self.data_dir / "world.db"

    def list_worlds(self) -> list[WorldDescriptor]:
        worlds = self._load_catalog()
        if self.legacy_db_path.exists() and not any(item.database_path == str(self.legacy_db_path) for item in worlds): worlds.insert(0, self._legacy_descriptor())
        return worlds

    def get(self, world_id: str) -> WorldDescriptor:
        for item in self.list_worlds():
            if item.world_id == world_id: return item
        raise KeyError(f"unknown world: {world_id}")

    def default_world(self) -> WorldDescriptor | None:
        worlds = self.list_worlds(); return worlds[0] if worlds else None

    def create(self, config: WorldConfig) -> WorldDescriptor:
        self.worlds_dir.mkdir(parents=True, exist_ok=True); base_id = make_world_id(config); world_id = base_id; suffix = 2
        existing = {item.world_id for item in self.list_worlds()}
        while world_id in existing: world_id = f"{base_id}-{suffix}"; suffix += 1
        database_path = self.worlds_dir / f"{world_id}.db"
        if database_path.exists(): raise FileExistsError(database_path)
        events = compile_bootstrap_events(config, world_id=world_id)
        try:
            with SQLiteEventStore(database_path) as store: store.append_batch("main", events, expected_sequence=0)
        except Exception:
            database_path.unlink(missing_ok=True); raise
        descriptor = WorldDescriptor(world_id=world_id, name=config.name, world_type=config.world_type, era=config.era, population=config.population, location_count=config.location_count, seed=config.seed, database_path=str(database_path), created_at=datetime.now(UTC).isoformat())
        worlds = self._load_catalog(); worlds.append(descriptor); self._save_catalog(worlds); return descriptor

    def delete(self, world_id: str) -> WorldDescriptor:
        if world_id == "first-living-world": raise ValueError("开发样板世界不能从页面删除")
        worlds = self._load_catalog(); target = next((item for item in worlds if item.world_id == world_id), None)
        if target is None: raise KeyError(f"unknown world: {world_id}")
        database_path = Path(target.database_path)
        for path in (database_path, Path(str(database_path)+"-wal"), Path(str(database_path)+"-shm")): path.unlink(missing_ok=True)
        self._save_catalog([item for item in worlds if item.world_id != world_id]); return target

    def _load_catalog(self) -> list[WorldDescriptor]:
        if not self.catalog_path.exists(): return []
        payload = json.loads(self.catalog_path.read_text(encoding="utf-8")); return [WorldDescriptor.model_validate(item) for item in payload.get("worlds", [])]

    def _save_catalog(self, worlds: list[WorldDescriptor]) -> None:
        self.worlds_dir.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "worlds": [item.model_dump(mode="json") for item in worlds]}
        temp_path = self.catalog_path.with_suffix(".tmp"); temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"); temp_path.replace(self.catalog_path)

    def _legacy_descriptor(self) -> WorldDescriptor:
        with SQLiteEventStore(self.legacy_db_path) as store:
            events = store.read("main"); world_event = next((event for event in events if event.event_type == "world.created"), None); flags = world_event.payload.get("flags", {}) if world_event else {}
            entities = [event for event in events if event.event_type == "entity.created"]
            population = sum(1 for event in entities if event.payload.get("kind") in {"human", "character"}); locations = sum(1 for event in entities if event.payload.get("kind") == "location")
        return WorldDescriptor(world_id="first-living-world", name=str(flags.get("world_name", "First Living World")), world_type=str(flags.get("world_type", "legacy")), era=str(flags.get("era", "unknown")), population=population, location_count=locations, seed=str(flags.get("seed", "legacy")), database_path=str(self.legacy_db_path), legacy=True)
