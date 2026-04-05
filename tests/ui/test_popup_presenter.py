from __future__ import annotations

from clipai.core.constants import EVENT_TTS_STATE
from clipai.core.event_bus import EventBus
from clipai.services.popup_session import PopupSession
from clipai.ui.popup_presenter import PopupPresenter
from clipai.ui.result_popup.action_handler import PopupActionHandler
from clipai.ui.result_popup.markdown_renderer import PopupMarkdownRenderer


class _FakeTextWidget:
    def __init__(self, bg: str = "#ffffff", selection: str = "") -> None:
        self._bg = bg
        self._selection = selection
        self.inserted: list[tuple[str, tuple[str, ...]]] = []
        self.config_calls: list[dict[str, object]] = []
        self.tags: dict[str, dict[str, object]] = {}

    def config(self, **kwargs) -> None:
        self.config_calls.append(kwargs)

    def delete(self, start: str, end: str) -> None:
        del start, end
        self.inserted.clear()

    def tag_configure(self, name: str, **kwargs) -> None:
        self.tags[name] = kwargs

    def insert(self, index: str, text: str, tags=()) -> None:
        del index
        if isinstance(tags, str):
            tags = (tags,)
        self.inserted.append((text, tuple(tags)))

    def cget(self, key: str) -> str:
        if key == "bg":
            return self._bg
        return ""

    def get(self, start: str, end: str) -> str:
        if start == "sel.first" and end == "sel.last":
            return self._selection
        return "".join(text for text, _ in self.inserted)

    def tag_remove(self, tag: str, start: str, end: str) -> None:
        del tag, start, end

    def mark_set(self, mark: str, value: str) -> None:
        del mark, value


class _FakeLabel:
    def __init__(self) -> None:
        self.text = None

    def configure(self, **kwargs) -> None:
        self.text = kwargs.get("text")


class _FakeWindow:
    def __init__(self) -> None:
        self.title_text = None

    def title(self, value: str) -> None:
        self.title_text = value


class _FakeClipboard:
    def __init__(self) -> None:
        self.payload = None

    def write(self, text: str) -> None:
        self.payload = text


class _FakeArchiveService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def append_text(self, session: PopupSession, text: str) -> None:
        self.calls.append((session.session_id, text))


class _FakeTTSService:
    def __init__(self, speaking: bool = False) -> None:
        self._speaking = speaking
        self.spoken: list[str] = []
        self.stop_calls = 0

    def is_speaking(self) -> bool:
        return self._speaking

    def speak_async(self, text: str) -> None:
        self._speaking = True
        self.spoken.append(text)

    def stop(self) -> bool:
        self._speaking = False
        self.stop_calls += 1
        return True


def test_speak_phase_to_ui_state_is_phase_aware() -> None:
    assert PopupPresenter._speak_phase_to_ui_state("start", True) is True
    assert PopupPresenter._speak_phase_to_ui_state("stop", False) is False
    assert PopupPresenter._speak_phase_to_ui_state("end", False) is False
    assert PopupPresenter._speak_phase_to_ui_state("error", False) is False
    assert PopupPresenter._speak_phase_to_ui_state("", True) is True
    assert PopupPresenter._speak_phase_to_ui_state("", False) is None


def test_popup_markdown_renderer_formats_loading_states() -> None:
    session = PopupSession(
        action_id="summarize_next_steps",
        action_name="Summary",
        original_input="",
        latest_result="",
        input_loading=True,
        result_loading=True,
    )

    assert PopupMarkdownRenderer.input_preview_for_session(session) == "Analysis: Connecting..."
    assert PopupMarkdownRenderer.result_text_for_session(session) == "Connecting..."

    session.mark_input_ready("hello world")
    session.mark_result_ready("final answer")

    assert PopupMarkdownRenderer.input_preview_for_session(session) == "Analysis: hello world"
    assert PopupMarkdownRenderer.result_text_for_session(session) == "final answer"


