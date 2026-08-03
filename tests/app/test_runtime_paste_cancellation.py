from ClipAI.core.commands import CloseSession, PasteResult, StartAction

from test_runtime import make_runtime, workflow


def _runtime_with_paste():
    runtime, view, supervisor, outputs, listener = make_runtime()
    runtime.enqueue(StartAction("a", "short"))
    runtime.drain_commands()
    workflow_id = view.snapshots[-1].session_id
    controller = workflow(view, workflow_id)
    controller._snapshot = controller.snapshot.evolve(content="use me")
    runtime.enqueue(PasteResult(workflow_id, operation_id="paste-op"))
    runtime.drain_commands()
    return runtime, view, supervisor, outputs, listener


def test_queued_paste_cancellation_is_terminal_without_running_side_effect() -> None:
    runtime, view, supervisor, outputs, _listener = _runtime_with_paste()

    assert runtime._result_output_module.cancel_operation("paste-op") == ("paste-op",)

    assert view.output_results[-1].state == "cancelled"
    assert outputs.pasted == []
    assert supervisor.cancelled[-1] == "paste-op"


def test_running_paste_cancellation_waits_for_real_operation_outcome() -> None:
    runtime, view, supervisor, outputs, _listener = _runtime_with_paste()
    job = runtime._result_output_module._paste_jobs["paste-op"]
    job.has_started = True

    runtime._result_output_module.cancel_operation("paste-op")

    assert view.output_results[-1].state == "pending"
    job.has_started = False
    supervisor.work["paste-op"]()
    assert view.output_results[-1].state == "cancelled"
    assert outputs.pasted == []


def test_closing_workflow_cancels_queued_paste_before_dispatch() -> None:
    runtime, view, supervisor, outputs, _listener = _runtime_with_paste()
    workflow_id = view.snapshots[-1].session_id

    runtime.enqueue(CloseSession(workflow_id))
    runtime.drain_commands()
    supervisor.work["paste-op"]()

    assert outputs.pasted == []
    assert "paste-op" in supervisor.cancelled
