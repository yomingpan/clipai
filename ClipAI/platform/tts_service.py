from __future__ import annotations

import re
import threading
import time
from typing import Callable

from clipai.core.constants import EVENT_TTS_STATE
from clipai.core.event_bus import EventBus


class TTSService:
    def __init__(
        self,
        event_bus: EventBus,
        speak_fn: Callable[[str], None],
        *,
        stop_fn: Callable[[], bool] | None = None,
        is_speaking_fn: Callable[[], bool] | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._speak_fn = speak_fn
        self._stop_fn = stop_fn
        self._is_speaking_fn = is_speaking_fn

    def _emit_state(self, is_speaking: bool, phase: str) -> None:
        self._event_bus.publish(EVENT_TTS_STATE, {"is_speaking": is_speaking, "phase": phase})

    def _normalize_for_speech(self, text: str) -> str:
        normalized = text
        for step in (
            self._strip_fenced_code_blocks,
            self._replace_markdown_links,
            self._strip_inline_markdown,
            self._normalize_headings_and_hashes,
            self._normalize_bullets_and_dividers,
            self._normalize_brackets,
            self._normalize_spacing,
        ):
            normalized = step(normalized)
        return normalized.strip()

    @staticmethod
    def _strip_fenced_code_blocks(text: str) -> str:
        return re.sub(r"```[\s\S]*?```", " ", text)

    @staticmethod
    def _replace_markdown_links(text: str) -> str:
        return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)

    @staticmethod
    def _strip_inline_markdown(text: str) -> str:
        normalized = re.sub(r"`([^`]+)`", r"\1", text)
        normalized = re.sub(r"(\*\*|__)(.+?)\1", r"\2", normalized)
        normalized = re.sub(r"(~~|\*)(.+?)\1", r"\2", normalized)
        normalized = re.sub(r"(^|\s)[*_~]+(?=\s|$)", " ", normalized)
        return normalized

    @staticmethod
    def _normalize_headings_and_hashes(text: str) -> str:
        lines: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            stripped = line.lstrip()
            if re.match(r"^#{1,6}\s+", stripped):
                lines.append(re.sub(r"^#{1,6}\s+", "", stripped))
                continue
            if re.fullmatch(r"#+", stripped):
                continue
            lines.append(line)
        normalized = "\n".join(lines)
        normalized = re.sub(r"(?<![A-Za-z0-9])#(?=\s|$)", " ", normalized)
        return normalized

    @staticmethod
    def _normalize_bullets_and_dividers(text: str) -> str:
        lines: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                lines.append("")
                continue
            if re.fullmatch(r"[-=*•·\s]{3,}", line):
                continue
            line = re.sub(r"^[-*•·]+\s+", "", line)
            line = re.sub(r"^\d+\.\s+", "", line)
            line = re.sub(r"\s[-–—]{2,}\s", " ", line)
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _normalize_brackets(text: str) -> str:
        normalized = re.sub(r"\(\s*\)|\[\s*\]|\{\s*\}|<\s*>", " ", text)
        normalized = re.sub(r"[\[\]{}()<>]", " ", normalized)
        return normalized

    @staticmethod
    def _normalize_spacing(text: str) -> str:
        normalized = re.sub(r"[ \t]+", " ", text)
        normalized = re.sub(r" *\n *", "\n", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized

    def speak(self, text: str, cancellation_token=None) -> None:
        cleaned = self._normalize_for_speech(text)
        if not cleaned:
            return
        try:
            for _ in range(2):
                if cancellation_token and cancellation_token.is_cancelled():
                    self._emit_state(False, "stop")
                    return
                time.sleep(0.01)
            if self._invoke_with_callbacks(cleaned):
                return
            self._emit_state(True, "start")
            self._speak_fn(cleaned)
            self._emit_state(False, "end")
        except Exception:
            self._emit_state(False, "error")
            raise

    def speak_async(self, text: str, cancellation_token=None) -> threading.Thread:
        thread = threading.Thread(target=self.speak, args=(text, cancellation_token), daemon=True)
        thread.start()
        return thread

    def stop(self) -> bool:
        if self._stop_fn is None:
            return False
        stopped = bool(self._stop_fn())
        if stopped:
            self._emit_state(False, "stop")
        return stopped

    def is_speaking(self) -> bool:
        if self._is_speaking_fn is None:
            return False
        try:
            return bool(self._is_speaking_fn())
        except Exception:
            return False

    def toggle_async(self, text: str, cancellation_token=None) -> bool:
        if self.is_speaking():
            self.stop()
            return False
        self.speak_async(text, cancellation_token=cancellation_token)
        return True

    def _invoke_with_callbacks(self, cleaned: str) -> bool:
        def on_start() -> None:
            self._emit_state(True, "start")

        def on_end() -> None:
            self._emit_state(False, "end")

        try:
            self._speak_fn(cleaned, on_start=on_start, on_end=on_end)
            return True
        except TypeError as exc:
            if "on_start" not in str(exc) and "on_end" not in str(exc):
                raise
            return False
