import os
import time
import keyboard


def maybe_auto_paste():
    time.sleep(0.05)
    keyboard.send("ctrl+v")


def save_to_file(path: str, content: str) -> None:
    if not path:
        return
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
