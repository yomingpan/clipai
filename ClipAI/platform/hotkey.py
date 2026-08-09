from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable

from ClipAI.core.hotkeys import GRAVE_KEY_ALIASES, GRAVE_KEY_TOKEN, canonicalize_hotkey, parse_hotkey_tokens
from ClipAI.core.commands import InterruptionRequested, ShortcutAttemptRejected, ShortcutInputEvent, ShortcutKeyStateChanged, ShortcutPressEnded, ShortcutPressInvoked, ShortcutPressStarted
from ClipAI.core.models import ShortcutObservationSnapshot, ShortcutPressId, ShortcutPressRef
from ClipAI.platform.keyboard_state import MODIFIER_KEYS, windows_key_is_pressed

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
        return GRAVE_KEY_TOKEN
    if isinstance(vk, int):
        if vk in _VK_DIGIT_MAP:
            return _VK_DIGIT_MAP[vk]
        if vk in _VK_NUMPAD_MAP:
            return _VK_NUMPAD_MAP[vk]
        if vk in _VK_ALPHA_MAP:
            return _VK_ALPHA_MAP[vk]

    char = getattr(key, "char", None)
    if char:
        normalized = str(char).lower()
        if normalized in GRAVE_KEY_ALIASES:
            return GRAVE_KEY_TOKEN
        return _SHIFTED_DIGIT_MAP.get(normalized, normalized)
    return None


def _parse_hotkey(hotkey: str) -> set[str]:
    return set(parse_hotkey_tokens(hotkey))


def _canonicalize_modifier_prefix(hotkey: str, modifier_mode: str) -> str:
    return canonicalize_hotkey(hotkey, modifier_mode)


def expand_hotkeys(hotkey: str, modifier_mode: str = "ctrl_alt") -> list[str]:
    normalized = hotkey.strip().lower()
    if not normalized:
        return []
    return [_canonicalize_modifier_prefix(normalized, modifier_mode)]


def build_hotkey_bindings(shortcut_map: dict[str, dict], *, modifier_mode: str = "alt_shift") -> list[tuple[str, set[str]]]:
    hotkeys: list[tuple[str, set[str]]] = []
    for shortcut_id, definition in shortcut_map.items():
        hotkey = str(definition.get("hotkey") or "").strip()
        for variant in expand_hotkeys(hotkey, modifier_mode=modifier_mode):
            hotkeys.append((shortcut_id, _parse_hotkey(variant)))
    return hotkeys


@dataclass
class _HotkeyState:
    timer_generation: int
    press_id: ShortcutPressId
    shortcut_id: str
    binding_tokens: frozenset[str]
    timer: threading.Timer | None = None
    long_fired: bool = False


class _ShortcutObservationLease:
    def __init__(
        self,
        dispatcher: _HotkeyDispatcher,
        token: int,
        snapshot: ShortcutObservationSnapshot,
    ) -> None:
        self._dispatcher = dispatcher
        self._token = token
        self._snapshot = snapshot
        self._closed = False

    @property
    def snapshot(self) -> ShortcutObservationSnapshot:
        return self._snapshot

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._dispatcher.close_observation(self._token)


class HotkeyListener:
    def __init__(self, listener, dispatcher: _HotkeyDispatcher) -> None:
        self._listener = listener
        self._dispatcher = dispatcher
        self.running = True

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        self._dispatcher.stop()
        self._listener.stop()

    def observe(self) -> _ShortcutObservationLease:
        return self._dispatcher.observe()


