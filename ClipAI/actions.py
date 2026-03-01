from __future__ import annotations


def load_actions() -> dict[str, dict]:
    return {
        "summarize": {
            "id": "summarize",
            "name": "Summarize",
            "provider": "gemini",
            "model": "gemini-1.5-flash",
            "stream": True,
            "temperature": 0.3,
            "template": "Summarize this text:\n{input}",
        },
        "translate": {
            "id": "translate",
            "name": "Translate",
            "provider": "gemini",
            "model": "gemini-1.5-flash",
            "stream": True,
            "temperature": 0.2,
            "template": "Translate to English:\n{input}",
        },
    }
