from __future__ import annotations

import queue
from dataclasses import replace

from ClipAI.core.commands import ArchiveResult, CloseSession, ControlSurfaceReleased, CopyResult, PasteResult, SubmitActionFeedback, TogglePin, ToggleSpeech
from ClipAI.core.models import ActionFeedbackContract, ControlSurfaceRef, FeedbackReason, OutputOperationResult, PasteTarget
from ClipAI.core.state import SessionSnapshot, SessionStatus
from ClipAI.core.voice import VoiceOrigin
from ClipAI.ui.popup_external_output import FocusEntered, OwnedDialogOpened, PopupExternalOutputTransitions, PopupRegistered, PopupShown
from ClipAI.ui.result_dialog import LatestSnapshotMailbox, ResultDialogPresenter, _SessionView, _content_render_key, workflow_render_patch


class Root:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def withdraw(self) -> None:
        self.events.append("withdraw")

    def deiconify(self) -> None:
        self.events.append("deiconify")


class Dialog:
    def __init__(self, events: list[str], *, alive: bool = True) -> None:
        self.root = Root(events)
        self.alive = alive
        self.pinned = False

    def is_alive(self) -> bool:
        return self.alive

    def is_visible(self) -> bool:
        return self.alive

    def close(self) -> None:
        self.alive = False
        self.root.events.append("close")

    def apply_external_output_visibility(self, visibility: str) -> None:
        self.root.events.append(f"visibility:{visibility}")

    def contains_screen_point(self, x: int, y: int) -> bool:
        return (x, y) == (10, 10)


class Surface:
    def __init__(self, selected: str | None, events: list[str]) -> None:
        self.selected = selected
        self.events = events
        self.overflow_expanded = False
        self.feedback_available = False
        self.header_double_click_callback = None
        self.focus_result = True

    def selected_text(self) -> str | None:
        return self.selected

    def set_standard_action_enabled(self, slot_id: str, enabled: bool) -> None:
        self.events.append(f"{slot_id}:{enabled}")

    def pulse_standard_action(self, slot_id: str, duration_ms: int = 1000) -> None:
        self.events.append(f"{slot_id}:pulse:{duration_ms}")

    def pulse_standard_action_error(self, slot_id: str, duration_ms: int = 1000) -> None:
        self.events.append(f"{slot_id}:error:{duration_ms}")

    def show_action_message(self, text: str, duration_ms: int = 1000) -> None:
        self.events.append(f"message:{text}:{duration_ms}")

    def set_speaker_active(self, active: bool) -> None:
        self.events.append(f"speaker:{active}")

    def toggle_pin(self) -> bool:
        self.events.append("pin:toggled")
        return True

    def bind_header_double_click(self, callback) -> None:
        self.header_double_click_callback = callback

    def bind_voice_draft_mode_toggle(self, callback) -> None:
        self.voice_draft_mode_toggle_callback = callback

    def focus_content(self) -> bool:
        return self.focus_result

    def configure_action_contract(self, contract, input_source: str) -> None:
        self.events.append(("contract", contract, input_source))

    def show_action_guidance_hint(self) -> None:
        self.events.append("guidance:shown")

    def configure_feedback(self, contract, state, message, on_submit) -> None:
        self.feedback_submit = on_submit
        self.events.append(("feedback", state, message))

    def hide_feedback(self) -> None:
        self.events.append("feedback:hidden")

    def toggle_feedback_overlay(self) -> bool:
        self.events.append("feedback:toggled")
        return self.feedback_available

    def close_feedback_overlay(self) -> None:
        self.events.append("feedback:closed")

    def collapse_overflow(self) -> None:
        self.events.append("overflow:collapsed")

    def set_paste_focus_state(self, focused, target, *, voice_draft_editing=None) -> None:
        self.focused = focused
        self.paste_target = target
        self.voice_draft_editing = voice_draft_editing
        if voice_draft_editing is not None:
            self.events.append(f"voice-mode:{voice_draft_editing}")

    def set_voice_draft_editing(self, editing: bool) -> None:
        self.voice_draft_editing = editing
        self.events.append(f"voice-editor:{editing}")

    def set_editable_content(self, text: str, _on_changed) -> None:
        self.events.append(f"voice-content:{text}")


