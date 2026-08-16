from typing import Literal


PasteFailureReason = Literal[
    "no_target_observed",
    "target_gone",
    "target_refused_focus",
    "target_focus_timeout",
    "target_changed",
    "modifiers_held",
    "another_paste_active",
    "clipboard_unavailable",
    "unknown",
]


PASTE_FAILURE_MESSAGES: dict[PasteFailureReason, str] = {
    "no_target_observed": "尚未觀測到可貼上的目標視窗。請先點選要貼入的視窗，再回到 ClipAI。",
    "target_gone": "原本的貼上目標已關閉或失效。",
    "target_refused_focus": "貼上目標拒絕取得前景焦點。",
    "target_focus_timeout": "等待貼上目標取得前景焦點時逾時。",
    "target_changed": "前景視窗在送出貼上前已改變。",
    "modifiers_held": "鍵盤修飾鍵持續按住，為避免誤輸入而未送出貼上。",
    "another_paste_active": "另一個貼上操作仍在進行中。",
    "clipboard_unavailable": "剪貼簿目前無法使用，因此未送出貼上。",
    "unknown": "貼上未送出，且無法判定具體原因。",
}


class ClipAIError(RuntimeError):
    """Base error with a user-safe message."""

    code = "clipai.error"


class ConfigError(ClipAIError):
    code = "config.invalid"


class InputError(ClipAIError):
    code = "input.invalid"


class PersonalStyleUnavailableError(InputError):
    code = "personal_style.unavailable"


class ProviderError(ClipAIError):
    code = "provider.error"


class ProviderAuthError(ProviderError):
    code = "provider.auth"


class ProviderTimeoutError(ProviderError):
    code = "provider.timeout"


class ProviderUnavailableError(ProviderError):
    code = "provider.unavailable"


class ProviderResponseError(ProviderError):
    code = "provider.response"


class CancelledError(ClipAIError):
    code = "operation.cancelled"


class PasteFailure(ClipAIError):
    code = "paste.failed"

    def __init__(self, reason: PasteFailureReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class InternalApplicationError(ClipAIError):
    code = "internal.unexpected"
