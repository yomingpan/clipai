from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure
from ClipAI.platform.managed_update_fs import ManagedUpdateFileError, atomic_write_verified_chunks
from ClipAI.platform.update_catalog import MAX_BUNDLE_SIZE


MAX_CATALOG_SIZE = 1024 * 1024
CATALOG_TIMEOUT_SEC = 12.0
BUNDLE_TIMEOUT_SEC = 20.0
USER_AGENT = "ClipAI-Managed-Update/1"
OpenUrl = Callable[..., Any]


class _BoundedHttpsRedirectHandler(HTTPRedirectHandler):
    max_redirections = 3

    def redirect_request(self, request, fp, code, message, headers, new_url):
        _require_https_url(new_url)
        return super().redirect_request(request, fp, code, message, headers, new_url)


def _open_url(request: Request, *, timeout: float):
    return build_opener(_BoundedHttpsRedirectHandler()).open(request, timeout=timeout)


class UrllibManagedUpdateTransport:
    """Fetch bounded managed-update documents through admitted HTTPS URLs."""

    def __init__(
        self,
        *,
        open_url: OpenUrl = _open_url,
        catalog_timeout_sec: float = CATALOG_TIMEOUT_SEC,
        maximum_catalog_size: int = MAX_CATALOG_SIZE,
        bundle_timeout_sec: float = BUNDLE_TIMEOUT_SEC,
    ) -> None:
        if catalog_timeout_sec <= 0 or maximum_catalog_size <= 0 or bundle_timeout_sec <= 0:
            raise ValueError("managed update transport bounds must be positive")
        self._open_url = open_url
        self._catalog_timeout_sec = catalog_timeout_sec
        self._maximum_catalog_size = maximum_catalog_size
        self._bundle_timeout_sec = bundle_timeout_sec

    def fetch_catalog(self, url: str) -> bytes:
        _require_https_url(url)
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="GET",
        )
        try:
            with self._open_url(request, timeout=self._catalog_timeout_sec) as response:
                _require_https_url(response.geturl())
                if getattr(response, "status", None) != 200:
                    raise ManagedUpdateFailure(FailureCode.CATALOG_INVALID, "catalog response status is invalid")
                length = _content_length(response.headers)
                if length is not None and length > self._maximum_catalog_size:
                    raise ManagedUpdateFailure(FailureCode.CATALOG_INVALID, "catalog response exceeds size limit")
                content = response.read(self._maximum_catalog_size + 1)
                if len(content) > self._maximum_catalog_size:
                    raise ManagedUpdateFailure(FailureCode.CATALOG_INVALID, "catalog response exceeds size limit")
                return content
        except ManagedUpdateFailure:
            raise
        except (HTTPError, URLError, OSError) as exc:
            raise ManagedUpdateFailure(FailureCode.CATALOG_UNAVAILABLE, "catalog request failed") from exc

    def download_bundle(
        self,
        url: str,
        destination: str | Path,
        *,
        expected_size: int,
        expected_sha256: str,
    ) -> Path:
        _require_bundle_url(url)
        request = Request(
            url,
            headers={
                "Accept": "application/octet-stream",
                "User-Agent": USER_AGENT,
            },
            method="GET",
        )
        try:
            with self._open_url(request, timeout=self._bundle_timeout_sec) as response:
                _require_bundle_url(response.geturl())
                if getattr(response, "status", None) != 200:
                    raise ManagedUpdateFailure(FailureCode.DOWNLOAD_FAILED, "bundle response status is invalid")
                length = _content_length(response.headers)
                if length is not None and length != expected_size:
                    raise ManagedUpdateFailure(FailureCode.DOWNLOAD_FAILED, "bundle content length does not match")
                return atomic_write_verified_chunks(
                    destination,
                    _response_chunks(response),
                    expected_size=expected_size,
                    expected_sha256=expected_sha256,
                    maximum_size=MAX_BUNDLE_SIZE,
                )
        except ManagedUpdateFailure as exc:
            if exc.code is FailureCode.CATALOG_INVALID:
                raise ManagedUpdateFailure(FailureCode.DOWNLOAD_FAILED, "bundle response admission failed") from exc
            raise
        except (HTTPError, URLError, OSError, ManagedUpdateFileError) as exc:
            raise ManagedUpdateFailure(FailureCode.DOWNLOAD_FAILED, "bundle download failed") from exc


def _require_https_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ManagedUpdateFailure(FailureCode.CATALOG_INVALID, "catalog URL is invalid") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port is not None and not 1 <= port <= 65535
    ):
        raise ManagedUpdateFailure(FailureCode.CATALOG_INVALID, "catalog URL is invalid")


def _content_length(headers: Any) -> int | None:
    value = headers.get("Content-Length")
    if value is None:
        return None
    try:
        length = int(value)
    except (TypeError, ValueError) as exc:
        raise ManagedUpdateFailure(FailureCode.CATALOG_INVALID, "catalog content length is invalid") from exc
    if length < 0:
        raise ManagedUpdateFailure(FailureCode.CATALOG_INVALID, "catalog content length is invalid")
    return length


def _require_bundle_url(url: str) -> None:
    try:
        _require_https_url(url)
    except ManagedUpdateFailure as exc:
        raise ManagedUpdateFailure(FailureCode.DOWNLOAD_FAILED, "bundle URL is invalid") from exc


def _response_chunks(response: Any):
    while chunk := response.read(1024 * 1024):
        yield chunk
