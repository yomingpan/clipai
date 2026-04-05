from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger("clipai.hotkey")

_SHIFTED_DIGIT_MAP = {
    "!": "1",
    "@": "2",
    "#": "3",
    "$": "4",
    "%": "5",
    "^": "6",
    "&": "7",
    "*": "8",
    "(": "9",
    ")": "0",
}


def _normalize_key(key) -> str | None:
    name = getattr(key, "name", None)
    if name:
        if name.startswith("alt"):
            return "alt"
        if name.startswith("shift"):
            return "shift"
        if name.startswith("ctrl"):
            return "ctrl"
        return str(name).lower()

    char = getattr(key, "char", None)
    if char:
        normalized = str(char).lower()
        return _SHIFTED_DIGIT_MAP.get(normalized, normalized)
    return None


def _parse_hotkey(hotkey: str) -> set[str]:
    return {part.strip().lower() for part in hotkey.split("+") if part.strip()}


def _swap_modifier_prefix(hotkey: str, modifier_mode: str) -> str | None:
    normalized = hotkey.strip().lower()
    if not normalized.startswith("alt+shift+"):
        return None
    suffix = normalized[len("alt+shift+") :]
    prefix_map = {
        "alt_shift": "alt+shift+",
        "ctrl_shift": "ctrl+shift+",
        "ctrl_alt": "ctrl+alt+",
    }
    prefix = prefix_map.get((modifier_mode or "alt_shift").lower())
    if not prefix or prefix == "alt+shift+":
        return None
    return f"{prefix}{suffix}"


def expand_hotkeys(hotkey: str, modifier_mode: str = "alt_shift") -> list[str]:
    normalized = hotkey.strip().lower()
    if not normalized:
        return []
    variants = [normalized]
    swapped = _swap_modifier_prefix(normalized, modifier_mode)
    if swapped and swapped not in variants:
        variants.append(swapped)
    return variants


@dataclass
class _HotkeyState:
    timer: threading.Timer | None = None
    long_fired: bool = False


class HotkeyListener:
    def __init__(self, listener) -> None:
        self._listener = listener
        self.running = True

    def stop(self) -> None:
        self.running = False
        self._listener.stop()


def register_hotkeys_with_long_press(
    action_map: dict[str, dict],
    on_press_action: Callable[[str], None],
    on_long_press_action: Callable[[str], None] | None = None,
    *,
    modifier_mode: str = "alt_shift",
    tts_check_fn: Callable[[], bool] | None = None,
    long_press_sec: float = 0.6,
):
    try:
        from pynput import keyboard
    except ImportError as exc:
        raise RuntimeError("pynput is required for desktop hotkey mode") from exc

    hotkeys: list[tuple[str, set[str]]] = []
    for action_id, action in action_map.items():
        hotkey = str(action.get("hotkey") or "").strip()
        for variant in expand_hotkeys(hotkey, modifier_mode=modifier_mode):
            hotkeys.append((action_id, _parse_hotkey(variant)))
            logger.info("[clipai] Registered hotkey %s -> %s", variant, action_id)

    pressed: set[str] = set()
    active: dict[str, _HotkeyState] = {}
    lock = threading.RLock()

    def _fire_normal(action_id: str) -> None:
        logger.info("[clipai] Hotkey triggered: %s", action_id)
        if tts_check_fn and tts_check_fn():
            on_press_action(action_id, tts_output=True)  # type: ignore[misc]
        else:
            on_press_action(action_id)

    def _fire_long(action_id: str) -> None:
        if on_long_press_action is None:
            return
        with lock:
            state = active.get(action_id)
            if state is None:
                return
            state.long_fired = True
        logger.info("[clipai] Hotkey long-press triggered: %s", action_id)
        on_long_press_action(action_id)

    def _on_press(key) -> None:
        token = _normalize_key(key)
        if not token:
            return
        with lock:
            pressed.add(token)
            for action_id, tokens in hotkeys:
                if action_id in active:
                    continue
                if tokens.issubset(pressed):
                    state = _HotkeyState()
                    state.timer = threading.Timer(long_press_sec, lambda aid=action_id: _fire_long(aid))
                    state.timer.daemon = True
                    state.timer.start()
                    active[action_id] = state

    def _on_release(key) -> None:
        token = _normalize_key(key)
        if not token:
            return

        callbacks: list[Callable[[], None]] = []
        with lock:
            pressed.discard(token)
            for action_id, tokens in hotkeys:
                if action_id not in active:
                    continue
                if tokens.issubset(pressed):
                    continue
                state = active.pop(action_id)
                if state.timer:
                    state.timer.cancel()
                if not state.long_fired:
                    callbacks.append(lambda aid=action_id: _fire_normal(aid))

        for callback in callbacks:
            callback()

    listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
    listener.start()
    return HotkeyListener(listener)
