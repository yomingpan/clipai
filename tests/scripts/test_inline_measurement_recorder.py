import io
import logging

from scripts.run_inline_measurement_app import InlineMeasurementRecorder


def record(message):
    return logging.LogRecord("fixture", logging.INFO, "", 0, message, (), None)


def test_dispatch_observation_requires_matching_inline_operation_and_strips_native_fields():
    output = io.StringIO()
    recorder = InlineMeasurementRecorder(output, clock=lambda: 9_000_000)
    recorder.handle(record("unrelated private text"))
    recorder.handle(record(
        "Paste trace stage=dispatch_returned operation_id=old workflow_id= "
        "receipt=dispatched_unconfirmed detail_present=False"
    ))
    assert output.getvalue() == ""
    recorder.handle(record(
        "Inline trace monotonic_ns=1000000 stage=paste_requested interaction_id=i-1 "
        "capture_id= operation_id=p-1 mode= outcome="
    ))
    recorder.handle(record(
        "Paste trace stage=dispatch_returned operation_id=p-1 workflow_id= "
        "receipt=failed detail_present=True private text"
    ))
    assert "paste_dispatched" not in output.getvalue()
    recorder.handle(record(
        "Paste trace stage=dispatch_returned operation_id=p-1 workflow_id= "
        "receipt=dispatched_unconfirmed detail_present=False"
    ))
    assert output.getvalue().splitlines()[-1] == (
        "Inline trace monotonic_ns=9000000 stage=paste_dispatched interaction_id=i-1 "
        "capture_id= operation_id=p-1 mode= outcome=dispatched_unconfirmed"
    )
    assert "private" not in output.getvalue()
    assert "workflow_id" not in output.getvalue()


def test_frame_observation_is_identity_scoped_and_recorded_once():
    output = io.StringIO()
    recorder = InlineMeasurementRecorder(output, clock=lambda: 4_000_000)
    recorder.record_frame("old")
    assert output.getvalue() == ""
    recorder.handle(record(
        "Inline trace monotonic_ns=1000000 stage=capture_requested interaction_id=i-1 "
        "capture_id=c-1 operation_id= mode=minimal outcome=short"
    ))
    recorder.record_frame("old")
    recorder.record_frame("i-1")
    recorder.record_frame("i-1")
    assert output.getvalue().count("stage=first_frame_visible") == 1


def test_legacy_present_before_capture_trace_keeps_shortcut_to_frame_order():
    output = io.StringIO()
    clock = iter([1_000_000, 3_000_000])
    recorder = InlineMeasurementRecorder(output, clock=lambda: next(clock))
    recorder.begin_shortcut()
    recorder.record_frame("i-1")
    recorder.handle(record(
        "Inline trace monotonic_ns=4000000 stage=capture_requested interaction_id=i-1 "
        "capture_id=c-1 operation_id= mode=minimal outcome=short"
    ))
    recorder.end_shortcut()
    assert output.getvalue().splitlines() == [
        "Inline trace monotonic_ns=1000000 stage=capture_requested interaction_id=i-1 "
        "capture_id=c-1 operation_id= mode=minimal outcome=short",
        "Inline trace monotonic_ns=3000000 stage=first_frame_visible interaction_id=i-1 "
        "capture_id= operation_id= mode= outcome=",
    ]
