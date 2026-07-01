from __future__ import annotations

from collections.abc import Callable

from ClipAI.ui.base_dialog import BaseDialog, BaseResultSurface


class ResultDialogPresenter:
    def __init__(self) -> None:
        self._dialog = BaseDialog(
            title="ClipAI",
            width=460,
            height=300,
            position="cursor",
            background_color="#111111",
            surface_color="#2B2B2B",
            frameless=True,
            transparent_background=True,
            surface_inset=8,
        )
        self._surface = BaseResultSurface(self._dialog)
        self._surface.configure_standard_actions()

    def show_loading(self, *, title: str, source_preview: str, model: str) -> None:
        self._surface.set_title(title)
        self._surface.set_source_preview(source_preview)
        self._surface.set_model(model)
        self._surface.set_loading("Loading result...")

    def show_result(self, text: str) -> None:
        self._dialog.flash("success")
        self._surface.set_content_chunks([(text, "body")])

    def show_error(self, message: str) -> None:
        self._dialog.flash("error")
        self._surface.set_content_chunks([(message, "body")])

    def set_copy_action(self, callback: Callable[[], None] | None) -> None:
        self._surface.configure_standard_actions(on_copy=callback)

    def run(self) -> None:
        self._dialog.run_dialog()
