from io import BytesIO
from hashlib import sha256
from pathlib import Path
from urllib.error import URLError

import pytest

from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure
from ClipAI.platform.managed_update_transport import UrllibManagedUpdateTransport


class _Response:
    def __init__(self, content: bytes, *, url: str = "https://updates.example/catalog.json") -> None:
        self._content = BytesIO(content)
        self.headers = {"Content-Length": str(len(content))}
        self.status = 200
        self._url = url

    def read(self, size: int = -1) -> bytes:
        return self._content.read(size)

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        return None


def test_catalog_transport_fetches_one_bounded_https_document_with_explicit_identity():
    observed = []

    def open_url(request, *, timeout):
        observed.append((request, timeout))
        return _Response(b'{"schema_version":1}')

    transport = UrllibManagedUpdateTransport(open_url=open_url)

    content = transport.fetch_catalog("https://updates.example/catalog.json")

    assert content == b'{"schema_version":1}'
    request, timeout = observed[0]
    assert request.full_url == "https://updates.example/catalog.json"
    assert request.get_header("User-agent") == "ClipAI-Managed-Update/1"
    assert request.get_header("Accept") == "application/json"
    assert timeout == 12.0


@pytest.mark.parametrize(
    "url",
    [
        "http://updates.example/catalog.json",
        "https://user:secret@updates.example/catalog.json",
        "file:///catalog.json",
    ],
)
def test_catalog_transport_rejects_non_https_or_credentialed_urls_before_network(url: str):
    transport = UrllibManagedUpdateTransport(
        open_url=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network used")),
    )

    with pytest.raises(ManagedUpdateFailure) as failure:
        transport.fetch_catalog(url)

    assert failure.value.code is FailureCode.CATALOG_INVALID


def test_catalog_transport_rejects_oversized_body_even_when_length_header_is_false():
    response = _Response(b"12345")
    response.headers["Content-Length"] = "1"
    transport = UrllibManagedUpdateTransport(
        open_url=lambda _request, *, timeout: response,
        maximum_catalog_size=4,
    )

    with pytest.raises(ManagedUpdateFailure) as failure:
        transport.fetch_catalog("https://updates.example/catalog.json")

    assert failure.value.code is FailureCode.CATALOG_INVALID


def test_catalog_transport_maps_network_failure_without_parsing_content():
    transport = UrllibManagedUpdateTransport(
        open_url=lambda _request, *, timeout: (_ for _ in ()).throw(URLError("offline")),
    )

    with pytest.raises(ManagedUpdateFailure) as failure:
        transport.fetch_catalog("https://updates.example/catalog.json")

    assert failure.value.code is FailureCode.CATALOG_UNAVAILABLE


def test_bundle_transport_streams_exact_catalog_identity_into_atomic_destination(tmp_path: Path):
    content = b"managed-bundle-content"
    observed = []

    def open_url(request, *, timeout):
        observed.append((request, timeout))
        return _Response(content, url="https://updates.example/clipai.zip")

    destination = tmp_path / "transaction" / "bundle.zip"
    transport = UrllibManagedUpdateTransport(open_url=open_url)

    result = transport.download_bundle(
        "https://updates.example/clipai.zip",
        destination,
        expected_size=len(content),
        expected_sha256=sha256(content).hexdigest(),
    )

    assert result == destination.resolve()
    assert destination.read_bytes() == content
    request, timeout = observed[0]
    assert request.get_header("Accept") == "application/octet-stream"
    assert timeout == 20.0


def test_bundle_transport_hash_failure_preserves_existing_destination(tmp_path: Path):
    destination = tmp_path / "bundle.zip"
    destination.write_bytes(b"known-good")
    transport = UrllibManagedUpdateTransport(
        open_url=lambda _request, *, timeout: _Response(b"replacement"),
    )

    with pytest.raises(ManagedUpdateFailure) as failure:
        transport.download_bundle(
            "https://updates.example/clipai.zip",
            destination,
            expected_size=len(b"replacement"),
            expected_sha256="0" * 64,
        )

    assert failure.value.code is FailureCode.DOWNLOAD_FAILED
    assert destination.read_bytes() == b"known-good"