def presenter_with_selection(selected: str | None):
    events: list[str] = []
    presenter = ResultDialogPresenter.__new__(ResultDialogPresenter)
    external_output = PopupExternalOutputTransitions()
    external_output.focus(PopupRegistered())
    external_output.focus(PopupShown())
    external_output.focus(FocusEntered())
    presenter._views = {"s1": _SessionView(Dialog(events), Surface(selected, events), external_output=external_output)}
    presenter._command_sink = lambda command: events.append(command)
    presenter._paste_target = PasteTarget("hwnd:10", 42, "Notepad", "Untitled", 1)
    presenter._paste_target_updates = queue.Queue()
    presenter._shortcut_guide_focus_hold_active = False
    presenter._shortcut_guide_focus_return = None
    return presenter, events


def test_text_command_carries_popup_selection() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._send_text_command("s1", CopyResult)
    assert events == [CopyResult("s1", "selected")]


def test_copy_and_archive_wait_for_typed_acknowledgment() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._copy("s1")
    presenter._archive("s1")
    assert len(events) == 2
    assert isinstance(events[0], CopyResult) and events[0].text == "selected" and events[0].operation_id
    assert isinstance(events[1], ArchiveResult) and events[1].text == "selected" and events[1].operation_id


def test_acknowledgment_projects_success_and_ignores_stale_operation() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._views["s1"].external_output.begin("archive", "new")
    presenter._apply_output_operation(OutputOperationResult("old", "s1", "archive", "succeeded"))
    assert events == []
    presenter._apply_output_operation(OutputOperationResult("new", "s1", "archive", "succeeded"))
    assert "archive:pulse:1000" in events


def test_late_output_operation_evicts_dead_view_without_touching_surface() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._views["s1"].dialog.alive = False

    presenter._apply_output_operation(OutputOperationResult("late", "s1", "archive", "pending"))

    assert events == []
    assert presenter._views == {}


def test_late_completed_snapshot_evicts_dead_view_without_touching_surface() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._views["s1"].dialog.alive = False
    snapshot = SessionSnapshot("s1", 1, SessionStatus.COMPLETED, "a", "A", "model", content="late")

    presenter._apply(snapshot)

    assert events == []
    assert presenter._views == {}


def test_closed_snapshot_cleanup_is_idempotent() -> None:
    presenter, events = presenter_with_selection("selected")
    snapshot = SessionSnapshot("s1", 1, SessionStatus.CLOSED, "a", "A", "model")

    presenter._apply(snapshot)
    presenter._apply(snapshot)

    assert events == ["close"]
    assert presenter._views == {}


def test_stopped_snapshot_has_distinct_content_render_key() -> None:
    snapshot = SessionSnapshot("s1", 1, SessionStatus.STOPPED, "a", "A", "model", status_text="Stopped")

    assert _content_render_key(snapshot) == (SessionStatus.STOPPED, "", "Stopped", None)


def test_latest_snapshot_mailbox_coalesces_each_workflow_to_highest_revision() -> None:
    mailbox = LatestSnapshotMailbox()
    mailbox.put(SessionSnapshot("one", 1, SessionStatus.REQUESTING_PROVIDER, "a", "A", "m"))
    mailbox.put(SessionSnapshot("one", 3, SessionStatus.COMPLETED, "a", "A", "m", content="done"))
    mailbox.put(SessionSnapshot("one", 2, SessionStatus.REQUESTING_PROVIDER, "a", "A", "m", content="late partial"))
    mailbox.put(SessionSnapshot("two", 1, SessionStatus.FAILED, "a", "A", "m", error="failed"))

    drained = {snapshot.session_id: snapshot for snapshot in mailbox.drain()}
    assert drained["one"].revision == 3
    assert drained["one"].status == SessionStatus.COMPLETED
    assert drained["two"].status == SessionStatus.FAILED
    assert mailbox.drain() == ()


