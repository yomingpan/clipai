from ClipAI.app.runtime_shortcut_guide import ShortcutGuideRuntimeModule
from ClipAI.core.commands import CancelActiveOperations, CloseShortcutGuide, OpenShortcutGuide, SelectShortcutGuideItem, ShortcutGestureProgressed, ShortcutTriggered
from ClipAI.core.models import ActionDefinition, ShortcutDefinition
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


def guide_module() -> tuple[ShortcutGuideRuntimeModule, GuidePresenter]:
    presenter = GuidePresenter()
    shortcuts = ShortcutCatalog([
        ShortcutDefinition("english", "ctrl+alt+8", "start_action", "english"),
    ])
    actions = ActionCatalog([
        ActionDefinition("english", "English Companion", "system", "{input}", {}),
    ])
    module = ShortcutGuideRuntimeModule(
        catalog=ShortcutGuideCatalog(shortcuts, actions, modifier_mode="ctrl_alt"),
        coordinator=ShortcutGuideCoordinator(),
        presenter=presenter,
    )
    return module, presenter


def test_runtime_module_projects_open_select_progress_and_close() -> None:
    module, presenter = guide_module()

    module.handle(OpenShortcutGuide("guide-1"))
    module.handle(SelectShortcutGuideItem("english"))
    module.handle(ShortcutGestureProgressed(2, frozenset({"ctrl"})))
    module.handle(CloseShortcutGuide("guide-1"))

    assert len(presenter.shown) == 1
    assert len(presenter.updated) == 2
    assert presenter.closed == 1


def test_runtime_module_consumes_trigger_and_projects_verification() -> None:
    module, presenter = guide_module()
    module.handle(OpenShortcutGuide("guide-1"))

    consumed = module.consume(ShortcutTriggered("english", "short", 5))

    assert consumed is True
    assert presenter.updated[-1].verified == frozenset({("english", "short")})


def test_app_runtime_routes_shortcut_to_open_guide_before_workflow() -> None:
    runtime, view, _supervisor, _outputs, _listener = make_runtime()
    module, _presenter = guide_module()
    module.handle(OpenShortcutGuide("guide-1"))
    runtime._shortcut_guide_module = module

    runtime.enqueue(ShortcutTriggered("english", "short", 5))
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


def test_app_runtime_does_not_queue_key_progress_while_guide_is_closed() -> None:
    runtime, _view, _supervisor, _outputs, _listener = make_runtime()
    module, _presenter = guide_module()
    runtime._shortcut_guide_module = module

    runtime._enqueue_shortcut_progress(3, frozenset({"a"}), False)

    assert runtime._commands.empty()


def test_escape_keeps_guide_open_and_routes_global_cancel() -> None:
    runtime, _view, _supervisor, _outputs, _listener = make_runtime()
    module, presenter = guide_module()
    module.handle(OpenShortcutGuide("guide-1"))
    runtime._shortcut_guide_module = module
    cancellations: list[CancelActiveOperations] = []
    runtime._cancel_active_operations = cancellations.append

    runtime.enqueue(ShortcutTriggered("", "cancel", 7))
    runtime.drain_commands()

    assert module.is_open is True
    assert presenter.closed == 0
    assert cancellations == [CancelActiveOperations()]
