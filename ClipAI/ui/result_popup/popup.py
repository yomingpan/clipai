from __future__ import annotations

"""Legacy popup widget kept for compatibility.

The active popup implementation lives in `clipai.ui.popup_presenter`
and `clipai.ui.result_popup.*` helpers.
"""

import tkinter as tk


class ResultPopup:
    def __init__(self, root) -> None:
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.title("ClipAI")
        self.text = tk.Text(self.window, width=70, height=18)
        self.text.pack(fill="both", expand=True)

    def show(self) -> None:
        self.window.deiconify()

    def set_content(self, content: str) -> None:
        self.text.delete("1.0", "end")
        self.text.insert("end", content)
