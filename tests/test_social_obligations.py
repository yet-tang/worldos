from worldos_core.events import NewEvent
from worldos_core.inspector import WorldInspector
from worldos_core.scheduler import DeterministicTickEngine
from worldos_core.social import SocialProjection, replay_social
from worldos_core.store import InMemoryEventStore
from worldos_core.world import replay_world


def _actor(
    actor_id: str,
    *,
    food: int = 3,
    hunger: int = 20,
    relationships: dict[str, int] | None = None,
    personality: dict[str, int] | None = None,
    drives: dict[str, int] | None = None,
) -> NewEvent:
    return NewEvent(
        tick=0,
        phase="bootstrap",
        event_type="entity.created",
        subject_ids=(actor_id,),
        payload={
            "kind": "character",
            "components": {
                "identity": {"name": actor_id},
                "position": {"location_id": "集市"},
                "health": {"current": 100, "maximum": 100},
                "needs": {"hunger": hunger, "fatigue": 10},
                "survival": {"hunger": hunger, "fatigue": 10},
                "inventory": {"food": food},
                "relationships": relationships or {},
                **({"personality": personality} if personality else {}),
                **({"drives": drives} if drives else {}),
            },
        },
    )


def test_social_projection_separates_affinity_trust_and_grievance():
    store = InMemoryEventStore()
    store.append_batch(
        "main",
        [
            NewEvent(
                tick=1,
                phase="resolution",
                event_type="social.helped",
                actor_id="甲",
                subject_ids=("甲", "乙"),
                payload={"target_id": "乙", "resource": "food", "quantity": 1},
            ),
            NewEvent(
                tick=2,
                phase="resolution",
                event_type="social.interacted",
                actor_id="乙",
                subject_ids=("乙", "甲"),
                payload={"target_id": "甲"},
            ),
            NewEvent(
                tick=3,
                phase="resolution",
                event_type="social.confronted",
                actor_id="乙",
                subject_ids=("乙", "丙"),
                payload={"target_id": "丙"},
            ),
        ],
        expected_sequence=0,
    )
    social = replay_social(store.read("main"))

    toward_helper = social.bond("乙", "甲")
    assert toward_helper.affinity > 0
    assert toward_helper.trust > 0
    assert toward_helper.helps_received == 1

    toward_rival = social.bond("乙", "丙")
    assert toward_rival.affinity < 0
    assert toward_rival.trust < 0
    assert toward_rival.grievance > 0


def test_help_creates_obligation_then_debtor_autonomously_repays():
    store = InMemoryEventStore()
    store.append_batch(
        "main",
        [
            _actor(
                "甲",
                food=3,
                personality={
                    "sociability": 10,
                    "generosity": 100,
                    "assertiveness": 10,
                    "risk_tolerance": 10,
                },
                drives={
                    "security": 30,
                    "belonging": 10,
                    "status": 20,
                    "wealth": 20,
                    "curiosity": 10,
                },
            ),
            _actor(
                "乙",
                food=3,
                hunger=60,
                personality={
                    "sociability": 10,
                    "generosity": 10,
                    "assertiveness": 10,
                    "risk_tolerance": 10,
                },
                drives={
                    "security": 90,
                    "belonging": 10,
                    "status": 90,
                    "wealth": 10,
                    "curiosity": 10,
                },
            ),
            _actor("丙", food=3, hunger=20),
        ],
        expected_sequence=0,
    )
    engine = DeterministicTickEngine(store, world_seed="social-loop")
    for tick in range(1, 21):
        engine.run_tick("main", tick)
        if any(event.event_type == "obligation.fulfilled" for event in store.read("main")):
            break

    history = store.read("main")
    event_types = [event.event_type for event in history]
    assert "social.helped" in event_types
    assert "obligation.created" in event_types
    assert "social.repaid" in event_types
    assert "obligation.fulfilled" in event_types
    assert any(
        event.event_type == "motivation.selected"
        and event.actor_id == "乙"
        and event.payload.get("goal_type") == "repay_obligation"
        for event in history
    )

    social = replay_social(history)
    obligations = list(social.obligations.values())
    assert obligations
    assert obligations[0].debtor_id == "乙"
    assert obligations[0].creditor_id == "甲"
    assert obligations[0].status == "fulfilled"
    assert social.bond("甲", "乙").trust > 0
    assert social.bond("乙", "甲").trust > 0

    world = replay_world(history)
    assert world.entities["甲"].components["inventory"]["food"] == 3
    assert world.entities["乙"].components["inventory"]["food"] == 3
    assert any(
        event.event_type == "observation.created"
        and event.actor_id == "丙"
        and event.payload.get("fact_type") == "social.repaid"
        for event in history
    )


