from worldos_core.events import NewEvent
from worldos_core.modules import ModuleContext
from worldos_core.store import InMemoryEventStore
from worldos_core.survival import SurvivalEconomyModule
from worldos_core.world import replay_world


def _seed(store: InMemoryEventStore, *, hunger: int = 40, fatigue: int = 10) -> None:
    store.append_batch(
        "main",
        [
            NewEvent(tick=0, phase="projection", event_type="entity.created", subject_ids=("alice",), payload={"kind": "character", "components": {"position": {"location_id": "market"}, "health": {"current": 100, "maximum": 100}, "needs": {"hunger": hunger, "fatigue": fatigue}, "survival": {"hunger": hunger, "fatigue": fatigue}, "metabolism": {"hunger_per_tick": 1, "fatigue_per_tick": 2}, "job": {"resource": "food", "rate": 3}, "inventory": {"food": 1}, "wallet": 0, "trade_offer": {"buyer_id": "bob", "resource": "food", "quantity": 2, "price": 4}, "rumors": ["the well is dry"], "relationships": {}, "conflict": {"target_id": "bob", "severity": 40}}}),
            NewEvent(tick=0, phase="projection", event_type="entity.created", subject_ids=("bob",), payload={"kind": "character", "components": {"position": {"location_id": "market"}, "health": {"current": 100, "maximum": 100}, "needs": {"hunger": 10, "fatigue": 5}, "survival": {"hunger": 10, "fatigue": 5}, "inventory": {}, "wallet": 10, "rumors": [], "relationships": {}}}),
        ], expected_sequence=0)


def _run_tick(store: InMemoryEventStore, tick: int):
    history = tuple(store.read("main")); context = ModuleContext(timeline_id="main", tick=tick, world=replay_world(list(history)), history=history)
    return store.append_batch("main", SurvivalEconomyModule().before_actions(context), expected_sequence=len(history))


def test_survival_economy_module_closes_deterministic_loop():
    store = InMemoryEventStore(); _seed(store); committed = _run_tick(store, 1); world = replay_world(store.read("main")); alice = world.entities["alice"].components; bob = world.entities["bob"].components; event_types = [event.event_type for event in committed]
    assert alice["needs"] == {"hunger": 41, "fatigue": 12}; assert alice["inventory"]["food"] >= 1; assert bob["health"]["current"] < 100; assert alice["relationships"]["bob"] <= 0; assert "trade_offer" not in alice; assert "conflict" not in alice; assert event_types.count("health.changed") >= 1; assert {"survival.metabolized", "resource.produced", "trade.completed", "conflict.resolved", "scarcity.perceived"}.issubset(event_types)


def test_critical_needs_stop_automatic_work_and_damage_health():
    store = InMemoryEventStore(); _seed(store, hunger=99, fatigue=99); committed = _run_tick(store, 1); world = replay_world(store.read("main")); alice = world.entities["alice"].components; alice_events = [event for event in committed if event.actor_id == "alice"]; self_damage = [event for event in committed if event.event_type == "health.changed" and event.subject_ids == ("alice",)]
    assert alice["needs"] == {"hunger": 100, "fatigue": 100}; assert alice["inventory"]["food"] == 1; assert alice["health"]["current"] == 98; assert "resource.produced" not in [event.event_type for event in alice_events]; assert len(self_damage) == 2


def test_zero_health_deactivates_character():
    store = InMemoryEventStore(); store.append_batch("main", [NewEvent(tick=0, phase="projection", event_type="entity.created", subject_ids=("alice",), payload={"kind": "character", "components": {"health": {"current": 1, "maximum": 100}, "needs": {"hunger": 99, "fatigue": 0}, "survival": {"hunger": 99, "fatigue": 0}, "metabolism": {"hunger_per_tick": 1, "fatigue_per_tick": 0}}})], expected_sequence=0)
    _run_tick(store, 1); alice = replay_world(store.read("main")).entities["alice"]
    assert alice.components["health"]["current"] == 0; assert alice.active is False


