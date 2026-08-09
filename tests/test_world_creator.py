from worldos_core.sqlite_store import SQLiteEventStore
from worldos_core.world import replay_world
from worldos_core.world_creator import WorldCatalog, WorldConfig, compile_bootstrap_events


def make_config(**overrides):
    values = {
        "name": "Linan Town",
        "world_type": "agrarian_town",
        "era": "agrarian",
        "population": 8,
        "location_count": 4,
        "resource_abundance": 45,
        "social_stability": 55,
        "conflicts": ["resource_scarcity", "power_struggle"],
        "seed": "linan-001",
    }
    values.update(overrides)
    return WorldConfig(**values)


def test_bootstrap_compiler_is_deterministic():
    first = [event.model_dump(mode="json") for event in compile_bootstrap_events(make_config())]
    second = [event.model_dump(mode="json") for event in compile_bootstrap_events(make_config())]

    assert first == second
    assert first[0]["event_type"] == "world.created"
    assert first[0]["payload"]["flags"]["world_name"] == "Linan Town"
    assert sum(1 for event in first if event["payload"].get("kind") == "character") == 8
    assert sum(1 for event in first if event["payload"].get("kind") == "location") == 4


def test_different_seed_changes_initial_actor_state():
    left = compile_bootstrap_events(make_config(seed="left"))
    right = compile_bootstrap_events(make_config(seed="right"))

    left_actor = next(event for event in left if event.payload.get("kind") == "character")
    right_actor = next(event for event in right if event.payload.get("kind") == "character")
    assert left_actor.payload["components"] != right_actor.payload["components"]


def test_catalog_creates_independent_replayable_world(tmp_path):
    catalog = WorldCatalog(tmp_path)
    first = catalog.create(make_config(name="World A", seed="a"))
    second = catalog.create(make_config(name="World B", seed="b", world_type="mars_colony", era="future"))

    assert first.world_id != second.world_id
    assert first.database_path != second.database_path
    assert len(catalog.list_worlds()) == 2

    with SQLiteEventStore(first.database_path) as store:
        history = store.read("main")
        world = replay_world(history)
        assert world.flags["world_name"] == "World A"
        assert world.flags["seed"] == "a"
        assert len([entity for entity in world.entities.values() if entity.kind == "character"]) == 8

    with SQLiteEventStore(second.database_path) as store:
        history = store.read("main")
        world = replay_world(history)
        assert world.flags["world_name"] == "World B"
        assert world.flags["world_type"] == "mars_colony"


def test_catalog_keeps_legacy_world_visible(tmp_path):
    legacy = tmp_path / "world.db"
    with SQLiteEventStore(legacy) as store:
        store.append_batch("main", compile_bootstrap_events(make_config(name="Legacy")), expected_sequence=0)

    catalog = WorldCatalog(tmp_path, legacy_db_path=legacy)
    worlds = catalog.list_worlds()

    assert worlds[0].world_id == "first-living-world"
    assert worlds[0].name == "Legacy"
    assert worlds[0].legacy is True
    assert worlds[0].population == 8
    assert worlds[0].location_count == 4


def test_duplicate_configuration_gets_unique_world_id(tmp_path):
    catalog = WorldCatalog(tmp_path)
    first = catalog.create(make_config())
    second = catalog.create(make_config())

    assert second.world_id == first.world_id + "-2"
