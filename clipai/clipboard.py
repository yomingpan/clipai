import pyperclip

try:
    from PIL import ImageGrab
except Exception:
    ImageGrab = None

try:
    import pytesseract
except Exception:
    pytesseract = None


def read_clipboard_text() -> str:
    try:
        return pyperclip.paste() or ""
    except Exception:
        return ""


def read_clipboard_image():
    if ImageGrab is None:
        return None
    try:
        return ImageGrab.grabclipboard()
    except Exception:
        return None


def ocr_image_to_text(image) -> str:
    if pytesseract is None:
        raise RuntimeError("pytesseract is not installed")
    return pytesseract.image_to_string(image) or ""


def write_clipboard_text(text: str) -> None:
    pyperclip.copy(text)
