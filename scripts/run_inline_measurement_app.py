"""Run unchanged ClipAI with a process-local, content-free baseline observer.

The first-frame timestamp follows Tk viewability and DwmFlush, not pixel
sampling. Capture-request time starts at shortcut admission, not HID key-down.
Dispatch is observed only after the existing Paste owner returns its receipt.
No audio, text, window titles, clipboard data or screenshots enter this file.
Run without concurrent desktop benchmarks; use --log with the controlled runner.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
import logging
from pathlib import Path
import re
import time
from typing import TextIO

from scripts.report_inline_dictation_baseline import TRACE


STAGES = frozenset({
    "capture_requested", "listening", "stop_requested", "recognition_settled",
    "choice_ready", "choice_shortcut", "refine_requested", "refine_admitted",
    "refine_settled", "refine_cancel_requested", "refine_cancel_unconfirmed",
    "late_refine_ignored", "paste_requested", "paste_terminal",
    "paste_cancel_requested", "recovery_visible_requested", "copy_result",
    "discard_requested", "discard_terminal",
})
DISPATCH = re.compile(
    r"Paste trace stage=dispatch_returned operation_id=(?P<operation>\S+) "
    r"workflow_id=\S* receipt=dispatched_unconfirmed detail_present=(?:True|False)"
)


class InlineMeasurementRecorder(logging.Handler):
    """Observe this process only; correlate dispatch with its Inline origin."""

    def __init__(self, output: TextIO, *, clock: Callable[[], int] = time.monotonic_ns):
        super().__init__()
        self._output = output
        self._clock = clock
        self._active = ""
        self._frame_recorded = False
        self._operations: dict[str, str] = {}
        self._shortcut_ns: int | None = None
        self._pending_frame: tuple[str, int] | None = None

    def begin_shortcut(self) -> None:
        self._shortcut_ns = self._clock()
        self._pending_frame = None

    def end_shortcut(self) -> None:
        self._shortcut_ns = None
        self._pending_frame = None

    def _write(self, line: str) -> None:
        self._output.write(line + "\n")
        self._output.flush()

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        match = TRACE.fullmatch(message)
        if match is not None:
            if match["stage"] not in STAGES or not match["interaction"]:
                return
            if match["stage"] == "capture_requested":
                self._active = match["interaction"]
                self._frame_recorded = False
            if match["stage"] in {"capture_requested", "stop_requested"} and self._shortcut_ns is not None:
                # Legacy runtime logs capture after showing the window. Keep the
                # independently observed shortcut-entry time, never subtract a
                # timestamp that already follows the first frame.
                message = message.replace(f"monotonic_ns={match['ns']}", f"monotonic_ns={self._shortcut_ns}", 1)
            if match["stage"] == "paste_requested" and match["operation"]:
                self._operations[match["operation"]] = match["interaction"]
            if match["stage"] == "paste_terminal":
                self._operations.pop(match["operation"], None)
            self._write(message)
            if match["stage"] == "capture_requested" and self._pending_frame is not None:
                interaction, timestamp = self._pending_frame
                if interaction == self._active:
                    self._write_frame(interaction, timestamp)
                self._pending_frame = None
            return
        dispatched = DISPATCH.fullmatch(message)
        if dispatched is None:
            return
        operation = dispatched["operation"]
        interaction = self._operations.pop(operation, None)
        if interaction is not None:
            self._write(
                f"Inline trace monotonic_ns={self._clock()} stage=paste_dispatched "
                f"interaction_id={interaction} capture_id= operation_id={operation} "
                "mode= outcome=dispatched_unconfirmed"
            )

    def record_frame(self, interaction_id: str) -> None:
        self.acquire()
        try:
            if not interaction_id:
                return
            if interaction_id != self._active:
                if self._shortcut_ns is not None:
                    self._pending_frame = (interaction_id, self._clock())
                return
            if not self._frame_recorded:
                self._write_frame(interaction_id, self._clock())
        finally:
            self.release()

    def _write_frame(self, interaction_id: str, timestamp: int) -> None:
        self._frame_recorded = True
        self._write(
            f"Inline trace monotonic_ns={timestamp} stage=first_frame_visible "
            f"interaction_id={interaction_id} capture_id= operation_id= mode= outcome="
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents a new run from silently appending stale data.
    with args.output.open("x", encoding="utf-8") as output:
        import main as application
        from ClipAI.ui.inline_pill import InlinePill
        from ClipAI.app.runtime_voice_input import VoiceInputRuntimeModule
        from scripts.popup_first_frame_benchmark import _await_presented_frame

        recorder = InlineMeasurementRecorder(output)
        original_build = application.build_runtime
        original_show = InlinePill.show
        original_toggle = VoiceInputRuntimeModule.toggle_inline_dictation
        runtime = None
        loggers = (logging.getLogger("clipai.inline_trace"), logging.getLogger("clipai.paste"))

        def build(*args, **kwargs):
            nonlocal runtime
            runtime = original_build(*args, **kwargs)
            for logger in loggers:
                logger.addHandler(recorder)
            return runtime

        def show(window):
            original_show(window)
            _await_presented_frame(window._window)
            recorder.record_frame(window.interaction_id)

        def toggle(module, *args, **kwargs):
            recorder.begin_shortcut()
            try:
                return original_toggle(module, *args, **kwargs)
            finally:
                recorder.end_shortcut()

        application.build_runtime = build
        InlinePill.show = show
        VoiceInputRuntimeModule.toggle_inline_dictation = toggle
        try:
            application.main()
        except KeyboardInterrupt:
            if runtime is not None:
                runtime.stop()
        finally:
            application.build_runtime = original_build
            InlinePill.show = original_show
            VoiceInputRuntimeModule.toggle_inline_dictation = original_toggle
            for logger in loggers:
                logger.removeHandler(recorder)
            recorder.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
