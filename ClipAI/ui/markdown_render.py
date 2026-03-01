from __future__ import annotations

import markdown


def render_markdown_to_html(text: str) -> str:
    return markdown.markdown(text)
