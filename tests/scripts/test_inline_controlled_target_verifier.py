from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.verify_inline_controlled_target import verify


def observation(kind: str, ns: int, *, text: str, pastes: int, clipboard: str = "original", focused: bool = True) -> dict:
    return {
        "kind": kind,
        "run_nonce": "fixed-run",
        "monotonic_ns": ns,
        "target": {
            "sha256": text,
            "utf8_bytes": len(text),
            "matches_expected": text == "expected",
            "paste_count": pastes,
            "foreground_hwnd": 42 if focused else 43,
            "target_hwnd": 42,
            "target_is_foreground": focused,
        },
        "clipboard": {"status": "observed", "formats": [{"id": 13, "bytes": 8, "sha256": clipboard}]},
    }


def delivered() -> list[dict]:
    return [
        observation("ready", 1, text="empty", pastes=0),
        observation("paste_observed", 2, text="expected", pastes=1),
        observation("observation", 3, text="expected", pastes=1),
    ]


def test_controlled_target_verifier_requires_actual_readback() -> None:
    report = verify(delivered(), scenario="delivery")

    assert report["status"] == "pass"
    assert report["scope"] == "controlled_target_readback"
    assert set(report["checks"].values()) == {"pass"}
    assert "expected" not in str(report)


def test_freeform_delivery_checks_nonempty_stable_insertion_without_claiming_accuracy() -> None:
    records = delivered()
    records[0]["target"]["utf8_bytes"] = 0
    records[1]["target"]["matches_expected"] = False
    records[2]["target"]["matches_expected"] = False

    report = verify(records, scenario="delivery", text_policy="nonempty")
    assert report["status"] == "pass"
    assert report["checks"]["target_text"] == "pass"
    assert report["content_accuracy"] == "not_machine_verified"

    records[2]["target"]["sha256"] = "different_after_paste"
    assert verify(records, scenario="delivery", text_policy="nonempty")["checks"]["target_text"] == "fail"

    records[2]["target"]["sha256"] = "expected"
    records[2]["target"]["utf8_bytes"] = 0
    assert verify(records, scenario="delivery", text_policy="nonempty")["checks"]["target_text"] == "fail"


def test_cancel_succeeds_only_when_target_and_clipboard_stay_unchanged() -> None:
    report = verify([
        observation("ready", 1, text="original", pastes=0),
        observation("observation", 3, text="original", pastes=0),
    ], scenario="cancel")

    assert report["status"] == "pass"


@pytest.mark.parametrize("mutation,failed_check", [
    ("wrong_text", "target_text"),
    ("duplicate_paste", "paste_count"),
    ("clipboard_changed", "clipboard_restored"),
    ("wrong_focus", "paste_target_focus"),
    ("late_paste", "no_late_paste"),
])
def test_mutations_cannot_pass_target_oracle(mutation: str, failed_check: str) -> None:
    records = deepcopy(delivered())
    if mutation == "wrong_text":
        records[-1]["target"]["matches_expected"] = False
    elif mutation == "duplicate_paste":
        records.insert(2, observation("paste_observed", 2, text="expected", pastes=2))
        records[-1]["target"]["paste_count"] = 2
    elif mutation == "clipboard_changed":
        records[-1]["clipboard"]["formats"][0]["sha256"] = "changed"
    elif mutation == "wrong_focus":
        records[1]["target"]["target_is_foreground"] = False
        records[1]["target"]["foreground_hwnd"] = 43
    elif mutation == "late_paste":
        records.append(observation("paste_observed", 4, text="expected", pastes=2))

    report = verify(records, scenario="delivery")

    assert report["status"] == "fail"
    assert report["checks"][failed_check] == "fail"


def test_missing_terminal_readback_and_unavailable_foreground_are_blocked() -> None:
    assert verify(delivered()[:-1], scenario="delivery")["status"] == "blocked"
    records = delivered()
    records[1]["target"]["foreground_hwnd"] = 0
    records[1]["target"]["target_is_foreground"] = False
    report = verify(records, scenario="delivery")

    assert report["status"] == "blocked"
    assert report["checks"]["paste_target_focus"] == "blocked"
