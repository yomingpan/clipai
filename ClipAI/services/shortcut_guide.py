from __future__ import annotations

from dataclasses import dataclass, replace

from ClipAI.core.commands import ShortcutAttemptRejected, ShortcutInputEvent, ShortcutKeyStateChanged, ShortcutPressEnded, ShortcutPressInvoked, ShortcutPressStarted
from ClipAI.core.hotkeys import MODIFIER_KEYS, canonicalize_hotkey, display_hotkey, parse_hotkey_tokens
from ClipAI.core.models import ShortcutGuideItem, ShortcutGuidePhase, ShortcutGuideSnapshot, ShortcutObservationSnapshot, ShortcutPressId
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.shortcut_catalog import ShortcutCatalog


_SPEECH_SHORT_TITLE = "朗讀選取文字或剪貼簿"
_SPEECH_SHORT_DESCRIPTION = "朗讀目前選取的文字；朗讀中再次觸發會改讀最新選取。Esc 短按關閉目前面板或停止最後啟動的操作，長按停止全部內容工作。"
_SPEECH_LONG_TITLE = "語音快捷鍵組合"
_SPEECH_LONG_DESCRIPTION = "長按後再按另一個 Action 快捷鍵，將該次結果以語音輸出。"


class ShortcutGuideCatalog:
    def __init__(
        self,
        shortcuts: ShortcutCatalog,
        actions: ActionCatalog,
        *,
        modifier_mode: str,
    ) -> None:
        self._shortcuts = shortcuts
        self._actions = actions
        self._modifier_mode = modifier_mode

    def items(self) -> tuple[ShortcutGuideItem, ...]:
        return tuple(self._item(definition) for definition in self._shortcuts.definitions())

    def _item(self, definition) -> ShortcutGuideItem:
        hotkey = canonicalize_hotkey(definition.hotkey, self._modifier_mode)
        if definition.command == "speak_selection_or_clipboard":
            return ShortcutGuideItem(
                definition.id,
                hotkey,
                display_hotkey(hotkey),
                parse_hotkey_tokens(hotkey),
                _SPEECH_SHORT_TITLE,
                _SPEECH_SHORT_DESCRIPTION,
                _SPEECH_LONG_TITLE,
                _SPEECH_LONG_DESCRIPTION,
            )

        if definition.command == "push_to_talk":
            return ShortcutGuideItem(
                definition.id,
                hotkey,
                display_hotkey(hotkey),
                parse_hotkey_tokens(hotkey),
                "Voice Input",
                "Hold to dictate; release to review before pasting.",
            )

        assert definition.action_id is not None
        action = self._actions.get(definition.action_id)
        short = self._actions.resolve(definition.action_id, "short")
        short_description = short.feedback_contract.ai_help_label if short.feedback_contract else short.name
        long_title = ""
        long_description = ""
        if "long" in action.press_variants:
            long = self._actions.resolve(definition.action_id, "long")
            long_title = long.name
            long_description = long.feedback_contract.ai_help_label if long.feedback_contract else long.name
        return ShortcutGuideItem(
            definition.id,
            hotkey,
            display_hotkey(hotkey),
            parse_hotkey_tokens(hotkey),
            short.name,
            short_description,
            long_title,
            long_description,
        )


@dataclass(frozen=True)
class ShortcutGuideDecision:
    consumed: bool
    snapshot: ShortcutGuideSnapshot | None = None


