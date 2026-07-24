from __future__ import annotations

import argparse
import json

from .events import NewEvent
from .store import InMemoryEventStore
from .world import replay_world


def demo() -> None:
    store = InMemoryEventStore()
    initial = [
        NewEvent(tick=0, phase="bootstrap", event_type="world.created", payload={"flags": {"weather": "snow"}}),
        NewEvent(tick=0, phase="bootstrap", event_type="entity.created", subject_ids=("traveler",), payload={"kind": "human", "components": {"position": {"location_id": "hall"}, "health": {"current": 100, "maximum": 100}}}),
        NewEvent(tick=0, phase="bootstrap", event_type="entity.created", subject_ids=("assassin",), payload={"kind": "human", "components": {"position": {"location_id": "hall"}, "health": {"current": 100, "maximum": 100}}}),
        NewEvent(tick=1, phase="resolution", event_type="entity.moved", actor_id="traveler", subject_ids=("traveler",), payload={"to_location_id": "room_2"}),
        NewEvent(tick=2, phase="resolution", event_type="health.changed", actor_id="assassin", subject_ids=("traveler",), payload={"delta": -40, "resolution_roll": 73}),
    ]
    store.append_batch("main", initial, expected_sequence=0)
    main = replay_world(store.read("main"))

    store.create_timeline("letter_not_stolen", parent_timeline_id="main", parent_through_sequence=4)
    store.append_batch(
        "letter_not_stolen",
        [
            NewEvent(tick=2, phase="resolution", event_type="entity.moved", actor_id="assassin", subject_ids=("assassin",), payload={"to_location_id": "kitchen"}),
            NewEvent(tick=3, phase="consequence", event_type="world.flag_set", payload={"name": "violence_started", "value": False}),
        ],
        expected_sequence=4,
    )
    branch = replay_world(store.read("letter_not_stolen"))

    result = {
        "main": {"hash": main.canonical_hash(), "traveler": main.entities["traveler"].model_dump(mode="json")},
        "branch": {"hash": branch.canonical_hash(), "traveler": branch.entities["traveler"].model_dump(mode="json"), "assassin": branch.entities["assassin"].model_dump(mode="json")},
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(prog="worldos-core")
    parser.add_argument("command", choices=["demo"])
    args = parser.parse_args()
    if args.command == "demo":
        demo()


if __name__ == "__main__":
    main()
