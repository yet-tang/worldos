import pytest

from worldos_core import BaseWorldModule, ModuleContext, NewEvent, WorldModuleRegistry


class LaterModule(BaseWorldModule):
    name = "later"
    order = 20

    def before_actions(self, context: ModuleContext):
        return [NewEvent(tick=context.tick, phase="module", event_type="world.flag_set", payload={"name": "later", "value": True})]


class EarlierModule(BaseWorldModule):
    name = "earlier"
    order = 10

    def before_actions(self, context: ModuleContext):
        return [NewEvent(tick=context.tick, phase="module", event_type="world.flag_set", payload={"name": "earlier", "value": True})]


def context(tick=3):
    from worldos_core import WorldProjection
    return ModuleContext(timeline_id="main", tick=tick, world=WorldProjection(), history=())


def test_registry_orders_modules_and_tags_events():
    registry = WorldModuleRegistry((LaterModule(), EarlierModule()))
    events = registry.before_actions(context())
    assert [event.metadata["module"] for event in events] == ["earlier", "later"]
    assert all(event.metadata["module_hook"] == "before_actions" for event in events)


def test_duplicate_module_names_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        WorldModuleRegistry((EarlierModule(), EarlierModule()))


def test_modules_cannot_emit_events_for_another_tick():
    class InvalidModule(BaseWorldModule):
        name = "invalid"
        def before_actions(self, context: ModuleContext):
            return [NewEvent(tick=context.tick + 1, phase="module", event_type="world.flag_set")]

    with pytest.raises(ValueError, match="expected 3"):
        WorldModuleRegistry((InvalidModule(),)).before_actions(context())
