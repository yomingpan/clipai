import re

SENSITIVE_PATTERNS = [
    r"\bpassword\b",
    r"\bsecret\b",
    r"\btoken\b",
    r"AKIA[0-9A-Z]{16}",
]


def should_block_send(text: str) -> bool:
    t = text.lower()
    for p in SENSITIVE_PATTERNS:
        if re.search(p.lower(), t):
            return True
    return False