def test_popup_markdown_renderer_renders_common_markdown_patterns() -> None:
    widget = _FakeTextWidget(bg="#141922")
    session = PopupSession(
        action_id="summarize_next_steps",
        action_name="Summary",
        original_input="hello",
        latest_result="### Title\n- item\n> quote\n**bold** and `code`",
    )

    PopupMarkdownRenderer.render_session_text(widget, session)

    inserted_tags = [tags for _, tags in widget.inserted]
    assert ("md_h3",) in inserted_tags
    assert ("body", "md_quote") in inserted_tags
    assert ("body", "md_bold") in inserted_tags
    assert ("body", "md_code") in inserted_tags
    assert widget.tags["md_code"]["background"] == "#2C3442"
    assert widget.tags["md_code"]["foreground"] == "#F7FAFF"


def test_popup_action_handler_prefers_selection_to_full_output() -> None:
    clipboard = _FakeClipboard()
    archive_service = _FakeArchiveService()
    handler = PopupActionHandler(
        archive_service=archive_service,
        clipboard_writer=clipboard.write,
    )
    session = PopupSession(
        action_id="summarize",
        action_name="Summarize",
        original_input="Original",
        latest_result="Full result",
    )
    widget = _FakeTextWidget(selection="Selected result")

    handler.copy_output(widget, session)
    handler.archive_output(widget, session)

    assert clipboard.payload == "Selected result"
    assert archive_service.calls == [(session.session_id, "Selected result")]


def test_popup_action_handler_toggle_speak_updates_tts() -> None:
    tts_service = _FakeTTSService(speaking=False)
    handler = PopupActionHandler(tts_service=tts_service)
    session = PopupSession(
        action_id="summarize",
        action_name="Summarize",
        original_input="Original",
        latest_result="Full result",
    )

    assert handler.toggle_speak(None, session) is True
    assert tts_service.spoken == ["Full result"]

    assert handler.toggle_speak(None, session) is False
    assert tts_service.stop_calls == 1


def test_popup_presenter_refresh_session_repaints_input_preview_from_session_state() -> None:
    presenter = PopupPresenter()
    presenter._input_label = _FakeLabel()
    presenter._text_widget = None
    presenter._follow_entry = None
    presenter._follow_hint_label = None

    first = PopupSession(
        action_id="first",
        action_name="First",
        original_input="",
        latest_result="",
        input_loading=True,
        result_loading=True,
    )
    first.mark_input_ready("first input")
    presenter._active_session = first
    presenter._refresh_session_on_ui(first.session_id)
    assert presenter._input_label.text == "Analysis: first input"

    second = PopupSession(
        action_id="second",
        action_name="Second",
        original_input="second input",
        latest_result="done",
        input_loading=False,
        result_loading=False,
    )
    presenter._active_session = second
    presenter._refresh_session_on_ui(second.session_id)
    assert presenter._input_label.text == "Analysis: second input"
    presenter.dispose()


def test_popup_presenter_refresh_session_updates_header_title() -> None:
    presenter = PopupPresenter()
    presenter._title_label = _FakeLabel()
    presenter._active_window = _FakeWindow()
    presenter._input_label = None
    presenter._text_widget = None
    presenter._follow_entry = None
    presenter._follow_hint_label = None

    session = PopupSession(
        action_id="translate_en",
        action_name="Translate EN",
        original_input="hello",
        latest_result="world",
        input_loading=False,
        result_loading=False,
    )
    presenter._active_session = session

    presenter._refresh_session_on_ui(session.session_id)

    assert presenter._title_label.text == "ClipAI - Translate EN"
    assert presenter._active_window.title_text == "ClipAI - Translate EN"
    presenter.dispose()


def test_popup_presenter_dispose_unsubscribes_tts_subscription() -> None:
    bus = EventBus()
    presenter = PopupPresenter(event_bus=bus)

    assert len(bus._subs_by_event[EVENT_TTS_STATE]) == 1

    presenter.dispose()

    assert len(bus._subs_by_event[EVENT_TTS_STATE]) == 0
