from __future__ import annotations

from dataclasses import dataclass, replace

from ClipAI.core.commands import ShortcutGestureProgressed, ShortcutTriggered
from ClipAI.core.hotkeys import MODIFIER_KEYS, canonicalize_hotkey, display_hotkey, parse_hotkey_tokens
from ClipAI.core.models import PressType, ShortcutGuideItem, ShortcutGuideSnapshot
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.shortcut_catalog import ShortcutCatalog


_SPEECH_SHORT_TITLE = "朗讀選取文字或剪貼簿"
_SPEECH_SHORT_DESCRIPTION = "朗讀目前選取的文字；沒有可用選取內容時改用剪貼簿。"
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

        assert definition.action_id is not None
        action = self._actions.get(definition.action_id)
        short = self._actions.resolve(definition.action_id, "short")
        short_description = short.feedback_contract.transform_label if short.feedback_contract else short.name
        long_title = ""
        long_description = ""
        if "long" in action.press_variants:
            long = self._actions.resolve(definition.action_id, "long")
            long_title = long.name
            long_description = long.feedback_contract.transform_label if long.feedback_contract else long.name
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
    close_requested: bool = False


class ShortcutGuideCoordinator:
    """Owns shortcut-guide state and the quarantine for captured gestures."""

    def __init__(self) -> None:
        self._snapshot: ShortcutGuideSnapshot | None = None
        self._captured_gestures: set[int] = set()

    @property
    def snapshot(self) -> ShortcutGuideSnapshot | None:
        return self._snapshot

    def wants_progress(self, gesture_id: int) -> bool:
        return self._snapshot is not None or gesture_id in self._captured_gestures

    def open(self, guide_id: str, items: tuple[ShortcutGuideItem, ...]) -> ShortcutGuideSnapshot:
        if self._snapshot is not None:
            return self._snapshot
        selected = items[0].shortcut_id if items else ""
        status = self._idle_status(items[0] if items else None)
        self._snapshot = ShortcutGuideSnapshot(guide_id, items, selected, status_text=status)
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

    def observe(self, event: ShortcutGestureProgressed) -> ShortcutGuideSnapshot | None:
        snapshot = self._snapshot
        if snapshot is not None and event.gesture_id:
            self._captured_gestures.add(event.gesture_id)
        if snapshot is not None:
            if event.ended and snapshot.phase in {"recognized", "invalid"}:
                self._snapshot = replace(snapshot, pressed_keys=frozenset())
            else:
                phase = "listening" if event.ended or not event.pressed_keys else "keys_pressed"
                selected = next((item for item in snapshot.items if item.shortcut_id == snapshot.selected_shortcut_id), None)
                status = self._idle_status(selected) if phase == "listening" else self._progress_status(event.pressed_keys, selected)
                self._snapshot = replace(snapshot, pressed_keys=event.pressed_keys, phase=phase, status_text=status)
        if event.ended:
            self._captured_gestures.discard(event.gesture_id)
        return self._snapshot

    def consume(self, trigger: ShortcutTriggered) -> ShortcutGuideDecision:
        snapshot = self._snapshot
        captured = bool(trigger.gesture_id and trigger.gesture_id in self._captured_gestures)
        if snapshot is None and not captured:
            return ShortcutGuideDecision(False)
        if snapshot is None:
            return ShortcutGuideDecision(True)
        if trigger.press_type == "cancel":
            self._snapshot = None
            return ShortcutGuideDecision(True, close_requested=True)
        if trigger.press_type == "invalid":
            self._snapshot = replace(
                snapshot,
                phase="invalid",
                status_text="ClipAI 有收到按鍵，但目前沒有對應功能。",
                matched_shortcut_id="",
                matched_press_type=None,
            )
            return ShortcutGuideDecision(True, self._snapshot)
        if trigger.press_type == "long_release":
            return ShortcutGuideDecision(True, snapshot)
        item = next((item for item in snapshot.items if item.shortcut_id == trigger.shortcut_id), None)
        if item is None:
            return ShortcutGuideDecision(True, snapshot)
        press_type: PressType = "long" if trigger.press_type == "long" else "short"
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
