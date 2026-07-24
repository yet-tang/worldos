from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from .events import Event, NewEvent
from .world import WorldProjection


@dataclass(frozen=True)
class ModuleContext:
    timeline_id: str
    tick: int
    world: WorldProjection
    history: tuple[Event, ...]


class WorldModule(Protocol):
    """Deterministic world subsystem invoked by the authoritative tick engine."""

    @property
    def name(self) -> str: ...

    @property
    def order(self) -> int: ...

    def before_actions(self, context: ModuleContext) -> Sequence[NewEvent]: ...

    def after_actions(self, context: ModuleContext, action_events: tuple[Event, ...]) -> Sequence[NewEvent]: ...


class BaseWorldModule:
    """Convenience base class for modules that implement only one hook."""

    name = "base"
    order = 100

    def before_actions(self, context: ModuleContext) -> Sequence[NewEvent]:
        return ()

    def after_actions(self, context: ModuleContext, action_events: tuple[Event, ...]) -> Sequence[NewEvent]:
        return ()


class WorldModuleRegistry:
    def __init__(self, modules: Sequence[WorldModule] = ()) -> None:
        names = [module.name for module in modules]
        if len(names) != len(set(names)):
            raise ValueError("world module names must be unique")
        self._modules = tuple(sorted(modules, key=lambda module: (module.order, module.name)))

    @property
    def modules(self) -> tuple[WorldModule, ...]:
        return self._modules

    def before_actions(self, context: ModuleContext) -> list[NewEvent]:
        return self._run("before_actions", context)

    def after_actions(self, context: ModuleContext, action_events: tuple[Event, ...]) -> list[NewEvent]:
        candidates: list[NewEvent] = []
        for module in self._modules:
            produced = module.after_actions(context, action_events)
            candidates.extend(self._normalize(module, "after_actions", produced, context.tick))
        return candidates

    def _run(self, hook: str, context: ModuleContext) -> list[NewEvent]:
        candidates: list[NewEvent] = []
        for module in self._modules:
            produced = getattr(module, hook)(context)
            candidates.extend(self._normalize(module, hook, produced, context.tick))
        return candidates

    @staticmethod
    def _normalize(module: WorldModule, hook: str, events: Sequence[NewEvent], tick: int) -> list[NewEvent]:
        normalized: list[NewEvent] = []
        for event in events:
            if event.tick != tick:
                raise ValueError(f"module {module.name} emitted event for tick {event.tick}, expected {tick}")
            metadata = dict(event.metadata)
            metadata.setdefault("module", module.name)
            metadata.setdefault("module_hook", hook)
            normalized.append(event.model_copy(update={"metadata": metadata}))
        return normalized
