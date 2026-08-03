"""Pure display-only line-break hints for Tk's limited word wrapper."""

from __future__ import annotations

import re
import unicodedata

# Tk's ``word`` wrapping on Windows only treats ASCII whitespace as a reliable
# break. Invisible separators make that space reversible in canonical text.
DISPLAY_BREAK_HINT = "\u2063 \u2063"
LATIN_ISLAND_MAX_CHARS = 12
_ASCII_TOKEN = frozenset("._-:/?&=#%@+~")
_OPENING_PUNCTUATION = frozenset("([{<（〔［｛〈《「『【〖")
_CLOSING_PUNCTUATION = frozenset(")]}>）〕］｝〉》」』、】【〗、，。！？；：")
_LATIN_ISLAND = re.compile(r"[A-Za-z0-9]+(?:[ \t]+[A-Za-z0-9]+)*")


def strip_display_break_hints(text: str) -> str:
    """Return canonical text from a display-only representation."""
    return text.replace(DISPLAY_BREAK_HINT, "")


def strip_display_break_hint_boundaries(
    text: str,
    *,
    leading: bool = False,
    trailing: bool = False,
) -> str:
    """Remove complete hints plus fragments cut by a Tk selection boundary."""
    if leading and not text.startswith(DISPLAY_BREAK_HINT):
        for start in range(1, len(DISPLAY_BREAK_HINT)):
            fragment = DISPLAY_BREAK_HINT[start:]
            if text.startswith(fragment):
                text = text[len(fragment):]
                break
    if trailing and not text.endswith(DISPLAY_BREAK_HINT):
        for end in range(len(DISPLAY_BREAK_HINT) - 1, 0, -1):
            fragment = DISPLAY_BREAK_HINT[:end]
            if text.endswith(fragment):
                text = text[:-len(fragment)]
                break
    return strip_display_break_hints(text)


def add_display_break_hints(text: str) -> str:
    """Add reversible Tk break opportunities without changing semantic text."""
    canonical = strip_display_break_hints(text)
    protected_spaces = _embedded_latin_space_boundaries(canonical)
    rendered: list[str] = []
    for index, char in enumerate(canonical):
        rendered.append(char)
        if index + 1 < len(canonical) and display_break_opportunity(
            char, canonical[index + 1], index=index, protected_spaces=protected_spaces
        ):
            rendered.append(DISPLAY_BREAK_HINT)
    return "".join(rendered)


def display_break_opportunity(left: str, right: str, *, index: int = -1, protected_spaces: frozenset[int] = frozenset()) -> bool:
    """Whether a display hint may sit between adjacent canonical characters."""
    if left == "\n" or right == "\n" or index in protected_spaces:
        return False
    if _joins_grapheme(left, right):
        return False
    if left in _OPENING_PUNCTUATION or right in _CLOSING_PUNCTUATION:
        return False
    return not (_is_ascii_token_char(left) and _is_ascii_token_char(right))


def _is_ascii_token_char(char: str) -> bool:
    return char.isascii() and (char.isalnum() or char in _ASCII_TOKEN)


def _joins_grapheme(left: str, right: str) -> bool:
    return (left == "\u200d" or right == "\u200d" or unicodedata.combining(right) != 0
            or "VARIATION SELECTOR" in unicodedata.name(right, "")
            or "VARIATION SELECTOR" in unicodedata.name(left, ""))


def _embedded_latin_space_boundaries(text: str) -> frozenset[int]:
    protected: set[int] = set()
    for match in _LATIN_ISLAND.finditer(text):
        island = match.group(0)
        if len(island) > LATIN_ISLAND_MAX_CHARS or not any(char.isspace() for char in island):
            continue
        before = text[match.start() - 1] if match.start() else ""
        after = text[match.end()] if match.end() < len(text) else ""
        if _is_cjk(before) and _is_cjk(after):
            for offset, char in enumerate(island):
                if char.isspace():
                    boundary = match.start() + offset
                    protected.update((boundary - 1, boundary))
    return frozenset(protected)


def _is_cjk(char: str) -> bool:
    codepoint = ord(char) if char else 0
    return 0x3400 <= codepoint <= 0x4DBF or 0x4E00 <= codepoint <= 0x9FFF or 0xF900 <= codepoint <= 0xFAFF
