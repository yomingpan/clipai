from ClipAI.app.runtime_action_language import ActionLanguageRuntimeModule
from ClipAI.core.commands import (
    ActionLanguagePackSelectionCompleted,
    SelectActionLanguagePack,
)
from ClipAI.core.models import (
    ActionLanguagePackDescriptor,
    ActionLanguagePackIdentity,
    ActionLanguagePackSelectionState,
)
from ClipAI.services.action_language_selection import (
    ActionLanguageSelectionCoordinator,
)


class Backend:
    def __init__(self, error=None) -> None:
        self.error = error
        self.calls = []

    def validate_and_save(self, pack_id):
        self.calls.append(pack_id)
        return self.error


class Supervisor:
    def __init__(self) -> None:
        self.work = {}
        self.task_classes = {}
        self.errors = {}

    def submit(self, task_id, work, on_error, *, task_class="interactive"):
        self.work[task_id] = work
        self.errors[task_id] = on_error
        self.task_classes[task_id] = task_class


class Presenter:
    def __init__(self) -> None:
        self.states = []

    def set_action_language_selection(self, state) -> None:
        self.states.append(state)


def _state() -> ActionLanguagePackSelectionState:
    zh = ActionLanguagePackIdentity("zh-TW", "1.0.0", "zh-TW")
    ja = ActionLanguagePackIdentity("ja-JP", "1.0.0", "ja-JP")
    return ActionLanguagePackSelectionState(
        (
            ActionLanguagePackDescriptor(zh, "繁體中文"),
            ActionLanguagePackDescriptor(ja, "日本語"),
        ),
        zh,
        "zh-TW",
    )


def _module(error=None):
    backend = Backend(error)
    supervisor = Supervisor()
    presenter = Presenter()
    commands = []
    module = ActionLanguageRuntimeModule(
        coordinator=ActionLanguageSelectionCoordinator(_state()),
        backend=backend,
        supervisor=supervisor,
        enqueue=commands.append,
        presenter=presenter,
    )
    return module, backend, supervisor, presenter, commands


def test_selection_revalidates_and_saves_on_maintenance_capacity() -> None:
    module, backend, supervisor, presenter, commands = _module()

    module.handle(SelectActionLanguagePack("ja-JP", "operation-1"))

    assert presenter.states[-1].pending_pack_id == "ja-JP"
    assert presenter.states[-1].selected_pack_id == "zh-TW"
    assert supervisor.task_classes["action-language:operation-1"] == "maintenance"
    supervisor.work["action-language:operation-1"]()
    assert backend.calls == ["ja-JP"]
    assert commands == [
        ActionLanguagePackSelectionCompleted("operation-1", "ja-JP")
    ]

    module.handle(commands.pop())
    assert presenter.states[-1].selected_pack_id == "ja-JP"
    assert presenter.states[-1].active_pack.pack_id == "zh-TW"
    assert presenter.states[-1].restart_required is True


def test_validation_failure_preserves_checked_selection() -> None:
    module, _backend, supervisor, presenter, commands = _module(
        "checksum_mismatch"
    )
    module.handle(SelectActionLanguagePack("ja-JP", "operation-1"))
    supervisor.work["action-language:operation-1"]()

    module.handle(commands.pop())

    assert presenter.states[-1].selected_pack_id == "zh-TW"
    assert presenter.states[-1].pending_pack_id is None


def test_unexpected_worker_failure_returns_typed_save_failure() -> None:
    module, _backend, supervisor, _presenter, commands = _module()
    module.handle(SelectActionLanguagePack("ja-JP", "operation-1"))

    supervisor.errors["action-language:operation-1"](RuntimeError("boom"))

    assert commands == [
        ActionLanguagePackSelectionCompleted(
            "operation-1",
            "ja-JP",
            "selection_save_failed",
        )
    ]
