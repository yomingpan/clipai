from pathlib import Path
import pytest

from ClipAI.app.runtime_managed_update import ManagedUpdateRuntimeModule
from ClipAI.core.commands import CheckForManagedUpdate, ManagedUpdateCheckCompleted, ManagedUpdatePreparationProgress
from ClipAI.core.managed_install import ManagedUpdateClientIdentity
from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure
from ClipAI.core.update_catalog import ManagedUpdateRelease
from ClipAI.app.managed_update_handoff import ManagedUpdateHandoffExecutor
from ClipAI.services.managed_update_coordinator import ManagedUpdateCoordinator


class Supervisor:
    def __init__(self) -> None:
        self.work = {}
        self.errors = {}
        self.task_classes = {}

    def submit(self, task_id, work, on_error, *, task_class="interactive", cancellation_hook=None):
        self.work[task_id] = work
        self.errors[task_id] = on_error
        self.task_classes[task_id] = task_class


class Presenter:
    def __init__(self) -> None:
        self.states = []

    def set_managed_update(self, state) -> None:
        self.states.append(state)


class Executor:
    def __init__(self, result=None, error=None) -> None:
        self.result = result
        self.error = error
        self.calls = []
        self.preparation = None

    def execute(self, identity, transaction_id, *, preparation=None):
        self.preparation = preparation
        self.calls.append((identity, transaction_id))
        if self.error is not None:
            raise self.error
        return self.result


def _identity(tmp_path: Path) -> ManagedUpdateClientIdentity:
    return ManagedUpdateClientIdentity(
        "3.7.3",
        "3.7.3",
        (tmp_path / "python.exe").resolve(),
        123,
        (tmp_path / "install").resolve(),
        (tmp_path / "shared").resolve(),
        "managed-1",
    )


def _module(tmp_path, *, result=None, error=None, identity=True):
    supervisor = Supervisor()
    presenter = Presenter()
    commands = []
    executor = Executor(result=result, error=error)
    module = ManagedUpdateRuntimeModule(
        executor=executor if identity else None,
        identity=_identity(tmp_path) if identity else None,
        supervisor=supervisor,
        enqueue=commands.append,
        presenter=presenter,
        transaction_id_factory=lambda: "update-operation-1",
    )
    return module, executor, supervisor, presenter, commands


def test_about_update_intent_runs_existing_handoff_on_maintenance_capacity(tmp_path) -> None:
    module, executor, supervisor, presenter, commands = _module(tmp_path)

    module.handle(CheckForManagedUpdate("operation-1"))

    assert presenter.states[-1].phase == "checking"
    assert supervisor.task_classes["managed-update:operation-1"] == "maintenance"
    supervisor.work["managed-update:operation-1"]()
    assert executor.calls == [(_identity(tmp_path), "update-operation-1")]
    assert commands == [ManagedUpdateCheckCompleted("operation-1", "up_to_date")]

    module.handle(commands.pop())
    assert presenter.states[-1].phase == "up_to_date"


def test_update_failure_is_typed_and_retryable(tmp_path) -> None:
    module, _executor, supervisor, presenter, commands = _module(
        tmp_path,
        error=ManagedUpdateFailure(FailureCode.CATALOG_UNAVAILABLE, "offline"),
    )
    module.handle(CheckForManagedUpdate("operation-1"))
    supervisor.work["managed-update:operation-1"]()

    assert commands == [
        ManagedUpdateCheckCompleted(
            "operation-1", "failed", FailureCode.CATALOG_UNAVAILABLE
        )
    ]
    module.handle(commands.pop())
    assert presenter.states[-1].phase == "failed"
    assert presenter.states[-1].failure_code is FailureCode.CATALOG_UNAVAILABLE
    assert presenter.states[-1].enabled is True


