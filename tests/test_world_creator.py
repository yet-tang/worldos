from pathlib import Path

import pytest

from worldos_core.runner import WorldRunner
from worldos_core.sqlite_store import SQLiteEventStore
from worldos_core.world import replay_world
from worldos_core.world_creator import WorldCatalog, WorldConfig, bootstrap_identity, compile_bootstrap_events


def make_config(**overrides):
    values = {"name":"Linan Town","world_type":"agrarian_town","era":"agrarian","population":8,"location_count":4,"resource_abundance":45,"social_stability":55,"conflicts":["resource_scarcity","power_struggle"],"seed":"linan-001"}
    values.update(overrides); return WorldConfig(**values)


def test_bootstrap_compiler_is_deterministic():
    first=[e.model_dump(mode="json") for e in compile_bootstrap_events(make_config())]; second=[e.model_dump(mode="json") for e in compile_bootstrap_events(make_config())]
    assert first==second; assert first[0]["event_type"]=="world.created"; assert first[0]["payload"]["flags"]["world_name"]=="Linan Town"
    assert sum(1 for e in first if e["payload"].get("kind")=="character")==8; assert sum(1 for e in first if e["payload"].get("kind")=="location")==4


def test_cross_world_storage_ids_do_not_change_bootstrap_state():
    config=make_config()
    left=compile_bootstrap_events(config, world_id="storage-a")
    right=compile_bootstrap_events(config, world_id="storage-b")
    assert [e.model_dump(mode="json") for e in left] == [e.model_dump(mode="json") for e in right]
    assert left[0].payload["flags"]["bootstrap_identity"] == bootstrap_identity(config)


def test_duplicate_catalog_worlds_have_identical_initial_canonical_hash(tmp_path):
    catalog=WorldCatalog(tmp_path); first=catalog.create(make_config()); second=catalog.create(make_config())
    assert second.world_id == first.world_id + "-2"
    with SQLiteEventStore(first.database_path) as a, SQLiteEventStore(second.database_path) as b:
        wa=replay_world(a.read("main")); wb=replay_world(b.read("main"))
        assert wa.canonical_hash() == wb.canonical_hash()
        assert wa.flags["world_id"] == wb.flags["world_id"]
        assert wa.flags["bootstrap_identity"] == wb.flags["bootstrap_identity"]


def test_bootstrap_uses_chinese_visible_world_content():
    events=compile_bootstrap_events(make_config(population=3,location_count=6)); locations=[e for e in events if e.payload.get("kind")=="location"]; actors=[e for e in events if e.payload.get("kind")=="character"]
    assert [e.subject_ids[0] for e in locations]==["农田","集市","民居","寺庙","工坊","河畔"]
    assert all(e.subject_ids[0].startswith("人物-") for e in actors); assert all("Resident" not in e.payload["components"]["identity"]["name"] for e in actors)
    assert actors[0].payload["components"]["identity"]["home"]=="农田"; assert actors[0].payload["components"]["rumors"]==["老井的水位可能正在下降"]


def test_different_seed_changes_initial_actor_state():
    left=compile_bootstrap_events(make_config(seed="left")); right=compile_bootstrap_events(make_config(seed="right"))
    la=next(e for e in left if e.payload.get("kind")=="character"); ra=next(e for e in right if e.payload.get("kind")=="character"); assert la.payload["components"] != ra.payload["components"]


def test_catalog_creates_independent_replayable_world(tmp_path):
    catalog=WorldCatalog(tmp_path); first=catalog.create(make_config(name="World A",seed="a")); second=catalog.create(make_config(name="World B",seed="b",world_type="mars_colony",era="future"))
    assert first.world_id != second.world_id; assert first.database_path != second.database_path; assert len(catalog.list_worlds())==2
    with SQLiteEventStore(first.database_path) as store:
        world=replay_world(store.read("main")); assert world.flags["world_name"]=="World A"; assert world.flags["seed"]=="a"; assert len([e for e in world.entities.values() if e.kind=="character"])==8
    with SQLiteEventStore(second.database_path) as store:
        world=replay_world(store.read("main")); assert world.flags["world_name"]=="World B"; assert world.flags["world_type"]=="mars_colony"


def test_created_world_runs_with_generic_runtime(tmp_path):
    descriptor=WorldCatalog(tmp_path).create(make_config(name="Runnable",seed="runtime"))
    with WorldRunner(descriptor.database_path,world_seed=descriptor.seed,snapshot_interval=0) as runner: result=runner.run(1)
    assert result.status.last_completed_tick==1; assert result.status.event_count>13; assert result.status.world_hash


def test_catalog_keeps_legacy_world_visible(tmp_path):
    legacy=tmp_path/"world.db"
    with SQLiteEventStore(legacy) as store: store.append_batch("main",compile_bootstrap_events(make_config(name="Legacy")),expected_sequence=0)
    worlds=WorldCatalog(tmp_path,legacy_db_path=legacy).list_worlds(); assert worlds[0].world_id=="first-living-world"; assert worlds[0].name=="Legacy"; assert worlds[0].legacy is True; assert worlds[0].population==8; assert worlds[0].location_count==4


def test_duplicate_configuration_gets_unique_world_id(tmp_path):
    catalog=WorldCatalog(tmp_path); first=catalog.create(make_config()); second=catalog.create(make_config()); assert second.world_id==first.world_id+"-2"


def test_catalog_deletes_created_world_and_sidecars(tmp_path):
    catalog=WorldCatalog(tmp_path); keep=catalog.create(make_config(name="保留世界",seed="keep")); target=catalog.create(make_config(name="删除世界",seed="delete")); db=Path(target.database_path); wal=Path(str(db)+"-wal"); shm=Path(str(db)+"-shm"); wal.write_bytes(b"wal"); shm.write_bytes(b"shm")
    deleted=catalog.delete(target.world_id); assert deleted.world_id==target.world_id; assert not db.exists(); assert not wal.exists(); assert not shm.exists(); assert [w.world_id for w in catalog.list_worlds()]==[keep.world_id]


def test_catalog_refuses_to_delete_legacy_world(tmp_path):
    legacy=tmp_path/"world.db"
    with SQLiteEventStore(legacy) as store: store.append_batch("main",compile_bootstrap_events(make_config(name="Legacy")),expected_sequence=0)
    catalog=WorldCatalog(tmp_path,legacy_db_path=legacy)
    with pytest.raises(ValueError,match="开发样板世界"): catalog.delete("first-living-world")
    assert legacy.exists()
