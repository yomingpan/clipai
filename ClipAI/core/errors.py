class ClipAIError(RuntimeError):
    """Base error with a user-safe message."""

    code = "clipai.error"


class ConfigError(ClipAIError):
    code = "config.invalid"


class InputError(ClipAIError):
    code = "input.invalid"


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


class InternalApplicationError(ClipAIError):
    code = "internal.unexpected"
