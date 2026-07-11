from __future__ import annotations

import re


class SpeechTextPreprocessor:
    """Convert display Markdown into concise, speakable text."""

    _LINK = re.compile(r"\[([^\]]+)\]\([^\s)]+\)")
    _BARE_URL = re.compile(r"https?://\S+")
    _LIST_PREFIX = re.compile(r"^\s*(?:[-*+] |\d+[.)]\s+)")
    _HEADING_PREFIX = re.compile(r"^\s{0,3}#{1,6}\s+")
    _EMPHASIS = re.compile(r"(?<!\w)(?:\*{1,3}|_{1,3})|(?:\*{1,3}|_{1,3})(?!\w)")

    def prepare(self, text: str) -> str:
        lines: list[str] = []
        in_fence = False
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            line = self._HEADING_PREFIX.sub("", raw_line)
            line = self._LIST_PREFIX.sub("", line)
            line = self._LINK.sub(r"\1", line)
            line = self._BARE_URL.sub("", line)
            line = self._EMPHASIS.sub("", line)
            line = re.sub(r"\s+", " ", line).strip()
            if line:
                lines.append(line)
        return "\n".join(lines)
