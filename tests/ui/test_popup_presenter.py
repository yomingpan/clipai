from __future__ import annotations

from clipai.core.constants import EVENT_TTS_STATE
from clipai.core.event_bus import EventBus
from clipai.services.popup_session import PopupSession
from clipai.ui.popup_presenter import ICON_ARCHIVE, ICON_COPY, PopupPresenter
from clipai.ui.result_popup.action_handler import PopupActionHandler
from clipai.ui.result_popup.markdown_renderer import PopupMarkdownRenderer


class _FakeTextWidget:
    def __init__(self, bg: str = "#ffffff", selection: str = "") -> None:
        self._bg = bg
        self._selection = selection
        self.inserted: list[tuple[str, tuple[str, ...]]] = []
        self.config_calls: list[dict[str, object]] = []
        self.tags: dict[str, dict[str, object]] = {}
        self.see_calls: list[str] = []

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

    def yview(self) -> tuple[float, float]:
        return (0.0, 1.0)

    def see(self, index: str) -> None:
        self.see_calls.append(index)


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

    def winfo_exists(self) -> bool:
        return True


class _FakePackFrame:
    def __init__(self) -> None:
        self.pack_calls: list[dict[str, object]] = []
        self.forget_calls = 0

    def pack(self, **kwargs) -> None:
        self.pack_calls.append(kwargs)

    def pack_forget(self) -> None:
        self.forget_calls += 1


class _FakeEntry:
    def __init__(self) -> None:
        self.focus_calls = 0
        self.deleted = False
        self.state = "normal"

    def focus_set(self) -> None:
        self.focus_calls += 1

    def cget(self, key: str) -> str:
        if key == "state":
            return self.state
        return ""

    def configure(self, **kwargs) -> None:
        if "state" in kwargs:
            self.state = str(kwargs["state"])

    def delete(self, start, end) -> None:
        del start, end
        self.deleted = True


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
    assert PopupPresenter._speak_phase_to_ui_state("requesting", True) is True
    assert PopupPresenter._speak_phase_to_ui_state("buffering", True) is True
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


def test_popup_markdown_renderer_normalizes_spacing() -> None:
    content = "\n\n## 重點\n\n\n- 第一點\n\n- 第二點"
    assert PopupMarkdownRenderer.normalize_content(content) == "## 重點\n- 第一點\n- 第二點"


def test_popup_markdown_renderer_uses_high_contrast_dark_palette() -> None:
    widget = _FakeTextWidget(bg="#141922")
    session = PopupSession(
        action_id="summarize_next_steps",
        action_name="Summary",
        original_input="hello",
        latest_result="## 重點\n- 這是主內容",
    )
    session.start_round(kind="follow_up", prompt_text="再說明一次", model="gemini")
    session.mark_result_ready("## 注意\n- 補充說明")

    PopupMarkdownRenderer.render_session_text(widget, session)

    inserted_tags = [tags for _, tags in widget.inserted]
    inserted_text = [text for text, _ in widget.inserted]
    assert ("body_heading",) in inserted_tags
    assert ("body_list_text",) in inserted_tags
    assert ("history_label",) in inserted_tags
    assert ("history_heading",) in inserted_tags
    assert widget.tags["body_heading"]["foreground"] == "#AFCBFF"
    assert widget.tags["history_heading"]["foreground"] == "#C3CDD9"
    assert widget.tags["history_code"]["foreground"] == "#C3CDD9"
    assert widget.tags["body_list_marker"]["foreground"] == "#C9DAF7"
    assert "• " in inserted_text


def test_popup_markdown_renderer_source_label_uses_provider_and_model() -> None:
    session = PopupSession(
        action_id="summarize",
        action_name="Summarize",
        original_input="Original",
        latest_result="Full result",
        current_provider="gemini",
        current_model="gemini-3.1-flash-lite-preview",
    )

    assert PopupMarkdownRenderer.source_label_for_session(session) == "gemini | gemini-3.1-flash-lite-preview"


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


def test_popup_presenter_refresh_session_updates_title_and_source_label() -> None:
    presenter = PopupPresenter()
    presenter._title_label = _FakeLabel()
    presenter._source_label = _FakeLabel()
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
        current_provider="gemini",
        current_model="gemini-1.5-flash",
        input_loading=False,
        result_loading=False,
    )
    presenter._active_session = session

    presenter._refresh_session_on_ui(session.session_id)

    assert presenter._title_label.text == "ClipAI - Translate EN"
    assert presenter._source_label.text == "gemini | gemini-1.5-flash"
    assert presenter._active_window.title_text == "ClipAI - Translate EN"
    presenter.dispose()


def test_popup_presenter_flush_pending_chunks_repaints_stable_stream_text() -> None:
    presenter = PopupPresenter()
    presenter._text_widget = _FakeTextWidget()
    presenter._active_session = PopupSession(
        action_id="summarize_next_steps",
        action_name="Summary",
        original_input="hello",
        latest_result="## 重點\n- 第一點",
        result_loading=False,
    )
    presenter._pending_chunks = ["## ", "重點"]

    presenter._flush_pending_chunks_on_ui(presenter._active_session.session_id)

    assert presenter._text_widget.get("1.0", "end") == "## 重點\n- 第一點"
    assert presenter._text_widget.see_calls == ["end"]
    presenter.dispose()


def test_popup_presenter_toggle_follow_up_packs_before_meta_row() -> None:
    presenter = PopupPresenter()
    presenter._follow_frame = _FakePackFrame()
    presenter._meta_row = object()
    presenter._follow_entry = _FakeEntry()
    presenter._active_window = _FakeWindow()
    presenter._follow_visible = False

    presenter._toggle_follow_up_on_ui()

    assert presenter._follow_visible is True
    assert presenter._follow_frame.pack_calls[0]["before"] is presenter._meta_row
    assert presenter._follow_entry.focus_calls == 1
    presenter.dispose()


def test_popup_presenter_toggle_secondary_actions_packs_before_meta_row() -> None:
    presenter = PopupPresenter()
    presenter._secondary_row = _FakePackFrame()
    presenter._meta_row = object()
    presenter._secondary_visible = False

    presenter._toggle_secondary_actions_on_ui()

    assert presenter._secondary_visible is True
    assert presenter._secondary_row.pack_calls[0]["before"] is presenter._meta_row
    presenter.dispose()


def test_popup_presenter_uses_updated_copy_and_archive_icons() -> None:
    assert ICON_COPY == "\U0001F4CB"
    assert ICON_ARCHIVE == "\U0001F4E6"


def test_popup_presenter_dispose_unsubscribes_tts_subscription() -> None:
    bus = EventBus()
    presenter = PopupPresenter(event_bus=bus)

    assert len(bus._subs_by_event[EVENT_TTS_STATE]) == 1

    presenter.dispose()

    assert len(bus._subs_by_event[EVENT_TTS_STATE]) == 0
