from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable

from clipai.logging_setup import diagnostics_enabled

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

_VK_DIGIT_MAP = {code: str(code - 48) for code in range(48, 58)}
_VK_NUMPAD_MAP = {code: str(code - 96) for code in range(96, 106)}
_VK_ALPHA_MAP = {code: chr(code).lower() for code in range(65, 91)}


def _describe_key(key) -> str:
    name = getattr(key, "name", None)
    char = getattr(key, "char", None)
    vk = getattr(key, "vk", None)
    return f"name={name!r} char={char!r} vk={vk!r} type={type(key).__name__}"


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

    vk = getattr(key, "vk", None)
    if isinstance(vk, int):
        if vk in _VK_DIGIT_MAP:
            return _VK_DIGIT_MAP[vk]
        if vk in _VK_NUMPAD_MAP:
            return _VK_NUMPAD_MAP[vk]
        if vk in _VK_ALPHA_MAP:
            return _VK_ALPHA_MAP[vk]
    return None


def _parse_hotkey(hotkey: str) -> set[str]:
    return {part.strip().lower() for part in hotkey.split("+") if part.strip()}


def _canonicalize_modifier_prefix(hotkey: str, modifier_mode: str) -> str:
    normalized = hotkey.strip().lower()
    prefix_map = {
        "alt_shift": ("alt+shift+", "alt+shift+"),
        "ctrl_shift": ("ctrl+shift+", "ctrl+shift+"),
        "ctrl_alt": ("ctrl+alt+", "ctrl+alt+"),
    }
    default_prefix, canonical_prefix = prefix_map.get((modifier_mode or "ctrl_alt").lower(), ("ctrl+alt+", "ctrl+alt+"))
    for prefix in ("alt+shift+", "ctrl+shift+", "ctrl+alt+"):
        if normalized.startswith(prefix):
            suffix = normalized[len(prefix) :]
            return f"{canonical_prefix}{suffix}"
    if "+" not in normalized:
        return f"{default_prefix}{normalized}"
    return normalized


def expand_hotkeys(hotkey: str, modifier_mode: str = "ctrl_alt") -> list[str]:
    normalized = hotkey.strip().lower()
    if not normalized:
        return []
    return [_canonicalize_modifier_prefix(normalized, modifier_mode)]


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

    logger.info("[clipai] Hotkey listener modifier_mode=%s", modifier_mode)

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
            if diagnostics_enabled("hotkey_raw_events"):
                logger.debug("[clipai] Ignored key press: %s", _describe_key(key))
            return
        with lock:
            pressed.add(token)
            if diagnostics_enabled("hotkey_raw_events") and (token in {"ctrl", "alt"} or {"ctrl", "alt"}.issubset(pressed)):
                logger.debug("[clipai] Key press token=%s raw=(%s) pressed=%s", token, _describe_key(key), sorted(pressed))
            for action_id, tokens in hotkeys:
                if action_id in active:
                    continue
                if tokens.issubset(pressed):
                    logger.debug(
                        "[clipai] Hotkey matched on press: action=%s tokens=%s pressed=%s",
                        action_id,
                        sorted(tokens),
                        sorted(pressed),
                    )
                    state = _HotkeyState()
                    state.timer = threading.Timer(long_press_sec, lambda aid=action_id: _fire_long(aid))
                    state.timer.daemon = True
                    state.timer.start()
                    active[action_id] = state

    def _on_release(key) -> None:
        token = _normalize_key(key)
        if not token:
            if diagnostics_enabled("hotkey_raw_events"):
                logger.debug("[clipai] Ignored key release: %s", _describe_key(key))
            return

        callbacks: list[Callable[[], None]] = []
        with lock:
            if diagnostics_enabled("hotkey_raw_events") and (token in {"ctrl", "alt"} or {"ctrl", "alt"}.issubset(pressed)):
                logger.debug("[clipai] Key release token=%s raw=(%s) pressed_before=%s", token, _describe_key(key), sorted(pressed))
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
                    logger.debug(
                        "[clipai] Hotkey matched on release: action=%s released=%s remaining_pressed=%s",
                        action_id,
                        token,
                        sorted(pressed),
                    )
                    callbacks.append(lambda aid=action_id: _fire_normal(aid))

        for callback in callbacks:
            callback()

    listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
    listener.start()
    return HotkeyListener(listener)