def test_source_install_stays_unavailable_and_never_creates_work(tmp_path) -> None:
    module, executor, supervisor, presenter, _commands = _module(
        tmp_path, identity=False
    )

    module.project()
    module.handle(CheckForManagedUpdate("operation-1"))

    assert presenter.states[-1].phase == "unavailable"
    assert presenter.states[-1].enabled is False
    assert supervisor.work == {}
    assert executor.calls == []


def test_duplicate_or_stale_operation_cannot_replace_active_projection(tmp_path) -> None:
    module, _executor, _supervisor, presenter, _commands = _module(tmp_path)
    module.handle(CheckForManagedUpdate("operation-1"))
    module.handle(CheckForManagedUpdate("operation-2"))
    module.handle(ManagedUpdateCheckCompleted("stale", "up_to_date"))

    assert [state.phase for state in presenter.states] == ["checking"]


def test_progress_is_operation_scoped_and_cannot_regress_or_follow_completion(tmp_path):
    module, _executor, _supervisor, presenter, _commands = _module(tmp_path)
    module.handle(CheckForManagedUpdate("one"))
    module.handle(ManagedUpdatePreparationProgress("stale", "downloading"))
    module.handle(ManagedUpdatePreparationProgress("one", "downloading"))
    module.handle(ManagedUpdatePreparationProgress("one", "preparing"))
    module.handle(ManagedUpdatePreparationProgress("one", "downloading"))
    module.handle(ManagedUpdateCheckCompleted("one", "failed", FailureCode.DOWNLOAD_FAILED))
    module.handle(CheckForManagedUpdate("two"))
    module.handle(ManagedUpdatePreparationProgress("one", "preparing"))
    assert [state.phase for state in presenter.states] == [
        "checking", "downloading", "preparing", "failed", "checking"
    ]


def test_runtime_stop_signals_only_owned_preparation_and_ignores_late_ack(tmp_path):
    module, executor, supervisor, presenter, commands = _module(tmp_path)
    module.handle(CheckForManagedUpdate("one"))
    supervisor.work["managed-update:one"]()
    assert not executor.preparation.cancellation.is_cancelled
    module.stop()
    assert executor.preparation.cancellation.is_cancelled
    module.handle(commands.pop())
    module.handle(CheckForManagedUpdate("two"))
    assert [state.phase for state in presenter.states] == ["checking"]


@pytest.mark.parametrize("download_fails", [False, True])
def test_real_preparation_pipeline_projects_download_then_handoff_on_ui_queue(tmp_path, download_fails):
    commands, events = [], []
    supervisor, presenter = Supervisor(), Presenter()
    def pump():
        while commands:
            module.handle(commands.pop(0))
    class Source:
        def discover(self, **_kwargs):
            return ManagedUpdateRelease("3.7.4", "https://updates.example/bundle.zip",
                "a" * 64, 42, "b" * 64, "release-key", "3.7.3")
        def download(self, _release, **_kwargs):
            pump()
            assert module.state.phase == "downloading"
            events.append("download")
            if download_fails:
                raise ManagedUpdateFailure(FailureCode.DOWNLOAD_FAILED, "stream failed")
            return (tmp_path / "bundle.zip").resolve()
    class Handoff:
        def prepare(self, _request):
            pump()
            assert module.state.phase == "preparing"
            events.append("handoff")
            return object()
    executor = ManagedUpdateHandoffExecutor(
        coordinator=ManagedUpdateCoordinator(release_source=Source(), now=lambda: "2026-10-05T00:00:00Z"),
        handoff=Handoff(), request_shutdown=lambda: events.append("shutdown"),
    )
    module = ManagedUpdateRuntimeModule(
        executor=executor, identity=_identity(tmp_path), supervisor=supervisor,
        enqueue=commands.append, presenter=presenter, transaction_id_factory=lambda: "update-one",
    )
    module.handle(CheckForManagedUpdate("one"))
    supervisor.work["managed-update:one"]()
    pump()
    if download_fails:
        assert events == ["download"]
        assert module.state.phase == "failed"
        assert module.state.enabled
    else:
        assert events == ["download", "handoff", "shutdown"]
        assert module.state.phase == "restarting"
