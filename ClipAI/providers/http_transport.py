from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import requests

from ClipAI.core.errors import ProviderTimeoutError, ProviderUnavailableError


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    text: str
    payload: Any


class HttpTransport(Protocol):
    def post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: dict[str, Any],
        timeout: float,
    ) -> HttpResponse: ...


class RequestsHttpTransport:
    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: dict[str, Any],
        timeout: float,
    ) -> HttpResponse:
        try:
            response = self._session.post(url, headers=headers, params=params, json=json, timeout=timeout)
        except requests.exceptions.Timeout as exc:
            raise ProviderTimeoutError("AI request timed out") from exc
        except requests.exceptions.ConnectionError as exc:
            raise ProviderUnavailableError("AI service connection failed") from exc
        except requests.exceptions.RequestException as exc:
            raise ProviderUnavailableError("AI request failed") from exc
        try:
            payload = response.json()
        except ValueError:
            payload = None
        return HttpResponse(status_code=response.status_code, text=response.text, payload=payload)

