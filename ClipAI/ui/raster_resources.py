"""Tk-root graphics resources, independent of any content or view lease."""

import tkinter as tk

from PIL import Image, ImageTk

from ClipAI.ui.voice_visuals import TRANSPARENT_KEY


class TkRasterResources:
    """Keep Tk's shared photo color table initialized until root teardown.

    The unplaced Canvas retains one fixed pixel. No document, backdrop, view
    identity, timer or input binding is retained here.
    """

    def __init__(self, root: tk.Misc) -> None:
        self._canvas: tk.Canvas | None = tk.Canvas(root, width=1, height=1, highlightthickness=0)
        self._photo: ImageTk.PhotoImage | None = ImageTk.PhotoImage(Image.new("RGB", (1, 1), TRANSPARENT_KEY), master=root)
        self._canvas.create_image(0, 0, image=self._photo)

    def close(self) -> None:
        canvas, self._canvas = self._canvas, None
        if canvas is not None:
            canvas.destroy()
        self._photo = None
