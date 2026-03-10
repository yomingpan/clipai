import pyperclip
import io
import base64
import time
import ctypes
from ctypes import wintypes

try:
    from PIL import ImageGrab, Image
except Exception:
    ImageGrab = None
    Image = None

try:
    import pytesseract
except Exception:
    pytesseract = None


def read_clipboard_text(retries=3, delay=0.1) -> str:
    for i in range(retries):
        try:
            return pyperclip.paste() or ""
        except Exception:
            if i < retries - 1:
                time.sleep(delay)
                continue
            return ""
    return ""


def read_clipboard_image(retries=3, delay=0.1):
    if ImageGrab is None:
        return None
    for i in range(retries):
        try:
            return ImageGrab.grabclipboard()
        except Exception:
            if i < retries - 1:
                time.sleep(delay)
                continue
            return None
    return None


def ocr_image_to_text(image) -> str:
    if pytesseract is None:
        raise RuntimeError("pytesseract is not installed")
    return pytesseract.image_to_string(image) or ""


def image_to_base64(image) -> str:
    """Convert a PIL Image to a base64 encoded string."""
    buffered = io.BytesIO()
    # Convert to RGB if necessary (e.g. for RGBA images from clipboard)
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
    image.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def _image_to_dib_bytes(image) -> bytes:
    """Convert PIL Image to DIB bytes for CF_DIB clipboard format."""
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
    with io.BytesIO() as output:
        image.save(output, format="BMP")
        bmp_data = output.getvalue()
    # Strip the BITMAPFILEHEADER (14 bytes) to get DIB data
    return bmp_data[14:]


def _set_clipboard_data(data_items) -> None:
    """Set multiple clipboard formats in one OpenClipboard call."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    if not user32.OpenClipboard(None):
        return

    try:
        user32.EmptyClipboard()

        for format_id, payload in data_items:
            if payload is None:
                continue
            h_mem = kernel32.GlobalAlloc(0x0042, len(payload) + 1)
            if not h_mem:
                continue
            p_mem = kernel32.GlobalLock(h_mem)
            if p_mem:
                ctypes.memmove(p_mem, payload, len(payload))
                kernel32.GlobalUnlock(h_mem)
                user32.SetClipboardData(format_id, h_mem)
    finally:
        user32.CloseClipboard()


def write_clipboard_image(image) -> None:
    if Image is None or image is None:
        return
    dib_bytes = _image_to_dib_bytes(image)
    CF_DIB = 8
    _set_clipboard_data([(CF_DIB, dib_bytes)])


def write_clipboard_content(text: str = None, image=None) -> None:
    data_items = []
    if image is not None:
        dib_bytes = _image_to_dib_bytes(image)
        data_items.append((8, dib_bytes))
    if text is not None:
        text_bytes = text.encode("utf-16le")
        data_items.append((13, text_bytes))
    if data_items:
        _set_clipboard_data(data_items)


def capture_clipboard_snapshot() -> dict:
    text = read_clipboard_text()
    image = read_clipboard_image()
    if image is not None and not hasattr(image, "mode"):
        image = None
    return {
        "text": text if text else None,
        "image": image,
    }


def restore_clipboard_snapshot(snapshot: dict) -> None:
    if not snapshot:
        return
    text = snapshot.get("text")
    image = snapshot.get("image")
    if text is None and image is None:
        return
    write_clipboard_content(text=text, image=image)


def write_clipboard_text(text: str, retries=3, delay=0.1) -> None:
    for i in range(retries):
        try:
            pyperclip.copy(text)
            return
        except Exception:
            if i < retries - 1:
                time.sleep(delay)
                continue
            print(f"[clipai] Failed to write to clipboard after {retries} attempts.")

def write_clipboard_html(html: str, plain_text: str = None) -> None:
    """
    Writes HTML to the Windows clipboard using the CF_HTML format.
    This allows pasting rich text into applications like Word, Outlook, Teams.
    """
    if plain_text is None:
        plain_text = html # Fallback

    # Windows HTML Clipboard format header
    MARKER_BLOCK_OUTPUT = \
        "Version:0.9\r\n" \
        "StartHTML:{0:08d}\r\n" \
        "EndHTML:{1:08d}\r\n" \
        "StartFragment:{2:08d}\r\n" \
        "EndFragment:{3:08d}\r\n"

    FRAGMENT_START = "<!--StartFragment-->"
    FRAGMENT_END = "<!--EndFragment-->"

    html_prefix = "<html><head><meta http-equiv=\"content-type\" content=\"text/html; charset=utf-8\"></head><body>"
    html_suffix = "</body></html>"
    
    full_html = html_prefix + FRAGMENT_START + html + FRAGMENT_END + html_suffix
    full_html_bytes = full_html.encode("utf-8")

    # Calculate offsets
    dummy_header = MARKER_BLOCK_OUTPUT.format(0, 0, 0, 0)
    header_len = len(dummy_header)
    
    start_html = header_len
    end_html = header_len + len(full_html_bytes)
    start_fragment = start_html + full_html.find(FRAGMENT_START) + len(FRAGMENT_START)
    end_fragment = start_html + full_html.find(FRAGMENT_END)

    final_header = MARKER_BLOCK_OUTPUT.format(start_html, end_html, start_fragment, end_fragment)
    final_data = final_header.encode("utf-8") + full_html_bytes

    # Win32 API calls
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    CF_UNICODETEXT = 13
    CF_HTML = user32.RegisterClipboardFormatW("HTML Format")

    if not user32.OpenClipboard(None):
        return

    try:
        user32.EmptyClipboard()

        # 1. Write HTML
        h_html_mem = kernel32.GlobalAlloc(0x0042, len(final_data) + 1) # GHND = GMEM_MOVEABLE | GMEM_ZEROINIT
        if h_html_mem:
            p_html_mem = kernel32.GlobalLock(h_html_mem)
            if p_html_mem:
                ctypes.memmove(p_html_mem, final_data, len(final_data))
                kernel32.GlobalUnlock(h_html_mem)
                user32.SetClipboardData(CF_HTML, h_html_mem)

        # 2. Write Plain Text (as fallback)
        plain_text_bytes = plain_text.encode("utf-16le")
        h_text_mem = kernel32.GlobalAlloc(0x0042, len(plain_text_bytes) + 2)
        if h_text_mem:
            p_text_mem = kernel32.GlobalLock(h_text_mem)
            if p_text_mem:
                ctypes.memmove(p_text_mem, plain_text_bytes, len(plain_text_bytes))
                kernel32.GlobalUnlock(h_text_mem)
                user32.SetClipboardData(CF_UNICODETEXT, h_text_mem)

    finally:
        user32.CloseClipboard()