def test_speaking_and_pin_updates_do_not_patch_unchanged_content() -> None:
    initial = SessionSnapshot("one", 1, SessionStatus.COMPLETED, "a", "A", "m", content="result")
    speaking = replace(initial, revision=2, speaking=True)
    pinned = replace(speaking, revision=3, pinned=True)

    speaking_patch = workflow_render_patch(initial, speaking)
    pinned_patch = workflow_render_patch(speaking, pinned)

    assert speaking_patch.content is False
    assert speaking_patch.visual_state is True
    assert pinned_patch.content is False
    assert pinned_patch.header is True


def test_speaker_command_waits_for_snapshot_to_change_icon() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._toggle_speech("s1")
    assert len(events) == 1
    assert isinstance(events[0], ToggleSpeech) and events[0].text == "selected" and events[0].operation_id


def test_speech_operation_projects_to_speaker_slot() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._views["s1"].external_output.begin("speech", "speech-op")
    presenter._apply_output_operation(OutputOperationResult("speech-op", "s1", "speech", "pending"))
    presenter._apply_output_operation(OutputOperationResult("speech-op", "s1", "speech", "succeeded"))
    assert "speaker:pulse:1000" in events


def test_speech_failure_projects_to_speaker_slot() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._views["s1"].external_output.begin("speech", "speech-op")
    presenter._apply_output_operation(OutputOperationResult("speech-op", "s1", "speech", "pending"))
    presenter._apply_output_operation(OutputOperationResult("speech-op", "s1", "speech", "failed"))
    assert "speaker:error:1000" in events


def test_paste_emits_identified_command_and_waits_for_pending_projection() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._paste("s1")
    assert len(events) == 2
    assert events[0] == "visibility:hidden"
    assert isinstance(events[1], PasteResult) and events[1].text == "selected" and events[1].operation_id


def test_pinned_unconfirmed_paste_restores_without_activation() -> None:
    presenter, events = presenter_with_selection("selected")
    view = presenter._views["s1"]
    view.dialog.pinned = True

    presenter._paste("s1")
    operation_id = events[-1].operation_id
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "paste", "pending"))
    presenter._apply_output_operation(OutputOperationResult(
        operation_id,
        "s1",
        "paste",
        "dispatched_unconfirmed",
    ))

    assert "visibility:visible_no_activate" in events
    assert view.surface.focused is False


def test_unpinned_paste_failure_restores_with_focus() -> None:
    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]

    presenter._paste("s1")
    operation_id = events[-1].operation_id
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "paste", "pending"))
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "paste", "failed"))

    assert "visibility:visible_activate" in events


def test_cancelled_paste_restores_without_stealing_focus() -> None:
    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]

    presenter._paste("s1")
    operation_id = events[-1].operation_id
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "paste", "pending"))
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "paste", "cancelled"))

    assert "visibility:visible_no_activate" in events
    assert "visibility:visible_activate" not in events
    assert "message:已取消貼上:1500" in events


def test_cleanup_failed_paste_restores_without_stealing_focus() -> None:
    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]

    presenter._paste("s1")
    operation_id = events[-1].operation_id
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "paste", "pending"))
    presenter._apply_output_operation(OutputOperationResult(
        operation_id,
        "s1",
        "paste",
        "cleanup_failed",
        message="Clipboard restore failed.",
    ))

    assert "visibility:visible_no_activate" in events
    assert "visibility:visible_activate" not in events
    assert "message:Clipboard restore failed.:3000" in events


def test_unpinned_unconfirmed_paste_stays_hidden_without_stealing_focus() -> None:
    presenter, events = presenter_with_selection("selected")
    view = presenter._views["s1"]

    presenter._paste("s1")
    operation_id = events[-1].operation_id
    presenter._apply_output_operation(OutputOperationResult(operation_id, "s1", "paste", "pending"))
    presenter._apply_output_operation(OutputOperationResult(
        operation_id,
        "s1",
        "paste",
        "dispatched_unconfirmed",
        message="Paste was sent; confirm before trying again.",
    ))

    assert "visibility:visible_activate" not in events
    assert "visibility:visible_no_activate" not in events
    assert presenter._views["s1"] is view
    assert "message:Paste was sent; confirm before trying again.:2500" in events


