from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ClipAI.app.config import ActionCatalog, AppConfig, ResolvedAction
from ClipAI.core.provider import ProviderRequest, TextProvider
from ClipAI.platform.clipboard import ClipboardGateway
from ClipAI.platform.hotkey import PressType


class ResultPresenter(Protocol):
    def show_loading(self, *, title: str, source_preview: str, model: str) -> None:
        ...

    def show_result(self, text: str) -> None:
        ...

    def show_error(self, message: str) -> None:
        ...

    def set_copy_action(self, callback: Callable[[], None] | None) -> None:
        ...

    def run(self) -> None:
        ...


@dataclass(frozen=True)
class VerticalSliceOutcome:
    action_id: str
    press_type: PressType
    status: str
    result_text: str = ""
    error: str = ""


class VerticalSliceWorkflow:
    def __init__(
        self,
        *,
        app_config: AppConfig,
        actions: ActionCatalog,
        clipboard: ClipboardGateway,
        provider: TextProvider,
        presenter_factory: Callable[[], ResultPresenter],
    ) -> None:
        self._app_config = app_config
        self._actions = actions
        self._clipboard = clipboard
        self._provider = provider
        self._presenter_factory = presenter_factory

    def run(self, action_id: str, press_type: PressType) -> VerticalSliceOutcome:
        action = self._actions.resolve(action_id, press_type)
        presenter = self._presenter_factory()
        input_text = self._clipboard.read_text().strip()
        source_preview = _source_preview(input_text)
        presenter.show_loading(
            title=action.name,
            source_preview=source_preview,
            model=self._app_config.default_model,
        )

        if not input_text:
            message = "Clipboard is empty. Copy text first, then trigger ClipAI again."
            presenter.show_error(message)
            presenter.set_copy_action(None)
            presenter.run()
            return VerticalSliceOutcome(action_id=action.id, press_type=press_type, status="error", error=message)

        request = ProviderRequest(
            messages=_build_messages(action, input_text),
            model=self._app_config.default_model,
            temperature=self._app_config.temperature,
        )

        try:
            result_text = self._provider.complete(request)
        except Exception as exc:
            message = f"Provider failed: {exc}"
            presenter.show_error(message)
            presenter.set_copy_action(None)
            presenter.run()
            return VerticalSliceOutcome(action_id=action.id, press_type=press_type, status="error", error=message)

        presenter.show_result(result_text)
        presenter.set_copy_action(lambda text=result_text: self._clipboard.write_text(text))
        presenter.run()
        return VerticalSliceOutcome(
            action_id=action.id,
            press_type=press_type,
            status="success",
            result_text=result_text,
        )


def _build_messages(action: ResolvedAction, input_text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": action.system_prompt},
        {"role": "user", "content": action.prompt.format(input=input_text)},
    ]


def _source_preview(input_text: str, limit: int = 90) -> str:
    if not input_text:
        return "Clipboard: empty"
    compact = " ".join(input_text.split())
    if len(compact) <= limit:
        return f"Clipboard: {compact}"
    return f"Clipboard: {compact[: limit - 1]}..."
