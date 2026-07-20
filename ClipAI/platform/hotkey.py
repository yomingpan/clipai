from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass
from typing import Callable

from ClipAI.core.models import HotkeyEventType

logger = logging.getLogger("clipai.hotkey")

LONG_PRESS_SEC = 0.5

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
_VK_OEM_3 = 192
_GRAVE_KEY_TOKEN = "grave"
_GRAVE_KEY_ALIASES = {"`", "~", _GRAVE_KEY_TOKEN}
_MODIFIER_VIRTUAL_KEYS = {
    "alt": 0x12,  # VK_MENU
    "ctrl": 0x11,  # VK_CONTROL
    "shift": 0x10,  # VK_SHIFT
}


def _windows_modifier_is_pressed(modifier: str) -> bool | None:
    """Return the physical modifier state, when Windows can report it.

    Secure desktop transitions (for example Ctrl+Alt+Delete) can prevent the
    keyboard hook from receiving matching release events.  The dispatcher uses
    this probe to discard those stale events before matching a later key.
    """
    virtual_key = _MODIFIER_VIRTUAL_KEYS.get(modifier)
    if virtual_key is None or sys.platform != "win32":
        return None
    try:
        import ctypes

        return bool(ctypes.windll.user32.GetAsyncKeyState(virtual_key) & 0x8000)
    except (AttributeError, OSError):
        return None


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

    vk = getattr(key, "vk", None)
    if vk == _VK_OEM_3:
        return _GRAVE_KEY_TOKEN

    char = getattr(key, "char", None)
    if char:
        normalized = str(char).lower()
        if normalized in _GRAVE_KEY_ALIASES:
            return _GRAVE_KEY_TOKEN
        return _SHIFTED_DIGIT_MAP.get(normalized, normalized)

    if isinstance(vk, int):
        if vk in _VK_DIGIT_MAP:
            return _VK_DIGIT_MAP[vk]
        if vk in _VK_NUMPAD_MAP:
            return _VK_NUMPAD_MAP[vk]
        if vk in _VK_ALPHA_MAP:
            return _VK_ALPHA_MAP[vk]
    return None


def _parse_hotkey(hotkey: str) -> set[str]:
    tokens = {part.strip().lower() for part in hotkey.split("+") if part.strip()}
    return {_GRAVE_KEY_TOKEN if token in _GRAVE_KEY_ALIASES else token for token in tokens}


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


def build_hotkey_bindings(action_map: dict[str, dict], *, modifier_mode: str = "alt_shift") -> list[tuple[str, set[str]]]:
    hotkeys: list[tuple[str, set[str]]] = []
    for action_id, action in action_map.items():
        hotkey = str(action.get("hotkey") or "").strip()
        for variant in expand_hotkeys(hotkey, modifier_mode=modifier_mode):
            hotkeys.append((action_id, _parse_hotkey(variant)))
    return hotkeys


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