def test_stale_paste_result_does_not_restore_current_transition() -> None:
    presenter, events = presenter_with_selection("selected")
    view = presenter._views["s1"]
    presenter._paste("s1")

    presenter._apply_output_operation(OutputOperationResult("old", "s1", "paste", "cancelled"))

    assert "visibility:visible_activate" not in events
    assert "visibility:visible_no_activate" not in events


def test_pin_updates_visual_state_before_emitting_command() -> None:
    presenter, events = presenter_with_selection(None)
    presenter._toggle_pin("s1")
    assert events == ["pin:toggled", TogglePin("s1")]


def test_feedback_submission_is_a_typed_identified_command() -> None:
    presenter, events = presenter_with_selection(None)

    presenter._submit_feedback("s1", "step-1", "needs_adjustment", "meaning_lost", "Too aggressive", True)

    assert len(events) == 1
    command = events[0]
    assert isinstance(command, SubmitActionFeedback)
    assert command.session_id == "s1"
    assert command.step_id == "step-1"
    assert command.operation_id
    assert command.reason == "meaning_lost"
    assert command.save_case is True


def test_ctrl_r_feedback_request_reports_unsupported_recipe() -> None:
    presenter, events = presenter_with_selection(None)

    presenter._toggle_feedback("s1")

    assert events == ["feedback:toggled", "message:此 Recipe 尚未啟用回饋:1000"]


def test_ctrl_r_feedback_request_opens_supported_recipe_overlay() -> None:
    presenter, events = presenter_with_selection(None)
    presenter._views["s1"].surface.feedback_available = True

    presenter._toggle_feedback("s1")

    assert events == ["feedback:toggled"]


def test_ctrl_slash_toggles_follow_up_for_active_popup() -> None:
    class ShortcutRoot:
        def __init__(self) -> None:
            self.bindings = {}

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings[sequence] = callback

    class Lifecycle:
        def schedule(self, _delay_ms, _callback) -> str:
            return "scheduled"

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.dialog.root = ShortcutRoot()
    view.dialog.lifecycle = Lifecycle()
    presenter._toggle_follow_up = lambda session_id: events.append(f"follow-up:{session_id}")

    presenter._register_view("s1", view)
    result = view.dialog.root.bindings["<Control-slash>"](None)

    assert result == "break"
    assert events == ["follow-up:s1"]


def test_failed_initial_focus_attempt_does_not_claim_popup_focus() -> None:
    class ShortcutRoot:
        def __init__(self) -> None:
            self.bindings = {}

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings[sequence] = callback

    class Lifecycle:
        def __init__(self) -> None:
            self.callbacks = []

        def schedule(self, _delay_ms, callback) -> str:
            self.callbacks.append(callback)
            return "scheduled"

        def focus(self) -> bool:
            return False

    presenter, _events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.external_output = PopupExternalOutputTransitions()
    view.dialog.root = ShortcutRoot()
    view.dialog.lifecycle = Lifecycle()
    view.surface.focus_result = False

    presenter._register_view("s1", view)
    view.dialog.lifecycle.callbacks[0]()

    assert view.external_output.focused_inside is False


def test_first_outside_pointer_press_closes_popup_when_native_focus_failed() -> None:
    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.external_output = PopupExternalOutputTransitions()
    view.external_output.focus(PopupRegistered())
    view.external_output.focus(PopupShown())

    presenter._handle_pointer_press(100, 100)

    assert ControlSurfaceReleased(ControlSurfaceRef("s1", "workflow")) in events
    assert CloseSession("s1") in events


def test_pointer_press_inside_popup_does_not_close_it() -> None:
    presenter, events = presenter_with_selection(None)

    presenter._handle_pointer_press(10, 10)

    assert not any(isinstance(event, CloseSession) for event in events)


def test_voice_capture_popup_establishes_initial_focus_immediately() -> None:
    class Button:
        def configure(self, **_kwargs) -> None:
            pass

    presenter, _events = presenter_with_selection(None)
    view = presenter._views.pop("s1")
    for method in (
        "set_pinned_state",
        "set_title",
        "set_source_preview",
        "set_model",
        "set_loading",
        "configure_standard_actions",
    ):
        setattr(view.surface, method, lambda *_args, **_kwargs: None)
    view.surface.close_button = Button()
    view.surface.pin_button = Button()
    view.surface.configure_back_action = lambda _callback: None
    presenter._create_view = lambda _session_id: view
    presenter._configure_voice_capture_controls = lambda _snapshot, _view: None
    requested_initial_focus = []
    presenter._register_view = lambda _session_id, _view, *, focus_on_show=True: requested_initial_focus.append(focus_on_show)

    presenter._apply(SessionSnapshot(
        "s1",
        1,
        SessionStatus.VOICE_LISTENING,
        "voice_input",
        "Voice Input",
        "model",
        status_text="Listening",
    ))

    assert requested_initial_focus == [True]