def test_unfulfilled_resource_debt_creates_rivalry_before_enemy_escalation():
    store = InMemoryEventStore()
    store.append_batch(
        "main",
        [
            _actor("甲", food=2),
            _actor(
                "乙",
                food=0,
                personality={
                    "sociability": 10,
                    "generosity": 10,
                    "assertiveness": 10,
                    "risk_tolerance": 10,
                },
                drives={
                    "security": 30,
                    "belonging": 10,
                    "status": 20,
                    "wealth": 90,
                    "curiosity": 10,
                },
            ),
            NewEvent(
                tick=0,
                phase="social",
                event_type="obligation.created",
                actor_id="乙",
                subject_ids=("乙", "甲"),
                payload={
                    "obligation_id": "obl_test_default",
                    "debtor_id": "乙",
                    "creditor_id": "甲",
                    "kind": "resource_debt",
                    "resource": "food",
                    "quantity": 1,
                    "created_tick": 0,
                    "due_tick": 2,
                    "status": "open",
                },
            ),
        ],
        expected_sequence=0,
    )
    engine = DeterministicTickEngine(store, world_seed="default-loop")
    engine.run_tick("main", 1)
    engine.run_tick("main", 2)

    history = store.read("main")
    social = replay_social(history)
    obligation = social.obligations["obl_test_default"]
    assert obligation.status == "defaulted"
    creditor_view = social.bond("甲", "乙")
    assert creditor_view.grievance >= 12
    assert creditor_view.trust < 0
    assert creditor_view.label() == "rival"

    world = replay_world(history)
    assert world.entities["甲"].components["relationships"]["乙"] <= -10
    assert any(
        event.event_type == "observation.created"
        and event.actor_id == "甲"
        and event.payload.get("fact_type") == "obligation.defaulted"
        for event in history
    )


def test_unreturned_favor_only_cools_trust():
    store = InMemoryEventStore()
    store.append_batch(
        "main",
        [
            _actor("甲"),
            _actor("乙", food=0),
            NewEvent(
                tick=0,
                phase="social",
                event_type="obligation.created",
                actor_id="乙",
                subject_ids=("乙", "甲"),
                payload={
                    "obligation_id": "obl_soft_favor",
                    "debtor_id": "乙",
                    "creditor_id": "甲",
                    "kind": "favor",
                    "resource": "food",
                    "quantity": 1,
                    "created_tick": 0,
                    "due_tick": 1,
                    "status": "open",
                },
            ),
        ],
        expected_sequence=0,
    )
    engine = DeterministicTickEngine(store, world_seed="favor-loop")
    engine.run_tick("main", 1)

    social = replay_social(store.read("main"))
    creditor_view = social.bond("甲", "乙")
    assert social.obligations["obl_soft_favor"].status == "defaulted"
    assert creditor_view.grievance == 3
    assert creditor_view.trust == -4
    assert creditor_view.label() == "stranger"


def test_inspector_exposes_bonds_and_obligations():
    store = InMemoryEventStore()
    store.append_batch(
        "main",
        [
            _actor("甲"),
            _actor("乙"),
            NewEvent(
                tick=1,
                phase="resolution",
                event_type="social.interacted",
                actor_id="甲",
                subject_ids=("甲", "乙"),
                payload={"target_id": "乙"},
            ),
            NewEvent(
                tick=1,
                phase="social",
                event_type="obligation.created",
                actor_id="乙",
                subject_ids=("乙", "甲"),
                payload={
                    "obligation_id": "obl_inspector",
                    "debtor_id": "乙",
                    "creditor_id": "甲",
                    "kind": "favor",
                    "resource": "food",
                    "quantity": 1,
                    "created_tick": 1,
                    "due_tick": 12,
                    "status": "open",
                },
            ),
        ],
        expected_sequence=0,
    )
    inspector = WorldInspector(store)
    creditor = inspector.actor("甲")
    debtor = inspector.actor("乙")

    assert creditor.social_bonds[0].other_id == "乙"
    assert creditor.obligations_as_creditor[0].obligation_id == "obl_inspector"
    assert debtor.obligations_as_debtor[0].obligation_id == "obl_inspector"


def test_social_replay_is_deterministic():
    left = SocialProjection()
    right = SocialProjection()
    store = InMemoryEventStore()
    store.append_batch(
        "main",
        [
            NewEvent(
                tick=1,
                phase="resolution",
                event_type="social.interacted",
                actor_id="甲",
                subject_ids=("甲", "乙"),
                payload={"target_id": "乙"},
            ),
            NewEvent(
                tick=2,
                phase="social",
                event_type="obligation.created",
                actor_id="乙",
                subject_ids=("乙", "甲"),
                payload={
                    "obligation_id": "obl_deterministic",
                    "debtor_id": "乙",
                    "creditor_id": "甲",
                    "kind": "favor",
                    "resource": "food",
                    "quantity": 1,
                    "created_tick": 2,
                    "due_tick": 10,
                    "status": "open",
                },
            ),
        ],
        expected_sequence=0,
    )
    history = store.read("main")
    left = replay_social(history, left)
    right = replay_social(history, right)
    assert left.model_dump(mode="json") == right.model_dump(mode="json")
