from ClipAI.services.presentation import MarkdownPresentationParser


def test_supported_markdown_becomes_typed_blocks_and_spans() -> None:
    document = MarkdownPresentationParser().parse(
        "# Title\n\nA **bold** and *soft* paragraph.\n\n- First\n2. Second"
    )
    assert [block.kind for block in document.blocks] == [
        "heading", "paragraph", "unordered_item", "ordered_item"
    ]
    assert document.blocks[0].level == 1
    assert [(span.text, span.style) for span in document.blocks[1].spans] == [
        ("A ", "plain"), ("bold", "bold"), (" and ", "plain"),
        ("soft", "italic"), (" paragraph.", "plain")
    ]
    assert document.blocks[-1].ordinal == 2


def test_unsupported_indented_syntax_remains_readable_plain_text() -> None:
    document = MarkdownPresentationParser().parse("Paragraph\n    unsupported nested content")
    assert document.fallback_text == "Paragraph\n    unsupported nested content"
    assert "unsupported nested content" in document.blocks[0].spans[0].text


def test_compact_learning_lines_remain_on_separate_lines() -> None:
    text = "appetizer\n餐前小點\nLet's order appetizers.\nSynonym: starter"
    document = MarkdownPresentationParser().parse(text)
    assert document.blocks[0].spans[0].text == text
