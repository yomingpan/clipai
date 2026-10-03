from __future__ import annotations

from ClipAI.core.errors import ProviderAuthError, ProviderResponseError
from ClipAI.providers.http_transport import HttpResponse


_REASONS = {
    "API_KEY_SERVICE_BLOCKED": "This key's API restrictions deny the Gemini API. Check its allowed APIs.",
    "API_KEY_HTTP_REFERRER_BLOCKED": "This key's website restrictions deny this desktop application.",
    "API_KEY_IP_ADDRESS_BLOCKED": "This key's IP restrictions deny this connection.",
    "API_KEY_ANDROID_APP_BLOCKED": "This key is restricted to an Android application.",
    "API_KEY_IOS_APP_BLOCKED": "This key is restricted to an iOS application.",
    "SERVICE_DISABLED": "The Gemini API is disabled for this key's project.",
    "CONSUMER_INVALID": "Google could not authorize this key's project.",
    "BILLING_DISABLED": "Billing is disabled for this key's project.",
}


def raise_for_gemini_error(response: HttpResponse) -> None:
    """Classify Google failures without echoing server text or credentials."""
    if response.status_code < 400:
        return
    error = response.payload.get("error") if isinstance(response.payload, dict) else None
    error = error if isinstance(error, dict) else {}
    details = error.get("details")
    details = details if isinstance(details, list) else []
    reasons = [item.get("reason") for item in details if isinstance(item, dict)]
    if response.status_code == 401 or any(reason in {"API_KEY_INVALID", "API_KEY_EXPIRED"}
                                          for reason in reasons if isinstance(reason, str)):
        raise ProviderAuthError("Gemini rejected the API key")
    for reason in reasons:
        if isinstance(reason, str) and reason in _REASONS:
            raise ProviderResponseError(f"Gemini HTTP {response.status_code} ({reason}): {_REASONS[reason]}")
    # Google currently returns this condition as message text, not ErrorInfo.
    message = error.get("message")
    if isinstance(message, str) and "api key was reported as leaked" in message.casefold():
        raise ProviderResponseError("Gemini blocked this key as leaked. Create a replacement in Google AI Studio.")
    if response.status_code == 403:
        raise ProviderResponseError("Gemini denied access (HTTP 403). Check key restrictions, project permissions and network policy.")
    raise ProviderResponseError(f"Gemini request failed with HTTP {response.status_code}. Check Google AI Studio and try again.")
