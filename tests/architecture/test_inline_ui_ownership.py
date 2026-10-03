from __future__ import annotations

import ast
import inspect

from ClipAI.app.runtime_workflows import WorkflowRuntimeModule
from ClipAI.services.voice_capture_admission import VoiceCaptureAdmissionPolicy
from ClipAI.ui.result_dialog import ResultDialogPresenter


def test_result_presenter_does_not_own_inline_or_modal_window_fields() -> None:
    source = inspect.getsource(ResultDialogPresenter)
    assert "_inline_dictation_window" not in source
    for field in (
        "_provider_settings_dialog", "_personal_styles_dialog", "_shortcut_guide_dialog",
        "_voice_setup_dialog", "_about_dialog",
    ):
        assert field not in source


def test_unpinned_popup_hook_query_does_not_iterate_workflow_records() -> None:
    method = ast.parse(inspect.getsource(WorkflowRuntimeModule.unpinned_foreground_popup_id).lstrip())
    assert not any(isinstance(node, (ast.For, ast.AsyncFor, ast.ListComp, ast.GeneratorExp)) for node in ast.walk(method))


def test_voice_admission_policy_is_owned_by_services() -> None:
    assert VoiceCaptureAdmissionPolicy.__module__ == "ClipAI.services.voice_capture_admission"
