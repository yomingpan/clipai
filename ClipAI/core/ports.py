from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from ClipAI.core.models import ApplicationStatus, LLMRequest, LLMResult, OperationKind
from ClipAI.core.state import CancellationToken, SessionSnapshot


class LLMProvider(Protocol):
    def complete(self, request: LLMRequest, cancellation: CancellationToken) -> LLMResult: ...


class ClipboardReader(Protocol):
    def read_text(self) -> str: ...


class ClipboardWriter(Protocol):
    def write_text(self, text: str) -> None: ...


class ClipboardStore(ClipboardReader, ClipboardWriter, Protocol):
    pass


class SelectionReader(Protocol):
    def read_text(self) -> str: ...


class ResultPresenter(Protocol):
    def render(self, snapshot: SessionSnapshot) -> None: ...


class ApplicationView(ResultPresenter, Protocol):
    def set_command_sink(self, sink: Callable[[object], None]) -> None: ...

    def run(self, command_pump: Callable[[], None]) -> None: ...

    def stop(self) -> None: ...


class ArchiveStore(Protocol):
    def save(self, text: str) -> None: ...


class SpeechOutput(Protocol):
    def speak(self, text: str) -> None: ...

    def stop(self) -> None: ...


class KeyboardOutput(Protocol):
    def paste(self) -> None: ...


class StatusIndicator(Protocol):
    def set_status(self, status: ApplicationStatus) -> None: ...

    def set_memory_active(self, active: bool) -> None: ...


class OperationHandle(Protocol):
    def succeed(self) -> None: ...

    def fail(self) -> None: ...

    def cancel(self) -> None: ...


class OperationTracker(Protocol):
    def start(self, operation_id: str, kind: OperationKind) -> OperationHandle: ...


class UserNotifier(Protocol):
    def notify(self, title: str, message: str) -> None: ...


class DiagnosticsExporter(Protocol):
    def export(self) -> Path: ...