class _HotkeyDispatcher:
    def __init__(
        self,
        hotkeys: list[tuple[str, set[str]]],
        on_trigger: Callable[[str, HotkeyEventType], None],
        *,
        long_press_sec: float = LONG_PRESS_SEC,
        timer_factory: Callable[..., threading.Timer] = threading.Timer,
        diagnostics_enabled: Callable[[str], bool] = lambda _flag: False,
        modifier_is_pressed: Callable[[str], bool | None] | None = None,
    ) -> None:
        self._hotkeys = hotkeys
        self._on_trigger = on_trigger
        self._long_press_sec = long_press_sec
        self._timer_factory = timer_factory
        self._diagnostics_enabled = diagnostics_enabled
        self._modifier_is_pressed = modifier_is_pressed
        self._pressed: set[str] = set()
        self._active: dict[str, _HotkeyState] = {}
        self._pending_release: dict[str, HotkeyEventType] = {}
        self._lock = threading.RLock()

    def _fire(self, action_id: str, press_type: HotkeyEventType) -> None:
        logger.info("[clipai] Hotkey triggered: action_id=%s press_type=%s", action_id, press_type)
        self._on_trigger(action_id, press_type)

    def _fire_long(self, action_id: str) -> None:
        with self._lock:
            state = self._active.get(action_id)
            if state is None:
                return
            state.long_fired = True
            # Long press is a complete typed intent as soon as its threshold is
            # reached. Waiting for every modifier to be released reverses the
            # order of held-key shortcut sequences (Q, then an action key).
            self._fire(action_id, "long")

    def _discard_stale_modifier_state(self) -> bool:
        if self._modifier_is_pressed is None:
            return False
        stale_modifiers = {
            modifier
            for modifier in self._pressed & set(_MODIFIER_VIRTUAL_KEYS)
            if self._modifier_is_pressed(modifier) is False
        }
        if not stale_modifiers:
            return False

        logger.info(
            "[clipai] Discarding stale hotkey state after missing modifier releases: modifiers=%s pressed=%s",
            sorted(stale_modifiers),
            sorted(self._pressed),
        )
        for state in self._active.values():
            if state.timer:
                state.timer.cancel()
        self._pressed.clear()
        self._active.clear()
        self._pending_release.clear()
        return True

    def on_press(self, key) -> None:
        token = _normalize_key(key)
        if not token:
            if self._diagnostics_enabled("hotkey_raw_events"):
                logger.debug("[clipai] Ignored key press: %s", _describe_key(key))
            return

        with self._lock:
            stale_state_discarded = self._discard_stale_modifier_state()
            if token == "esc":
                self._fire("", "cancel")
                return
            if stale_state_discarded:
                # Do not reinterpret the key that exposed the stale state as a
                # new shortcut. The user can begin a fresh chord immediately.
                return
            if token in self._pressed:
                return
            self._pressed.add(token)
            matched = False
            if self._diagnostics_enabled("hotkey_raw_events") and (token in {"ctrl", "alt", "shift"} or len(self._pressed) > 1):
                logger.debug("[clipai] Key press token=%s raw=(%s) pressed=%s", token, _describe_key(key), sorted(self._pressed))
            for action_id, tokens in self._hotkeys:
                if action_id in self._active:
                    continue
                if tokens.issubset(self._pressed):
                    matched = True
                    logger.debug(
                        "[clipai] Hotkey matched on press: action=%s tokens=%s pressed=%s",
                        action_id,
                        sorted(tokens),
                        sorted(self._pressed),
                    )
                    state = _HotkeyState()
                    state.timer = self._timer_factory(self._long_press_sec, lambda aid=action_id: self._fire_long(aid))
                    state.timer.daemon = True
                    state.timer.start()
                    self._active[action_id] = state
            if not matched and token not in {"ctrl", "alt", "shift"}:
                self._fire("", "invalid")

    def on_release(self, key) -> None:
        token = _normalize_key(key)
        if not token:
            if self._diagnostics_enabled("hotkey_raw_events"):
                logger.debug("[clipai] Ignored key release: %s", _describe_key(key))
            return

        callbacks: list[Callable[[], None]] = []
        with self._lock:
            if self._diagnostics_enabled("hotkey_raw_events") and (token in {"ctrl", "alt", "shift"} or len(self._pressed) > 1):
                logger.debug(
                    "[clipai] Key release token=%s raw=(%s) pressed_before=%s",
                    token,
                    _describe_key(key),
                    sorted(self._pressed),
                )
            self._pressed.discard(token)
            for action_id, tokens in self._hotkeys:
                if action_id not in self._active:
                    continue
                if tokens.issubset(self._pressed):
                    continue
                state = self._active.pop(action_id)
                if state.timer:
                    state.timer.cancel()
                if not state.long_fired:
                    logger.debug(
                        "[clipai] Hotkey matched on release: action=%s released=%s remaining_pressed=%s",
                        action_id,
                        token,
                        sorted(self._pressed),
                    )
                    self._pending_release[action_id] = "short"
                else:
                    self._pending_release[action_id] = "long_release"

            for action_id, tokens in self._hotkeys:
                press_type = self._pending_release.get(action_id)
                if press_type is None or not tokens.isdisjoint(self._pressed):
                    continue
                self._pending_release.pop(action_id, None)
                if press_type == "long_release":
                    callbacks.append(lambda aid=action_id: self._fire(aid, "long_release"))
                else:
                    callbacks.append(lambda aid=action_id: self._fire(aid, "short"))

        for callback in callbacks:
            callback()


def create_hotkey_dispatcher(
    action_map: dict[str, dict],
    on_trigger: Callable[[str, HotkeyEventType], None],
    *,
    modifier_mode: str = "alt_shift",
    long_press_sec: float = LONG_PRESS_SEC,
    timer_factory: Callable[..., threading.Timer] = threading.Timer,
    diagnostics_enabled: Callable[[str], bool] = lambda _flag: False,
    modifier_is_pressed: Callable[[str], bool | None] | None = None,
) -> _HotkeyDispatcher:
    return _HotkeyDispatcher(
        build_hotkey_bindings(action_map, modifier_mode=modifier_mode),
        on_trigger,
        long_press_sec=long_press_sec,
        timer_factory=timer_factory,
        diagnostics_enabled=diagnostics_enabled,
        modifier_is_pressed=modifier_is_pressed,
    )


def register_hotkeys_with_long_press(
    action_map: dict[str, dict],
    on_trigger: Callable[[str, HotkeyEventType], None],
    *,
    modifier_mode: str = "alt_shift",
    long_press_sec: float = LONG_PRESS_SEC,
    diagnostics_enabled: Callable[[str], bool] = lambda _flag: False,
):
    try:
        from pynput import keyboard
    except ImportError as exc:
        raise RuntimeError("pynput is required for desktop hotkey mode") from exc

    hotkeys = build_hotkey_bindings(action_map, modifier_mode=modifier_mode)
    for action_id, tokens in hotkeys:
        logger.info("[clipai] Registered hotkey %s -> %s", "+".join(sorted(tokens)), action_id)

    logger.info("[clipai] Hotkey listener modifier_mode=%s long_press_sec=%s", modifier_mode, long_press_sec)

    dispatcher = _HotkeyDispatcher(
        hotkeys,
        on_trigger,
        long_press_sec=long_press_sec,
        diagnostics_enabled=diagnostics_enabled,
        modifier_is_pressed=_windows_modifier_is_pressed,
    )
    listener = keyboard.Listener(on_press=dispatcher.on_press, on_release=dispatcher.on_release)
    listener.start()
    return HotkeyListener(listener)
