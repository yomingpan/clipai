from __future__ import annotations

from ClipAI.core.errors import PASTE_FAILURE_MESSAGES, PasteFailure


def test_every_paste_failure_reason_has_a_unique_user_message() -> None:
    expected = {
        "no_target_observed",
        "target_gone",
        "target_refused_focus",
        "target_focus_timeout",
        "target_changed",
        "modifiers_held",
        "another_paste_active",
        "clipboard_unavailable",
        "unknown",
    }

    assert set(PASTE_FAILURE_MESSAGES) == expected
    assert len(set(PASTE_FAILURE_MESSAGES.values())) == len(expected)


def test_paste_failure_retains_typed_reason_without_parsing_message() -> None:
    failure = PasteFailure("target_changed", "opaque localized message")

    assert failure.reason == "target_changed"
    assert str(failure) == "opaque localized message"