def test_resource_shock_uses_fractional_carry_so_long_run_modifier_is_linear():
    store = InMemoryEventStore(); _seed(store)
    store.append_batch("main", [NewEvent(tick=0, phase="external", event_type="world.stimulus.resource_shock", payload={"stimulus_kind": "resource_shock", "resource": "food", "magnitude": -0.4, "duration_ticks": 5})], expected_sequence=2)
    quantities = []
    for tick in range(1, 6):
        committed = _run_tick(store, tick)
        produced = next(event for event in committed if event.event_type == "resource.produced" and event.actor_id == "alice")
        quantities.append(produced.payload["quantity"])
        assert produced.payload["stimulus_modifier"] == -0.4
    assert sum(quantities) == 9


def test_information_stimulus_seeds_rumor_once_and_remains_replay_safe():
    store = InMemoryEventStore(); _seed(store)
    store.append_batch("main", [NewEvent(tick=0, phase="external", event_type="world.stimulus.spread_information", payload={"message": "市场传言粮价要涨", "actor_ids": ["bob"], "duration_ticks": 1})], expected_sequence=2)
    committed = _run_tick(store, 1); world = replay_world(store.read("main")); types = [event.event_type for event in committed]
    assert "市场传言粮价要涨" in world.entities["bob"].components["rumors"]
    assert "rumor.seeded" in types
    _run_tick(store, 2)
    world2 = replay_world(store.read("main"))
    assert world2.entities["bob"].components["rumors"].count("市场传言粮价要涨") == 1


def test_high_scarcity_can_endogenously_trigger_resource_conflict_after_sustained_pressure():
    store = InMemoryEventStore()
    store.append_batch("main", [
        NewEvent(tick=0, phase="projection", event_type="world.created", payload={"flags": {"seed": "conflict-test"}}),
        NewEvent(tick=0, phase="projection", event_type="entity.created", subject_ids=("hungry",), payload={"kind": "character", "components": {"position": {"location_id": "market"}, "health": {"current": 100, "maximum": 100}, "needs": {"hunger": 100, "fatigue": 0}, "survival": {"hunger": 100, "fatigue": 0}, "metabolism": {"hunger_per_tick": 0, "fatigue_per_tick": 0}, "inventory": {"food": 0}, "wallet": 0, "relationships": {"holder": -20}, "rumors": ["粮食可能会短缺", "有人囤粮", "市场已经断粮"]}}),
        NewEvent(tick=0, phase="projection", event_type="entity.created", subject_ids=("holder",), payload={"kind": "character", "components": {"position": {"location_id": "market"}, "health": {"current": 100, "maximum": 100}, "needs": {"hunger": 0, "fatigue": 0}, "survival": {"hunger": 0, "fatigue": 0}, "metabolism": {"hunger_per_tick": 0, "fatigue_per_tick": 0}, "inventory": {"food": 8}, "wallet": 0, "relationships": {"hungry": -20}, "rumors": []}}),
    ], expected_sequence=0)
    first = _run_tick(store, 1); second = _run_tick(store, 2); third = _run_tick(store, 3)
    assert "conflict.resolved" not in [event.event_type for event in first]
    assert "conflict.resolved" not in [event.event_type for event in second]
    types = [event.event_type for event in third]
    world = replay_world(store.read("main"))
    assert "conflict.resolved" in types
    assert world.entities["holder"].components["health"]["current"] < 100
    assert world.entities["hungry"].components["relationships"]["holder"] < -20
    evidence = [event for event in third if event.event_type == "decision.evidence" and event.actor_id == "hungry"]
    assert any(event.payload.get("decision") == "resource_conflict" for event in evidence)


def test_survival_economy_is_replay_deterministic():
    first = InMemoryEventStore(); second = InMemoryEventStore()
    for store in (first, second):
        _seed(store); _run_tick(store, 1)
    assert replay_world(first.read("main")).canonical_hash() == replay_world(second.read("main")).canonical_hash(); assert [event.model_dump(exclude={"event_id", "timeline_id", "sequence"}) for event in first.read("main")] == [event.model_dump(exclude={"event_id", "timeline_id", "sequence"}) for event in second.read("main")]
