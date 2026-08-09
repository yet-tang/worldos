from __future__ import annotations

from pydantic import BaseModel

from .actions import (
    ActionContext,
    ActionRule,
    AttackRule,
    ConfrontRule,
    EatRule,
    HelpResidentRule,
    MoveRule,
    RequestResourceRule,
    RestRule,
    SocializeRule,
)
from .events import Event, NewEvent
from .intents import Intent, ValidationIssue
from .resolution import DeterministicResolver
from .social_actions import RepayObligationRule
from .store import InMemoryEventStore
from .world import WorldProjection, replay_world


class IntentProcessingResult(BaseModel):
    intent_id: str
    accepted: bool
    committed_events: tuple[Event, ...]
    issues: tuple[ValidationIssue, ...] = ()


class IntentPipelineError(RuntimeError):
    pass


class IntentPipeline:
    """Validates and resolves intents, then atomically appends resulting events."""

    def __init__(self, store: InMemoryEventStore, *, world_seed: str | int, rules: tuple[ActionRule, ...] | None = None) -> None:
        self.store = store
        self.resolver = DeterministicResolver(world_seed)
        registered = rules or (
            MoveRule(),
            AttackRule(),
            EatRule(),
            RestRule(),
            SocializeRule(),
            HelpResidentRule(),
            RequestResourceRule(),
            ConfrontRule(),
            RepayObligationRule(),
        )
        self._rules = {rule.intent_type: rule for rule in registered}
        if len(self._rules) != len(registered):
            raise ValueError("duplicate intent rule registration")

    def process(
        self,
        timeline_id: str,
        intent: Intent,
        *,
        expected_sequence: int | None = None,
        state: WorldProjection | None = None,
    ) -> IntentProcessingResult:
        intent_id = intent.deterministic_id()
        rule = self._rules.get(intent.intent_type)
        active_state = state if state is not None else replay_world(self.store.read(timeline_id))
        context = ActionContext(timeline_id=timeline_id, state=active_state, resolver=self.resolver)

        if rule is None:
            issues = (ValidationIssue(code="unsupported_intent", message=f"no rule registered for intent type: {intent.intent_type}"),)
            committed = self._commit_rejection(timeline_id, intent, issues, expected_sequence)
            return IntentProcessingResult(intent_id=intent_id, accepted=False, committed_events=tuple(committed), issues=issues)

        validation = rule.validate(intent, context)
        if not validation.accepted:
            committed = self._commit_rejection(timeline_id, intent, validation.issues, expected_sequence)
            return IntentProcessingResult(intent_id=intent_id, accepted=False, committed_events=tuple(committed), issues=validation.issues)

        candidates = rule.resolve(intent, context)
        self._assert_event_batch(intent, candidates)
        committed = self.store.append_batch(timeline_id, candidates, expected_sequence=expected_sequence)
        return IntentProcessingResult(intent_id=intent_id, accepted=True, committed_events=tuple(committed))

    def _commit_rejection(self, timeline_id: str, intent: Intent, issues: tuple[ValidationIssue, ...], expected_sequence: int | None) -> list[Event]:
        intent_id = intent.deterministic_id()
        rejection = NewEvent(
            tick=intent.tick,
            phase="validation",
            event_type="intent.rejected",
            actor_id=intent.actor_id,
            subject_ids=tuple(subject for subject in (intent.actor_id, intent.target_id) if subject is not None),
            correlation_id=intent.correlation_id or intent_id,
            payload={"intent_id": intent_id, "intent_type": intent.intent_type, "issues": [issue.model_dump(mode="json") for issue in issues]},
        )
        return self.store.append_batch(timeline_id, [rejection], expected_sequence=expected_sequence)

    @staticmethod
    def _assert_event_batch(intent: Intent, events: list[NewEvent]) -> None:
        if not events:
            raise IntentPipelineError(f"rule emitted no events for accepted intent: {intent.intent_type}")
        if any(event.tick != intent.tick for event in events):
            raise IntentPipelineError("all resolved events must use the intent tick")
