from __future__ import annotations

from collections.abc import Callable

from ClipAI.app.config import AppConfig, load_action_catalog
from ClipAI.core.provider import ProviderRequest
from ClipAI.providers.fake import FakeProvider
from ClipAI.services.vertical_slice import VerticalSliceWorkflow


class FakeClipboard:
    def __init__(self, text: str) -> None:
        self.text = text
        self.writes: list[str] = []

    def read_text(self) -> str:
        return self.text

    def write_text(self, text: str) -> None:
        self.writes.append(text)


class RecordingProvider:
    def __init__(self, result: str = "provider result") -> None:
        self.result = result
        self.requests: list[ProviderRequest] = []

    def complete(self, request: ProviderRequest) -> str:
        self.requests.append(request)
        return self.result


class FailingProvider:
    def complete(self, request: ProviderRequest) -> str:
        raise RuntimeError("provider boom")


class RecordingPresenter:
    instances: list["RecordingPresenter"] = []

    def __init__(self) -> None:
        self.loading: dict[str, str] | None = None
        self.result = ""
        self.error = ""
        self.copy_callback: Callable[[], None] | None = None
        self.ran = False
        RecordingPresenter.instances.append(self)

    def show_loading(self, *, title: str, source_preview: str, model: str) -> None:
        self.loading = {"title": title, "source_preview": source_preview, "model": model}

    def show_result(self, text: str) -> None:
        self.result = text

    def show_error(self, message: str) -> None:
        self.error = message

    def set_copy_action(self, callback: Callable[[], None] | None) -> None:
        self.copy_callback = callback

    def run(self) -> None:
        self.ran = True


def setup_function() -> None:
    RecordingPresenter.instances.clear()


def make_workflow(clipboard: FakeClipboard, provider) -> VerticalSliceWorkflow:
    return VerticalSliceWorkflow(
        app_config=AppConfig(default_model="fake-model", temperature=0.2),
        actions=load_action_catalog("config/actions.yaml"),
        clipboard=clipboard,
        provider=provider,
        presenter_factory=RecordingPresenter,
    )


def test_missing_clipboard_text_shows_error_state() -> None:
    workflow = make_workflow(FakeClipboard("   "), RecordingProvider())

    outcome = workflow.run("english_companion", "short")
    presenter = RecordingPresenter.instances[0]

    assert outcome.status == "error"
    assert "Clipboard is empty" in presenter.error
    assert presenter.copy_callback is None
    assert presenter.ran is True


def test_fake_provider_result_updates_dialog_presenter_model() -> None:
    workflow = make_workflow(FakeClipboard("appetizer"), FakeProvider())

    outcome = workflow.run("english_companion", "short")
    presenter = RecordingPresenter.instances[0]

    assert outcome.status == "success"
    assert presenter.loading == {
        "title": "English Companion",
        "source_preview": "Clipboard: appetizer",
        "model": "fake-model",
    }
    assert "Phase 3 Fake Result" in presenter.result


def test_copy_action_writes_result_to_clipboard() -> None:
    clipboard = FakeClipboard("appetizer")
    workflow = make_workflow(clipboard, RecordingProvider("copied result"))

    workflow.run("english_companion", "short")
    presenter = RecordingPresenter.instances[0]
    assert presenter.copy_callback is not None

    presenter.copy_callback()

    assert clipboard.writes == ["copied result"]


def test_provider_error_shows_dialog_error_state() -> None:
    workflow = make_workflow(FakeClipboard("appetizer"), FailingProvider())

    outcome = workflow.run("english_companion", "short")
    presenter = RecordingPresenter.instances[0]

    assert outcome.status == "error"
    assert "Provider failed: provider boom" == presenter.error
    assert presenter.copy_callback is None
    assert presenter.ran is True