class ShortcutGuideCoordinator:
    """Owns shortcut-guide state and the quarantine for captured Shortcut Presses."""

    def __init__(self) -> None:
        self._snapshot: ShortcutGuideSnapshot | None = None
        self._captured_presses: set[ShortcutPressId] = set()

    @property
    def snapshot(self) -> ShortcutGuideSnapshot | None:
        return self._snapshot

    def open(
        self,
        guide_id: str,
        items: tuple[ShortcutGuideItem, ...],
        observation: ShortcutObservationSnapshot = ShortcutObservationSnapshot(),
    ) -> ShortcutGuideSnapshot:
        if self._snapshot is not None:
            return self._snapshot
        self._captured_presses.update(
            active.press_id for active in observation.active_presses
        )
        selected = items[0].shortcut_id if items else ""
        selected_item = items[0] if items else None
        phase: ShortcutGuidePhase = (
            "keys_pressed" if observation.pressed_keys else "listening"
        )
        status = (
            self._progress_status(observation.pressed_keys, selected_item)
            if observation.pressed_keys
            else self._idle_status(selected_item)
        )
        self._snapshot = ShortcutGuideSnapshot(
            guide_id,
            items,
            selected,
            pressed_keys=observation.pressed_keys,
            phase=phase,
            status_text=status,
        )
        return self._snapshot

    def close(self, guide_id: str = "") -> bool:
        if self._snapshot is None or (guide_id and guide_id != self._snapshot.guide_id):
            return False
        self._snapshot = None
        return True

    def select(self, shortcut_id: str) -> ShortcutGuideSnapshot | None:
        snapshot = self._snapshot
        if snapshot is None or not any(item.shortcut_id == shortcut_id for item in snapshot.items):
            return snapshot
        self._snapshot = replace(snapshot, selected_shortcut_id=shortcut_id)
        return self._snapshot

    def handle(self, event: ShortcutInputEvent) -> ShortcutGuideDecision:
        snapshot = self._snapshot
        if isinstance(event, ShortcutPressStarted):
            if snapshot is None:
                return ShortcutGuideDecision(False)
            self._captured_presses.add(event.press_id)
            return ShortcutGuideDecision(True, snapshot)
        if isinstance(event, ShortcutPressEnded):
            captured = event.press_id in self._captured_presses
            self._captured_presses.discard(event.press_id)
            return ShortcutGuideDecision(captured, snapshot if captured else None)
        if isinstance(event, ShortcutKeyStateChanged):
            if snapshot is None:
                return ShortcutGuideDecision(False)
            phase: ShortcutGuidePhase = (
                "listening" if not event.pressed_keys else "keys_pressed"
            )
            selected = next(
                (
                    item
                    for item in snapshot.items
                    if item.shortcut_id == snapshot.selected_shortcut_id
                ),
                None,
            )
            status = (
                self._idle_status(selected)
                if phase == "listening"
                else self._progress_status(event.pressed_keys, selected)
            )
            self._snapshot = replace(
                snapshot,
                pressed_keys=event.pressed_keys,
                phase=phase,
                status_text=status,
            )
            return ShortcutGuideDecision(True, self._snapshot)
        if isinstance(event, ShortcutAttemptRejected):
            if snapshot is None:
                return ShortcutGuideDecision(False)
            self._snapshot = replace(
                snapshot,
                phase="invalid",
                status_text="ClipAI 有收到按鍵，但目前沒有對應功能。",
                matched_shortcut_id="",
                matched_press_type=None,
            )
            return ShortcutGuideDecision(True, self._snapshot)
        if not isinstance(event, ShortcutPressInvoked):
            return ShortcutGuideDecision(False)
        captured = event.press_id in self._captured_presses
        if not captured:
            return ShortcutGuideDecision(False)
        if snapshot is None:
            return ShortcutGuideDecision(True)
        item = next(
            (item for item in snapshot.items if item.shortcut_id == event.shortcut_id),
            None,
        )
        if item is None:
            return ShortcutGuideDecision(True, snapshot)
        press_type = event.press_type
        description = item.long_title if press_type == "long" and item.long_title else item.title
        self._snapshot = replace(
            snapshot,
            selected_shortcut_id=item.shortcut_id,
            verified=snapshot.verified | {(item.shortcut_id, press_type)},
            phase="recognized",
            status_text=f"已驗證 {item.display_hotkey}（{'長按' if press_type == 'long' else '短按'}）→ {description}",
            matched_shortcut_id=item.shortcut_id,
            matched_press_type=press_type,
        )
        return ShortcutGuideDecision(True, self._snapshot)

    @staticmethod
    def _modifier_label(item: ShortcutGuideItem | None) -> str:
        if item is None:
            return "修飾鍵"
        parts = item.display_hotkey.split(" + ")
        return " + ".join(parts[:-1]) or item.display_hotkey

    @classmethod
    def _idle_status(cls, item: ShortcutGuideItem | None) -> str:
        return f"請按住 {cls._modifier_label(item)}，再按一個功能鍵。"

    @classmethod
    def _progress_status(cls, pressed_keys: frozenset[str], item: ShortcutGuideItem | None) -> str:
        if item is None:
            return "請按住快捷鍵組合。"
        required = item.key_tokens & MODIFIER_KEYS
        missing = required - pressed_keys
        if missing:
            labels = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift"}
            missing_label = " + ".join(labels[token] for token in ("ctrl", "alt", "shift") if token in missing)
            return f"已偵測部分組合；請再按住 {missing_label}。"
        return f"已偵測 {cls._modifier_label(item)}；請再按一個功能鍵。"