def test_ctrl_v_pastes_only_for_active_popup() -> None:
    class ShortcutRoot:
        def __init__(self) -> None:
            self.bindings = {}

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings[sequence] = callback

    class Lifecycle:
        def schedule(self, _delay_ms, _callback) -> str:
            return "scheduled"

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.dialog.root = ShortcutRoot()
    view.dialog.lifecycle = Lifecycle()
    presenter._paste = lambda session_id: events.append(f"paste:{session_id}")

    presenter._register_view("s1", view)
    result = view.dialog.root.bindings["<Control-v>"](None)

    assert result == "break"
    assert events == ["paste:s1"]

    events.clear()
    view.external_output.focus(OwnedDialogOpened())
    result = view.dialog.root.bindings["<Control-v>"](None)

    assert result == "break"
    assert events == []


def test_ctrl_v_preserves_native_paste_in_editable_popup_fields() -> None:
    class EditableWidget:
        def winfo_class(self) -> str:
            return "Entry"

        def cget(self, option: str) -> str:
            assert option == "state"
            return "normal"

    presenter, events = presenter_with_selection(None)
    presenter._paste = lambda session_id: events.append(f"paste:{session_id}")

    result = presenter._paste_shortcut(type("Event", (), {"widget": EditableWidget()})(), "s1")

    assert result is None
    assert events == []


def test_ctrl_v_preserves_native_paste_in_editable_voice_review() -> None:
    class EditableVoiceDraft:
        def winfo_class(self) -> str:
            return "Text"

        def cget(self, option: str) -> str:
            assert option == "state"
            return "normal"

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.last_snapshot = SessionSnapshot(
        "s1",
        1,
        SessionStatus.VOICE_REVIEW,
        "voice_input",
        "Voice Input",
        "",
        content="current draft",
    )
    presenter._paste = lambda session_id: events.append(f"paste:{session_id}")

    result = presenter._paste_shortcut(
        type("Event", (), {"widget": EditableVoiceDraft()})(),
        "s1",
    )

    assert result is None
    assert events == []


def test_ctrl_enter_switches_voice_draft_to_reading_mode() -> None:
    class ShortcutRoot:
        def __init__(self) -> None:
            self.bindings = {}

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings[sequence] = callback

    class Lifecycle:
        def schedule(self, _delay_ms, _callback) -> str:
            return "scheduled"

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.dialog.root = ShortcutRoot()
    view.dialog.lifecycle = Lifecycle()
    view.last_snapshot = SessionSnapshot(
        "s1",
        1,
        SessionStatus.VOICE_REVIEW,
        "voice_input",
        "Voice Input",
        "",
        content="current draft",
    )

    presenter._register_view("s1", view)
    result = view.dialog.root.bindings["<Control-Return>"](
        type("Event", (), {"state": 0x0004})(),
    )

    assert result == "break"
    assert view.voice_draft_editing is False
    assert events[-2:] == ["voice-editor:False", "voice-mode:False"]

    class VoiceDraftWidget:
        def winfo_class(self) -> str:
            return "Text"

        def cget(self, option: str) -> str:
            assert option == "state"
            return "normal" if view.voice_draft_editing else "disabled"

    presenter._paste = lambda session_id: events.append(f"paste:{session_id}")
    paste_event = type("Event", (), {"state": 0x0004, "widget": VoiceDraftWidget()})()

    assert view.dialog.root.bindings["<Control-v>"](paste_event) == "break"
    assert events[-1] == "paste:s1"

    assert view.dialog.root.bindings["<Control-Return>"](
        type("Event", (), {"state": 0x0004})(),
    ) == "break"
    paste_count = events.count("paste:s1")
    assert view.dialog.root.bindings["<Control-v>"](paste_event) is None
    assert events.count("paste:s1") == paste_count


