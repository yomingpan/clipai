from ClipAI.core.models import (
    ActionLanguagePackDescriptor,
    ActionLanguagePackIdentity,
    ActionLanguagePackRecovery,
    ActionLanguagePackSelectionState,
)
from ClipAI.services.action_language_selection import (
    ActionLanguageSelectionCoordinator,
)


ZH = ActionLanguagePackIdentity("zh-TW", "1.0.0", "zh-TW")
JA = ActionLanguagePackIdentity("ja-JP", "1.0.0", "ja-JP")


def _state(
    *,
    selected: str = "zh-TW",
    recovery: ActionLanguagePackRecovery | None = None,
) -> ActionLanguagePackSelectionState:
    return ActionLanguagePackSelectionState(
        available_packs=(
            ActionLanguagePackDescriptor(ZH, "繁體中文"),
            ActionLanguagePackDescriptor(JA, "日本語"),
        ),
        active_pack=ZH,
        selected_pack_id=selected,
        recovery=recovery,
    )


def test_success_changes_only_next_start_selection_and_requires_restart() -> None:
    coordinator = ActionLanguageSelectionCoordinator(_state())

    started = coordinator.begin("ja-JP", "operation-1")
    completed = coordinator.complete("operation-1", "ja-JP")

    assert started.state.pending_pack_id == "ja-JP"
    assert started.state.selected_pack_id == "zh-TW"
    assert completed.state.active_pack == ZH
    assert completed.state.selected_pack_id == "ja-JP"
    assert completed.state.restart_required is True


def test_failure_keeps_previous_selection_and_active_pack() -> None:
    coordinator = ActionLanguageSelectionCoordinator(_state())
    coordinator.begin("ja-JP", "operation-1")

    completed = coordinator.complete(
        "operation-1",
        "ja-JP",
        "checksum_mismatch",
    )

    assert completed.state.active_pack == ZH
    assert completed.state.selected_pack_id == "zh-TW"
    assert completed.state.pending_pack_id is None
    assert "previous selection remains" in completed.state.message


def test_pending_operation_blocks_another_intent_and_stale_completion() -> None:
    coordinator = ActionLanguageSelectionCoordinator(_state())
    coordinator.begin("ja-JP", "operation-1")

    second = coordinator.begin("zh-TW", "operation-2")
    stale = coordinator.complete("operation-2", "zh-TW")

    assert second.ignored is True
    assert stale.ignored is True
    assert coordinator.state.pending_pack_id == "ja-JP"


def test_unavailable_pack_never_creates_work() -> None:
    coordinator = ActionLanguageSelectionCoordinator(_state())

    update = coordinator.begin("missing", "operation-1")

    assert update.work is None
    assert update.state.pending_pack_id is None
    assert update.state.selected_pack_id == "zh-TW"


def test_successfully_selecting_active_default_clears_recovery() -> None:
    recovery = ActionLanguagePackRecovery(
        "missing",
        "pack_missing",
        "action_language_pack.pack_missing",
    )
    coordinator = ActionLanguageSelectionCoordinator(
        _state(selected="missing", recovery=recovery)
    )

    coordinator.begin("zh-TW", "operation-1")
    completed = coordinator.complete("operation-1", "zh-TW")

    assert completed.state.active_pack == ZH
    assert completed.state.selected_pack_id == "zh-TW"
    assert completed.state.restart_required is False
    assert completed.state.recovery is None
