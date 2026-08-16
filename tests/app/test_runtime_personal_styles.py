from __future__ import annotations

from ClipAI.app.runtime_personal_styles import PersonalStyleRuntimeModule
from ClipAI.core.commands import ImportPersonalStyle, OpenPersonalStyles, PersonalStyleOperationCompleted
from ClipAI.core.models import PersonalStyleCollection
from ClipAI.services.personal_styles import PersonalStyleCoordinator


class Store:
    def __init__(self) -> None:
        self.collection = PersonalStyleCollection()

    def load(self):
        return self.collection

    def save(self, collection):
        self.collection = collection


class Reader:
    def read_text(self, _path):
        return "只改怎麼說。"


class Supervisor:
    def __init__(self, error=None) -> None:
        self.error = error
        self.work = None

    def submit(self, _task_id, work, _on_error, **_kwargs):
        if self.error is not None:
            raise self.error
        self.work = work


class Presenter:
    def __init__(self) -> None:
        self.states = []

    def show_personal_styles(self, state):
        self.states.append(state)

    def set_personal_styles(self, state):
        self.states.append(state)

    def close_personal_styles(self):
        pass


def test_runtime_projects_pending_then_actual_persistence_completion() -> None:
    queued = []
    supervisor = Supervisor()
    presenter = Presenter()
    module = PersonalStyleRuntimeModule(
        coordinator=PersonalStyleCoordinator(Store(), Reader()),
        supervisor=supervisor,
        enqueue=queued.append,
        presenter=presenter,
    )
    module.handle(OpenPersonalStyles())

    module.handle(ImportPersonalStyle("Yoming.md", "import-1"))

    assert presenter.states[-1].operation_state == "pending"
    assert supervisor.work is not None
    supervisor.work()
    assert isinstance(queued[-1], PersonalStyleOperationCompleted)
    module.handle(queued.pop())
    assert presenter.states[-1].operation_state == "succeeded"
    assert presenter.states[-1].profiles[0].name == "Yoming"


def test_runtime_submit_failure_settles_pending_state_immediately() -> None:
    presenter = Presenter()
    module = PersonalStyleRuntimeModule(
        coordinator=PersonalStyleCoordinator(Store(), Reader()),
        supervisor=Supervisor(RuntimeError("closed")),
        enqueue=lambda _command: None,
        presenter=presenter,
    )
    module.handle(OpenPersonalStyles())

    module.handle(ImportPersonalStyle("Yoming.md", "import-1"))

    assert presenter.states[-1].operation_state == "failed"
    assert "previous selection remains active" in presenter.states[-1].message
