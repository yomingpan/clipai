class ClipAIError(RuntimeError):
    """Base error with a user-safe message."""


class ConfigError(ClipAIError):
    pass


class InputError(ClipAIError):
    pass


class ProviderError(ClipAIError):
    pass


class ProviderAuthError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class ProviderUnavailableError(ProviderError):
    pass


class ProviderResponseError(ProviderError):
    pass


class CancelledError(ClipAIError):
    pass


class InternalApplicationError(ClipAIError):
    pass

