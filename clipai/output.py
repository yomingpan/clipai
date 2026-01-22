import time
import keyboard


def maybe_auto_paste():
    time.sleep(0.05)
    keyboard.send("ctrl+v")
