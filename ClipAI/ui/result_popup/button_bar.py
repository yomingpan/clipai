from __future__ import annotations

import tkinter as tk


class ButtonBar:
    def __init__(self, root, on_copy, on_tts) -> None:
        self.frame = tk.Frame(root)
        tk.Button(self.frame, text="Copy", command=on_copy).pack(side="left")
        tk.Button(self.frame, text="TTS", command=on_tts).pack(side="left")
