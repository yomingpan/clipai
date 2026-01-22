import re

DEFAULT_PATTERNS = [
    r"\bpassword\b",
    r"\bsecret\b",
    r"\btoken\b",
    r"AKIA[0-9A-Z]{16}",
]


def apply_safety(text: str, mode: str = "block", patterns=None):
    patterns = patterns or DEFAULT_PATTERNS
    mode = (mode or "block").lower()

    if mode == "off":
        return {"action": "allow", "text": text}

    hits = []
    masked = text
    for p in patterns:
        if re.search(p, masked, flags=re.IGNORECASE):
            hits.append(p)
            if mode == "mask":
                masked = re.sub(p, "[REDACTED]", masked, flags=re.IGNORECASE)

    if hits and mode == "block":
        return {"action": "block", "text": text, "hits": hits}

    if hits and mode == "mask":
        return {"action": "mask", "text": masked, "hits": hits}

    return {"action": "allow", "text": text}