class _HotkeyDispatcher:
    def __init__(
        self,
        hotkeys: list[tuple[str, set[str]]],
        on_event: Callable[[ShortcutInputEvent], None],
        *,
        long_press_sec: float = LONG_PRESS_SEC,
        timer_factory: Callable[..., threading.Timer] = threading.Timer,
        diagnostics_enabled: Callable[[str], bool] = lambda _flag: False,
        key_is_pressed: Callable[[str], bool | None] | None = None,
    ) -> None:
        self._hotkeys = [(shortcut_id, frozenset(tokens)) for shortcut_id, tokens in hotkeys]
        self._on_event = on_event
        self._long_press_sec = long_press_sec
        self._timer_factory = timer_factory
        self._diagnostics_enabled = diagnostics_enabled
        self._key_is_pressed = key_is_pressed
        self._pressed: set[str] = set()
        self._active: dict[str, _HotkeyState] = {}
        self._escape: _HotkeyState | None = None
        self._timer_generation = 0
        self._press_generation = 0
        self._observation_generation = 0
        self._observers: set[int] = set()
        self._lock = threading.RLock()
        self._stopped = False

    def _emit(self, event: ShortcutInputEvent) -> None:
        if not self._stopped:
            self._on_event(event)

    def _report_key_state(self) -> None:
        if self._observers:
            self._emit(ShortcutKeyStateChanged(frozenset(self._pressed)))

    def _next_press_id(self) -> ShortcutPressId:
        self._press_generation += 1
        return ShortcutPressId(self._press_generation)

    def observe(self) -> _ShortcutObservationLease:
        with self._lock:
            if self._stopped:
                return _ShortcutObservationLease(
                    self,
                    0,
                    ShortcutObservationSnapshot(),
                )
            self._observation_generation += 1
            token = self._observation_generation
            self._observers.add(token)
            active = tuple(
                ShortcutPressRef(state.press_id, state.shortcut_id)
                for state in self._active.values()
            )
            return _ShortcutObservationLease(
                self,
                token,
                ShortcutObservationSnapshot(frozenset(self._pressed), active),
            )

    def close_observation(self, token: int) -> None:
        with self._lock:
            self._observers.discard(token)

    def stop(self) -> None:
        with self._lock:
            if self._stopped:
                return
            active = tuple(self._active.values())
            for state in active:
                if state.timer:
                    state.timer.cancel()
            if self._escape is not None and self._escape.timer is not None:
                self._escape.timer.cancel()
            self._pressed.clear()
            self._active.clear()
            self._escape = None
            self._observers.clear()
            self._stopped = True
        for state in active:
            self._on_event(ShortcutPressEnded(state.press_id, state.shortcut_id, "cancelled"))

    def _fire_long(
        self,
        action_id: str,
        press_id: ShortcutPressId,
        timer_generation: int,
    ) -> None:
        with self._lock:
            if self._stopped:
                return
            state = self._active.get(action_id)
            if (
                state is None
                or state.timer_generation != timer_generation
                or state.press_id != press_id
            ):
                return
            trigger_tokens = state.binding_tokens.difference(MODIFIER_KEYS)
            released_tokens = {
                token
                for token in trigger_tokens
                if self._key_is_pressed is not None
                and self._key_is_pressed(token) is False
            }
            if released_tokens:
                self._active.pop(action_id, None)
                self._pressed.difference_update(released_tokens)
                self._report_key_state()
                self._emit(
                    ShortcutPressEnded(
                        state.press_id,
                        state.shortcut_id,
                        "cancelled",
                    )
                )
                return
            state.long_fired = True
            logger.info(
                "[clipai] Shortcut press invoked: shortcut_id=%s press_id=%s press_type=long",
                action_id,
                press_id,
            )
            self._emit(ShortcutPressInvoked(press_id, action_id, "long"))

    def _discard_stale_pressed_state(self) -> set[str]:
        if self._key_is_pressed is None:
            return set()
        stale_tokens = {
            token
            for token in self._pressed
            if self._key_is_pressed(token) is False
        }
        if not stale_tokens:
            return set()

        affected_actions = {
            action_id
            for action_id, state in self._active.items()
            if not state.binding_tokens.isdisjoint(stale_tokens)
        }
        logger.info(
            "[clipai] Discarding stale hotkey state after missing key releases: tokens=%s actions=%s pressed=%s",
            sorted(stale_tokens),
            sorted(affected_actions),
            sorted(self._pressed),
        )
        for action_id in affected_actions:
            state = self._active.pop(action_id, None)
            if state is not None and state.timer:
                state.timer.cancel()
            if state is not None:
                self._emit(
                    ShortcutPressEnded(
                        state.press_id,
                        state.shortcut_id,
                        "cancelled",
                    )
                )
        self._pressed.difference_update(stale_tokens)
        self._report_key_state()
        return stale_tokens

    def on_press(self, key, injected: bool = False) -> None:
        # Windows low-level keyboard hooks identify events created through
        # SendInput (including pynput.Controller and external macro tools).
        # Synthetic input must never become a ClipAI user intent or mutate the
        # physical-key state used to resolve short and long presses.
        if injected:
            if self._diagnostics_enabled("hotkey_raw_events"):
                logger.debug("[clipai] Ignored injected key press: %s", _describe_key(key))
            return

        token = _normalize_key(key)
        if not token:
            if self._diagnostics_enabled("hotkey_raw_events"):
                logger.debug("[clipai] Ignored key press: %s", _describe_key(key))
            return

        with self._lock:
            if self._stopped:
                return
            stale_tokens = self._discard_stale_pressed_state()
            if token == "esc":
                if self._escape is not None:
                    return
                for state in tuple(self._active.values()):
                    if state.timer is not None:
                        state.timer.cancel()
                    self._emit(
                        ShortcutPressEnded(
                            state.press_id,
                            state.shortcut_id,
                            "cancelled",
                        )
                    )
                self._active.clear()
                self._pressed.add(token)
                self._timer_generation += 1
                state = _HotkeyState(
                    self._timer_generation,
                    ShortcutPressId(0),
                    "",
                    frozenset({"esc"}),
                )

                def fire_all(generation=state.timer_generation) -> None:
                    with self._lock:
                        current = self._escape
                        if (
                            self._stopped
                            or current is None
                            or current.timer_generation != generation
                        ):
                            return
                        current.long_fired = True
                        self._emit(InterruptionRequested("all"))

                state.timer = self._timer_factory(self._long_press_sec, fire_all)
                state.timer.daemon = True
                state.timer.start()
                self._escape = state
                self._report_key_state()
                self._emit(InterruptionRequested("current"))
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
                    self._timer_generation += 1
                    press_id = self._next_press_id()
                    state = _HotkeyState(
                        self._timer_generation,
                        press_id,
                        action_id,
                        tokens,
                    )
                    state.timer = self._timer_factory(
                        self._long_press_sec,
                        lambda aid=action_id, pid=press_id, generation=state.timer_generation: self._fire_long(aid, pid, generation),
                    )
                    state.timer.daemon = True
                    state.timer.start()
                    self._active[action_id] = state
                    self._emit(ShortcutPressStarted(press_id, action_id))
            if not matched and not stale_tokens and token not in {"ctrl", "alt", "shift"}:
                if self._observers or not self._pressed.isdisjoint(MODIFIER_KEYS):
                    self._emit(ShortcutAttemptRejected())
            self._report_key_state()

    def on_release(self, key, injected: bool = False) -> None:
        if injected:
            if self._diagnostics_enabled("hotkey_raw_events"):
                logger.debug("[clipai] Ignored injected key release: %s", _describe_key(key))
            return

        token = _normalize_key(key)
        if not token:
            if self._diagnostics_enabled("hotkey_raw_events"):
                logger.debug("[clipai] Ignored key release: %s", _describe_key(key))
            return

        events: list[ShortcutInputEvent] = []
        with self._lock:
            if self._stopped:
                return
            if token == "esc":
                state, self._escape = self._escape, None
                self._pressed.discard(token)
                if state is not None and state.timer is not None:
                    state.timer.cancel()
                self._report_key_state()
                return
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
                trigger_tokens = tokens.difference(MODIFIER_KEYS)
                if not trigger_tokens.isdisjoint(self._pressed):
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
                    events.append(
                        ShortcutPressInvoked(
                            state.press_id,
                            state.shortcut_id,
                            "short",
                        )
                    )
                events.append(
                    ShortcutPressEnded(
                        state.press_id,
                        state.shortcut_id,
                        "released",
                    )
                )

            for event in events:
                self._emit(event)
            self._report_key_state()