def test_voice_draft_snapshot_keeps_the_selected_reading_mode() -> None:
    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    target = PasteTarget("hwnd:10", 42, "Notepad", "Untitled", 1)
    previous = SessionSnapshot(
        "s1",
        1,
        SessionStatus.VOICE_REVIEW,
        "voice_input",
        "Voice Input",
        "",
        content="old draft",
        voice_origin=VoiceOrigin(target, "old draft", 0),
    )
    current = replace(
        previous,
        revision=2,
        content="updated draft",
        voice_origin=VoiceOrigin(target, "updated draft", 1),
    )
    view.revision = previous.revision
    view.last_snapshot = previous
    view.voice_draft_editing = False

    presenter._apply(current)

    assert events[-2:] == ["voice-content:updated draft", "voice-editor:False"]
    assert view.voice_draft_editing is False


def test_ctrl_e_toggles_pin_for_active_popup() -> None:
    class ShortcutRoot:
        def __init__(self) -> None:
            self.bindings = {}

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings[sequence] = callback

    class Lifecycle:
        def schedule(self, _delay_ms, _callback) -> str:
            return "scheduled"

    class CtrlWithNumLockEvent:
        state = 0x0004 | 0x0008

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.dialog.root = ShortcutRoot()
    view.dialog.lifecycle = Lifecycle()

    presenter._register_view("s1", view)
    result = view.dialog.root.bindings["<Control-e>"](CtrlWithNumLockEvent())

    assert result == "break"
    assert events == ["pin:toggled", TogglePin("s1")]

    events.clear()
    view.external_output.focus(OwnedDialogOpened())
    result = view.dialog.root.bindings["<Control-e>"](CtrlWithNumLockEvent())

    assert result == "break"
    assert events == []


def test_popup_shortcuts_ignore_alt_modified_global_chords() -> None:
    class ShortcutRoot:
        def __init__(self) -> None:
            self.bindings = {}

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings[sequence] = callback

    class Lifecycle:
        def schedule(self, _delay_ms, _callback) -> str:
            return "scheduled"

    class CtrlAltEvent:
        state = 0x0004 | 0x0008 | 0x00020000

    class CtrlShiftEvent:
        state = 0x0004 | 0x0001

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.dialog.root = ShortcutRoot()
    view.dialog.lifecycle = Lifecycle()
    presenter._toggle_speech = lambda _session_id: events.append("speech:toggled")
    presenter._copy = lambda _session_id: events.append("copied")
    presenter._archive = lambda _session_id: events.append("archived")

    presenter._register_view("s1", view)

    for event in (CtrlAltEvent(), CtrlShiftEvent()):
        for shortcut in ("<Control-e>", "<Control-q>", "<Control-c>", "<Control-s>"):
            assert view.dialog.root.bindings[shortcut](event) == "break"

    assert events == []


def test_double_clicking_popup_header_toggles_pin() -> None:
    class ShortcutRoot:
        def __init__(self) -> None:
            self.bindings = {}

        def bind(self, sequence, callback, add=None) -> None:
            self.bindings[sequence] = callback

    class Lifecycle:
        def schedule(self, _delay_ms, _callback) -> str:
            return "scheduled"

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.dialog.root = ShortcutRoot()
    view.dialog.lifecycle = Lifecycle()

    presenter._register_view("s1", view)
    result = view.surface.header_double_click_callback(None)

    assert result == "break"
    assert events == ["pin:toggled", TogglePin("s1")]


def test_workflow_context_projects_selection_and_displayed_step() -> None:
    presenter, _events = presenter_with_selection("selected")
    presenter._views["s1"].content = "full result"
    presenter._views["s1"].step_id = "step-1"
    context = presenter.workflow_context("s1")
    assert context.workflow_id == "s1"
    assert context.step_id == "step-1"
    assert context.content == "full result"
    assert context.selected_text == "selected"


