
import os
import time
from pynput.keyboard import Controller, Key


def maybe_auto_paste(delay_sec: float = 0.1):
    """
    Simulate Ctrl+V using pynput.
    """
    time.sleep(delay_sec) # Small delay to ensure clipboard is ready
    keyboard = Controller()
    
    # Press and release Ctrl+V
    with keyboard.pressed(Key.ctrl):
        keyboard.press('v')
        keyboard.release('v')

def save_to_file(path: str, content: str) -> None:
    if not path:
        return
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)



