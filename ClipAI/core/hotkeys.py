from __future__ import annotations


GRAVE_KEY_TOKEN = "grave"
GRAVE_KEY_ALIASES = {"`", "~", GRAVE_KEY_TOKEN}
MODIFIER_KEYS = frozenset({"ctrl", "alt", "shift"})


def canonicalize_hotkey(hotkey: str, modifier_mode: str = "ctrl_alt") -> str:
    normalized = hotkey.strip().lower()
    if not normalized:
        return ""
    prefix_map = {
        "alt_shift": "alt+shift+",
        "ctrl_shift": "ctrl+shift+",
        "ctrl_alt": "ctrl+alt+",
    }
    canonical_prefix = prefix_map.get((modifier_mode or "ctrl_alt").lower(), "ctrl+alt+")
    for prefix in prefix_map.values():
        if normalized.startswith(prefix):
            return f"{canonical_prefix}{normalized[len(prefix):]}"
    if "+" not in normalized:
        return f"{canonical_prefix}{normalized}"
    return normalized


def parse_hotkey_tokens(hotkey: str) -> frozenset[str]:
    tokens = {part.strip().lower() for part in hotkey.split("+") if part.strip()}
    return frozenset(GRAVE_KEY_TOKEN if token in GRAVE_KEY_ALIASES else token for token in tokens)


def display_hotkey(hotkey: str) -> str:
    labels = {
        "ctrl": "Ctrl",
        "alt": "Alt",
        "shift": "Shift",
        GRAVE_KEY_TOKEN: "~",
    }
    return " + ".join(labels.get(token, token.upper() if len(token) == 1 else token.title()) for token in hotkey.split("+"))
