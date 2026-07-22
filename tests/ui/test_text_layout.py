from __future__ import annotations

import random

from ClipAI.ui.text_layout import DISPLAY_BREAK_HINT, add_display_break_hints, strip_display_break_hints


def _headless_wrap(text: str, available_width: int) -> list[str]:
    """A Tk-independent harness: hints are the only soft-wrap boundaries."""
    lines: list[str] = []
    line = ""
    for token in add_display_break_hints(text).split(DISPLAY_BREAK_HINT):
        if "\n" in token:
            first, *rest = token.split("\n")
            line += first
            lines.append(line)
            line = ""
            for hard_line in rest[:-1]:
                lines.append(hard_line)
            line = rest[-1]
        elif len(line) + len(token) > available_width and line:
            lines.append(line)
            line = token
        else:
            line += token
    if line:
        lines.append(line)
    return lines


def test_mixed_script_text_adds_breaks_without_splitting_ascii_tokens() -> None:
    rendered = add_display_break_hints("這是Clip AI的百分之200測試，網址https://clip.ai/a-b?q=1。")
    assert "這" + DISPLAY_BREAK_HINT + "是" in rendered
    assert "Clip" + DISPLAY_BREAK_HINT not in rendered
    assert "2" + DISPLAY_BREAK_HINT + "0" not in rendered
    assert "0" + DISPLAY_BREAK_HINT + "0" not in rendered
    assert "https" + DISPLAY_BREAK_HINT not in rendered
    assert DISPLAY_BREAK_HINT + "。" not in rendered


def test_punctuation_and_grapheme_sequences_are_not_orphaned() -> None:
    rendered = add_display_break_hints("（表情☺️）微笑AI")
    assert "（" + DISPLAY_BREAK_HINT not in rendered
    assert DISPLAY_BREAK_HINT + "）" not in rendered
    assert "☺" + DISPLAY_BREAK_HINT + "️" not in rendered


def test_short_latin_island_keeps_its_internal_space_when_embedded_in_cjk() -> None:
    rendered = add_display_break_hints("中文AI Tool中文")
    assert "AI" + DISPLAY_BREAK_HINT not in rendered
    assert " " + DISPLAY_BREAK_HINT not in rendered
    assert DISPLAY_BREAK_HINT + " " not in rendered


def test_display_transform_is_idempotent_and_round_trips_arbitrary_mixed_text() -> None:
    alphabet = "中文測試ClipAI 200%.-_/?:@#()[]，。☺️\n"
    randomizer = random.Random(57250)
    for _ in range(250):
        source = "".join(randomizer.choice(alphabet) for _ in range(randomizer.randrange(80)))
        rendered = add_display_break_hints(source)
        assert strip_display_break_hints(rendered) == source
        assert add_display_break_hints(rendered) == rendered


def test_headless_render_harness_fills_mixed_script_lines_at_supported_dpi_scales() -> None:
    examples = (
        "這是一段包含Clip AI與更多中文內容用來驗證換行不會過早留白",
        "表情符號微笑AI以及後續中文內容應該充分利用每一行",
        "百分之200 modifier接著是更多中文內容供換行測試使用",
        "中文AI Tool中文接著是更長的敘述內容以填滿顯示區域",
    )
    for scale in (1.0, 1.33, 2.0):
        width = round(20 * scale)
        for example in examples:
            # Scale the available width with the font: logical line filling is
            # invariant, while the adapter measures physical list indents.
            lines = _headless_wrap(example, width)
            assert all(len(line) >= width - 3 for line in lines[:-1])
