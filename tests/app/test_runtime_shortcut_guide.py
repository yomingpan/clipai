from ClipAI.app.runtime_shortcut_guide import ShortcutGuideRuntimeModule
from ClipAI.core.commands import CloseShortcutGuide, InterruptionRequested, OpenShortcutGuide, SelectShortcutGuideItem, ShortcutKeyStateChanged, ShortcutPressInvoked, ShortcutPressStarted
from ClipAI.core.models import ActionDefinition, ShortcutDefinition, ShortcutPressId
from ClipAI.platform.hotkey import create_hotkey_dispatcher
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.shortcut_catalog import ShortcutCatalog
from ClipAI.services.shortcut_guide import ShortcutGuideCatalog, ShortcutGuideCoordinator
from tests.app.test_runtime import make_runtime


class GuidePresenter:
    def __init__(self) -> None:
        self.shown = []
        self.updated = []
        self.closed = 0

    def show_shortcut_guide(self, snapshot) -> None:
        self.shown.append(snapshot)

    def set_shortcut_guide(self, snapshot) -> None:
        self.updated.append(snapshot)

    def close_shortcut_guide(self) -> None:
        self.closed += 1


class Key:
    def __init__(self, *, name=None, char=None) -> None:
        self.name = name
        self.char = char


def guide_module() -> tuple[ShortcutGuideRuntimeModule, GuidePresenter]:
    presenter = GuidePresenter()
    shortcuts = ShortcutCatalog([
        ShortcutDefinition("a", "ctrl+alt+8", "start_action", "a"),
    ])
    actions = ActionCatalog([
        ActionDefinition("a", "English Companion", "system", "{input}", {}),
    ])
    module = ShortcutGuideRuntimeModule(
        catalog=ShortcutGuideCatalog(shortcuts, actions, modifier_mode="ctrl_alt"),
        coordinator=ShortcutGuideCoordinator(),
        presenter=presenter,
    )
    return module, presenter


def test_runtime_module_projects_open_select_key_state_and_close() -> None:
    module, presenter = guide_module()

    module.handle(OpenShortcutGuide("guide-1"))
    module.handle(SelectShortcutGuideItem("a"))
    module.consume(ShortcutKeyStateChanged(frozenset({"ctrl"})))
    module.handle(CloseShortcutGuide("guide-1"))

    assert len(presenter.shown) == 1
    assert len(presenter.updated) == 2
    assert presenter.closed == 1


def test_runtime_module_consumes_trigger_and_projects_verification() -> None:
    module, presenter = guide_module()
    module.handle(OpenShortcutGuide("guide-1"))
    press_id = ShortcutPressId(5)
    module.consume(ShortcutPressStarted(press_id, "a"))

    consumed = module.consume(ShortcutPressInvoked(press_id, "a", "short"))

    assert consumed is True
    assert presenter.updated[-1].verified == frozenset({("a", "short")})


def test_app_runtime_routes_shortcut_to_open_guide_before_workflow() -> None:
    runtime, view, _supervisor, _outputs, _listener = make_runtime()
    module, _presenter = guide_module()
    module.handle(OpenShortcutGuide("guide-1"))
    runtime._shortcut_guide_module = module
    press_id = ShortcutPressId(5)

    runtime.enqueue(ShortcutPressStarted(press_id, "a"))
    runtime.enqueue(ShortcutPressInvoked(press_id, "a", "short"))
    runtime.drain_commands()

    assert view.snapshots == []


def test_app_runtime_cancels_pending_sequence_when_guide_opens() -> None:
    runtime, _view, _supervisor, _outputs, _listener = make_runtime()
    module, _presenter = guide_module()
    runtime._shortcut_guide_module = module
    cancelled = []
    runtime._workflow_module.cancel_shortcut_sequence = lambda: cancelled.append(True)

    runtime.enqueue(OpenShortcutGuide("guide-1"))
    runtime.drain_commands()

    assert cancelled == [True]


def test_short_escape_closes_only_the_focused_guide() -> None:
    runtime, _view, _supervisor, _outputs, _listener = make_runtime()
    module, presenter = guide_module()
    runtime._shortcut_guide_module = module

    runtime.enqueue(OpenShortcutGuide("guide-1"))
    runtime.enqueue(InterruptionRequested("current"))
    runtime.drain_commands()

    assert module.is_open is False
    assert presenter.closed == 1


def test_new_press_after_guide_closes_runs_while_modifiers_remain_held() -> None:
    runtime, view, _supervisor, _outputs, _listener = make_runtime()
    module, _presenter = guide_module()
    runtime._shortcut_guide_module = module
    dispatcher = create_hotkey_dispatcher(
        {"a": {"hotkey": "ctrl+alt+8"}},
        runtime.enqueue,
        modifier_mode="ctrl_alt",
    )
    runtime._listener = dispatcher

    runtime.enqueue(OpenShortcutGuide("guide-1"))
    runtime.drain_commands()
    dispatcher.on_press(Key(name="ctrl_l"))
    dispatcher.on_press(Key(name="alt_l"))
    dispatcher.on_press(Key(char="8"))
    dispatcher.on_release(Key(char="8"))
    runtime.drain_commands()

    runtime.enqueue(CloseShortcutGuide("guide-1"))
    runtime.drain_commands()
    dispatcher.on_press(Key(char="8"))
    dispatcher.on_release(Key(char="8"))
    runtime.drain_commands()

    assert view.snapshots
