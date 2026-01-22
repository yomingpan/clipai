import pyperclip


def read_clipboard_text() -> str:
    try:
        return pyperclip.paste() or ""
    except Exception:
        return ""


def write_clipboard_text(text: str) -> None:
    pyperclip.copy(text)
