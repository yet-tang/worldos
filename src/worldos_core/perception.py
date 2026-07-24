from __future__ import annotations

import hashlib
import json

from .events import Event, NewEvent
from .store import InMemoryEventStore
from .world import WorldProjection, replay_world


class PerceptionEngine:
    """Derives observer-specific observations and beliefs from committed world events."""

    AUDIBLE_EVENTS = {"attack.attempted", "attack.resolved", "health.changed"}
    VISIBLE_EVENTS = {"entity.moved", "attack.attempted", "attack.resolved", "health.changed"}

    def derive(self, source_events: list[Event], state: WorldProjection) -> list[NewEvent]:
        derived: list[NewEvent] = []
        for source in source_events:
            for observer_id, observer in sorted(state.entities.items()):
                if not observer.active or not self._can_perceive(observer_id, source, state):
                    continue
                observation_id = self._observation_id(observer_id, source.event_id)
                data = {
                    "event_type": source.event_type,
                    "actor_id": source.actor_id,
                    "subject_ids": list(source.subject_ids),
                    "payload": source.payload,
                }
                derived.append(NewEvent(
                    tick=source.tick,
                    phase="knowledge",
                    event_type="observation.created",
                    actor_id=observer_id,
                    subject_ids=(observer_id, *source.subject_ids),
                    caused_by=(source.event_id,),
                    correlation_id=source.correlation_id,
                    payload={
                        "observation_id": observation_id,
                        "observer_id": observer_id,
                        "source_event_id": source.event_id,
                        "tick": source.tick,
                        "fact_type": source.event_type,
                        "subject_ids": list(source.subject_ids),
                        "data": data,
                        "confidence": 1.0,
                    },
                ))
                derived.append(NewEvent(
                    tick=source.tick,
                    phase="knowledge",
                    event_type="belief.updated",
                    actor_id=observer_id,
                    subject_ids=(observer_id, *source.subject_ids),
                    caused_by=(source.event_id,),
                    correlation_id=source.correlation_id,
                    payload={
                        "belief_id": self._belief_id(observer_id, source),
                        "observer_id": observer_id,
                        "fact_type": source.event_type,
                        "subject_ids": list(source.subject_ids),
                        "data": data,
                        "confidence": 1.0,
                        "source_observation_id": observation_id,
                        "updated_tick": source.tick,
                    },
                ))
        return derived

    def process(self, store: InMemoryEventStore, timeline_id: str, source_events: list[Event], *, expected_sequence: int | None = None) -> list[Event]:
        state = replay_world(store.read(timeline_id))
        candidates = self.derive(source_events, state)
        if not candidates:
            return []
        return store.append_batch(timeline_id, candidates, expected_sequence=expected_sequence)

    def _can_perceive(self, observer_id: str, source: Event, state: WorldProjection) -> bool:
        if observer_id in source.subject_ids or observer_id == source.actor_id:
            return True
        if source.event_type not in self.VISIBLE_EVENTS | self.AUDIBLE_EVENTS:
            return False
        observer = state.entities[observer_id]
        observer_location = observer.components.get("position", {}).get("location_id")
        participants = [entity_id for entity_id in (source.actor_id, *source.subject_ids) if entity_id in state.entities]
        return any(state.entities[entity_id].components.get("position", {}).get("location_id") == observer_location for entity_id in participants)

    @staticmethod
    def _observation_id(observer_id: str, source_event_id: str) -> str:
        digest = hashlib.sha256(f"{observer_id}:{source_event_id}".encode()).hexdigest()
        return f"obs_{digest[:24]}"

    @staticmethod
    def _belief_id(observer_id: str, source: Event) -> str:
        key = json.dumps([observer_id, source.event_type, sorted(source.subject_ids)], separators=(",", ":"))
        return f"blf_{hashlib.sha256(key.encode()).hexdigest()[:24]}"
