from dataclasses import replace

import pytest

from ClipAI.core.models import ActionInvocation, InputDocument, InputRecovery, InputTarget, PreparedInput, ResolvedAction, SelectionCaptureOutcome
from ClipAI.core.popup_presentation import project_popup_presentation
from ClipAI.core.state import SessionSnapshot, SessionStatus


def recovery_snapshot():
    action = ResolvedAction("translate", "翻譯", "system", "{input}", "short", "selection_or_clipboard", "popup", None)
    invocation = ActionInvocation("attempt", action.id, "short", InputTarget("external_text"), workflow_id="workflow")
    prepared = PreparedInput(
        clipboard_text_document=InputDocument("The original clipboard content", "clipboard"),
        selection_outcome=SelectionCaptureOutcome(reason="unsupported"),
    )
    recovery = InputRecovery("choice", invocation, action, prepared)
    return SessionSnapshot("workflow", 2, SessionStatus.AWAITING_INPUT_CHOICE, action.id, action.name, "model",
        source_preview=prepared.clipboard_preview(), status_text=recovery.message, input_recovery=recovery)


@pytest.fixture(scope="module")
def recovery_root():
    import customtkinter as ctk
    root = ctk.CTk()
    root.withdraw()
    yield root
    for job in root.tk.call("after", "info"):
        root.after_cancel(job)
    root.destroy()


def test_recovery_projection_exposes_only_frozen_choice_and_hides_on_resume():
    snapshot = recovery_snapshot()
    model = project_popup_presentation(snapshot)
    assert model.input_recovery_id == "choice"
    assert model.clipboard_choice_available
    assert "original clipboard" in model.source_preview
    assert model.enabled_actions == ()
    assert model.feedback is None
    resumed = project_popup_presentation(replace(snapshot, status=SessionStatus.PREPARING_REQUEST, input_recovery=None))
    assert resumed.input_recovery_id is None
    assert not resumed.clipboard_choice_available


@pytest.mark.integration
def test_real_popup_recovery_button_is_read_only_and_resumes_without_rebuilding(recovery_root):
    import customtkinter as ctk
    from ClipAI.ui.base_dialog import BaseDialog, BaseResultSurface
    from ClipAI.core.models import PopupBounds
    from ClipAI.ui.primary_surface import PrimarySurfaceHost, PrimarySurfaceSpec

    root = recovery_root
    dialog = None
    try:
        host = PrimarySurfaceHost(root, PrimarySurfaceSpec(PopupBounds(20, 20, 400, 336)), None)
        dialog = BaseDialog(title="翻譯", width=400, height=336, master=root, show_on_create=False, primary_surface_host=host, primary_surface_lease=host.acquire())
        surface = BaseResultSurface(dialog)
        selected = []
        surface.bind_clipboard_choice(selected.append)
        snapshot = recovery_snapshot()
        surface.render(project_popup_presentation(snapshot))
        surface.set_content_chunks([(snapshot.status_text, "body")])
        root.update_idletasks()
        before = surface.content_text.get("1.0", "end-1c")
        surface.content_text.insert("end", "unexpected edit")
        assert surface.content_text.get("1.0", "end-1c") == before
        assert surface.clipboard_choice_button.winfo_manager() == "grid"
        surface.clipboard_choice_button.invoke()
        assert selected == ["choice"]
        assert surface.clipboard_choice_button.cget("state") == "disabled"
        surface.render(project_popup_presentation(replace(snapshot, status=SessionStatus.PREPARING_REQUEST, input_recovery=None)))
        assert surface.clipboard_choice_button.winfo_manager() == ""
    finally:
        if dialog is not None:
            dialog.close()


def test_coalesced_new_recovery_replaces_old_guidance_even_when_message_is_equal():
    from ClipAI.ui.result_dialog import workflow_render_patch
    old = recovery_snapshot()
    current = replace(
        old, revision=4,
        input_recovery=replace(
            old.input_recovery, recovery_id="new",
            prepared=PreparedInput(selection_outcome=SelectionCaptureOutcome(reason="unsupported")),
        ),
    )
    assert workflow_render_patch(old, current).content


@pytest.mark.integration
@pytest.mark.parametrize("held_on_focus", [False, True, None])
def test_real_popup_enter_confirms_on_fresh_release_once_and_hidden_choice_cannot_fire(held_on_focus, recovery_root):
    import customtkinter as ctk
    from ClipAI.ui.base_dialog import BaseDialog, BaseResultSurface
    from ClipAI.core.models import PopupBounds
    from ClipAI.ui.primary_surface import PrimarySurfaceHost, PrimarySurfaceSpec
    root = recovery_root
    host = PrimarySurfaceHost(root, PrimarySurfaceSpec(PopupBounds(20, 20, 400, 336)), None)
    dialog = BaseDialog(title="Recovery", width=400, height=336, master=root, show_on_create=False, primary_surface_host=host, primary_surface_lease=host.acquire())
    try:
        held = [held_on_focus]
        surface = BaseResultSurface(dialog, key_state_reader=lambda _token: held[0])
        selected = []
        surface.bind_clipboard_choice(selected.append)
        model = project_popup_presentation(recovery_snapshot())
        surface.render(model)
        assert surface.clipboard_choice_button.cget("text") == "使用剪貼簿執行（Enter）"
        dialog.show()
        surface.content_text.focus_force()
        root.update()
        if held_on_focus is not False:
            # External key-down was never delivered to this Popup. Its first
            # delivered event can be an auto-repeat after the settle period.
            delay = ctk.BooleanVar(root, False)
            root.after(350, lambda: delay.set(True))
            root.wait_variable(delay)
        surface.content_text.event_generate("<KeyPress-Return>")
        surface.content_text.event_generate("<KeyRelease-Return>")
        root.update()
        assert selected == []
        held[0] = False
        settled = ctk.BooleanVar(root, False)
        root.after(350, lambda: settled.set(True))
        root.wait_variable(settled)
        surface.content_text.event_generate("<KeyPress-Return>")
        root.update()
        assert selected == []
        surface.content_text.event_generate("<KeyRelease-Return>")
        root.update()
        assert selected == ["choice"]
        surface.render(model)
        assert surface.clipboard_choice_button.cget("state") == "disabled"
        surface.clipboard_choice_button.invoke()
        assert selected == ["choice"]
        surface.render(replace(model, input_recovery_id=None, clipboard_choice_available=False))
        surface.content_text.event_generate("<KeyPress-Return>")
        surface.content_text.event_generate("<KeyRelease-Return>")
        root.update()
        assert selected == ["choice"]
        surface.render(model)
        assert surface.clipboard_choice_button.cget("state") == "disabled"
    finally:
        dialog.close()