def create_hotkey_dispatcher(
    shortcut_map: dict[str, dict],
    on_event: Callable[[ShortcutInputEvent], None],
    *,
    modifier_mode: str = "alt_shift",
    long_press_sec: float = LONG_PRESS_SEC,
    timer_factory: Callable[..., threading.Timer] = threading.Timer,
    diagnostics_enabled: Callable[[str], bool] = lambda _flag: False,
    key_is_pressed: Callable[[str], bool | None] | None = None,
) -> _HotkeyDispatcher:
    return _HotkeyDispatcher(
        build_hotkey_bindings(shortcut_map, modifier_mode=modifier_mode),
        on_event,
        long_press_sec=long_press_sec,
        timer_factory=timer_factory,
        diagnostics_enabled=diagnostics_enabled,
        key_is_pressed=key_is_pressed,
    )


def register_hotkeys_with_long_press(
    shortcut_map: dict[str, dict],
    on_event: Callable[[ShortcutInputEvent], None],
    *,
    modifier_mode: str = "alt_shift",
    long_press_sec: float = LONG_PRESS_SEC,
    diagnostics_enabled: Callable[[str], bool] = lambda _flag: False,
):
    try:
        from pynput import keyboard
    except ImportError as exc:
        raise RuntimeError("pynput is required for desktop hotkey mode") from exc

    hotkeys = build_hotkey_bindings(shortcut_map, modifier_mode=modifier_mode)
    for shortcut_id, tokens in hotkeys:
        logger.info("[clipai] Registered hotkey %s -> %s", "+".join(sorted(tokens)), shortcut_id)

    logger.info("[clipai] Hotkey listener modifier_mode=%s long_press_sec=%s", modifier_mode, long_press_sec)

    dispatcher = _HotkeyDispatcher(
        hotkeys,
        on_event,
        long_press_sec=long_press_sec,
        diagnostics_enabled=diagnostics_enabled,
        key_is_pressed=windows_key_is_pressed,
    )
    listener = keyboard.Listener(on_press=dispatcher.on_press, on_release=dispatcher.on_release)
    listener.start()
    return HotkeyListener(listener, dispatcher)
