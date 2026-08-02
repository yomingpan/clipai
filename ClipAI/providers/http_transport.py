from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from ClipAI.core.errors import ProviderTimeoutError, ProviderUnavailableError


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    text: str
    payload: Any


@dataclass(frozen=True)
class HttpLineResponse:
    status_code: int
    lines: AsyncIterator[str]


class HttpTransport(Protocol):
    async def start(self) -> None: ...
    async def close(self) -> None: ...

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        timeout: float,
    ) -> HttpResponse: ...

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: dict[str, Any],
        timeout: float,
    ) -> HttpResponse: ...

    def stream_lines(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: dict[str, Any],
        timeout: float,
    ) -> AbstractAsyncContextManager[HttpLineResponse]: ...


class HttpxAsyncTransport:
    """One loop-confined AsyncClient shared by every provider adapter."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
            )

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    async def post(self, url: str, **kwargs: Any) -> HttpResponse:
        return await self._request("POST", url, **kwargs)

    async def get(self, url: str, **kwargs: Any) -> HttpResponse:
        return await self._request("GET", url, **kwargs)

    async def _request(self, method: str, url: str, **kwargs: Any) -> HttpResponse:
        try:
            response = await self._require_client().request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("AI request timed out") from exc
        except httpx.RequestError as exc:
            raise ProviderUnavailableError("AI service connection failed") from exc
        try:
            payload = response.json()
        except ValueError:
            payload = None
        return HttpResponse(response.status_code, response.text, payload)

    @asynccontextmanager
    async def stream_lines(self, url: str, **kwargs: Any) -> AsyncIterator[HttpLineResponse]:
        try:
            async with self._require_client().stream("POST", url, **kwargs) as response:
                yield HttpLineResponse(response.status_code, response.aiter_lines())
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("AI request timed out") from exc
        except httpx.RequestError as exc:
            raise ProviderUnavailableError("AI service connection failed") from exc

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("HTTP transport has not started")
        return self._client