def test_voice_review_projects_its_draft_as_workflow_context() -> None:
    presenter, _events = presenter_with_selection("selected")
    view = presenter._views["s1"]
    view.content = "voice draft"
    view.step_id = None
    view.last_snapshot = SessionSnapshot("s1", 1, SessionStatus.VOICE_REVIEW, "voice_input", "Voice Input", "", content="voice draft")

    context = presenter.workflow_context("s1")

    assert context is not None
    assert context.step_id == "voice-origin"
    assert context.content == "voice draft"


def test_native_close_request_immediately_excludes_popup_content_and_emits_close_intent() -> None:
    presenter, events = presenter_with_selection("selected")
    presenter._views["s1"].content = "full result"
    presenter._views["s1"].step_id = "step-1"

    presenter._request_close("s1")
    presenter._copy("s1")
    presenter._send_text_command("s1", CopyResult)

    assert events == [CloseSession("s1")]
    assert presenter.workflow_context("s1") is None


def test_shortcut_guide_holds_and_restores_the_original_popup_focus() -> None:
    class Guide:
        def show(self, _snapshot) -> None:
            events.append("guide:show")

        def close(self) -> None:
            events.append("guide:close")

    class Lifecycle:
        def schedule(self, _delay_ms, callback) -> str:
            callback()
            return "restore-focus"

        def focus(self) -> None:
            events.append("focus")

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    view.dialog.lifecycle = Lifecycle()
    presenter._shortcut_guide_dialog = Guide()
    presenter._shortcut_guide_focus_return = None

    presenter.show_shortcut_guide(object())

    assert view.surface.focused is False

    presenter.close_shortcut_guide()
    presenter._copy("s1")

    assert events[:3] == ["guide:show", "guide:close", "focus"]
    assert isinstance(events[3], CopyResult)
    assert view.external_output.focused_inside is True
    assert view.surface.focused is True


def test_shortcut_guide_does_not_restore_a_popup_that_started_closing() -> None:
    class Guide:
        def show(self, _snapshot) -> None:
            pass

        def close(self) -> None:
            events.append("guide:close")

    presenter, events = presenter_with_selection(None)
    view = presenter._views["s1"]
    presenter._shortcut_guide_dialog = Guide()
    presenter._shortcut_guide_focus_return = None

    presenter.show_shortcut_guide(object())
    view.close_requested = True
    presenter.close_shortcut_guide()

    assert events == ["guide:close"]
    assert view.external_output.focused_inside is False


def test_shortcut_guide_without_an_original_popup_does_not_force_focus() -> None:
    events = []

    class Guide:
        def show(self, _snapshot) -> None:
            events.append("guide:show")

        def close(self) -> None:
            events.append("guide:close")

    presenter = ResultDialogPresenter.__new__(ResultDialogPresenter)
    presenter._views = {}
    presenter._shortcut_guide_dialog = Guide()
    presenter._shortcut_guide_focus_hold_active = False
    presenter._shortcut_guide_focus_return = None

    presenter.show_shortcut_guide(object())
    presenter.close_shortcut_guide()

    assert events == ["guide:show", "guide:close"]
    assert presenter._shortcut_guide_focus_return is None


def test_latest_paste_target_updates_visible_focus_projection() -> None:
    presenter, _events = presenter_with_selection(None)
    newer = PasteTarget("hwnd:20", 84, "Writer", "Draft", 2)

    presenter._apply_paste_target(newer)
    presenter._apply_paste_target(PasteTarget("hwnd:10", 42, "Old", "Old", 1))

    surface = presenter._views["s1"].surface
    assert surface.focused is True
    assert surface.paste_target == newer


def test_content_key_ignores_speaking_and_pin_snapshot_changes() -> None:
    snapshot = SessionSnapshot("s1", 0, SessionStatus.COMPLETED, "a", "A", "model", content="long content")
    changed_ui_state = snapshot.evolve(speaking=True, pinned=True)
    assert _content_render_key(changed_ui_state) == _content_render_key(snapshot)


def test_content_key_changes_for_new_content() -> None:
    snapshot = SessionSnapshot("s1", 0, SessionStatus.COMPLETED, "a", "A", "model", content="first")
    changed_content = snapshot.evolve(content="second")
    assert _content_render_key(changed_content) != _content_render_key(snapshot)
