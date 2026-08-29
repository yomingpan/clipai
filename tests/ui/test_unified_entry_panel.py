from ClipAI.core.commands import (
    EntryPanelActionSelected,
    EntryPanelEscape,
    EntryPanelSlotSelected,
    EntryPanelToggleDensity,
)
from ClipAI.core.models import EntryActionRef, EntryPanelOption, EntryPanelSnapshot
from ClipAI.ui.unified_entry_panel import EntryPanelIntentAdapter, UnifiedEntryPanelDialog


def test_intent_adapter_emits_typed_mouse_and_keyboard_commands() -> None:
    commands = []
    adapter = EntryPanelIntentAdapter(commands.append)
    action = EntryActionRef("shorten_content", "short")
    snapshot = EntryPanelSnapshot(
        "panel-1",
        "scene",
        options=(EntryPanelOption(1, "縮短內容", action=action),),
    )
    adapter.apply(snapshot)

    adapter.select(snapshot.options[0])
    adapter.select_slot(2)
    adapter.toggle_density()
    adapter.escape()

    assert commands == [
        EntryPanelActionSelected("panel-1", action),
        EntryPanelSlotSelected("panel-1", 2),
        EntryPanelToggleDensity("panel-1"),
        EntryPanelEscape("panel-1"),
    ]


def test_disabled_option_does_not_emit_action_intent() -> None:
    commands = []
    adapter = EntryPanelIntentAdapter(commands.append)
    option = EntryPanelOption(
        1,
        "Unavailable",
        action=EntryActionRef("shorten_content", "short"),
        enabled=False,
        disabled_reason="Provider is busy",
    )
    adapter.apply(EntryPanelSnapshot("panel-1", "scene", options=(option,)))

    adapter.select(option)

    assert commands == []


def test_projection_text_respects_density_and_keeps_disabled_reason() -> None:
    option = EntryPanelOption(
        1,
        "縮短內容",
        "保留意思並縮短篇幅",
        enabled=False,
        disabled_reason="AI 正在回答",
    )

    detailed = UnifiedEntryPanelDialog._option_text(
        option,
        EntryPanelSnapshot("panel-1", "scene", density="detailed"),
    )
    compact = UnifiedEntryPanelDialog._option_text(
        option,
        EntryPanelSnapshot("panel-1", "scene", density="compact"),
    )

    assert "保留意思並縮短篇幅" in detailed
    assert "保留意思並縮短篇幅" not in compact
    assert "AI 正在回答" in detailed
    assert "AI 正在回答" in compact
