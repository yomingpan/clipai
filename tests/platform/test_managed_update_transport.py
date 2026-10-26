from io import BytesIO
from hashlib import sha256
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure
from ClipAI.core.update_preparation import ManagedUpdatePreparation
from ClipAI.platform.managed_update_transport import UrllibManagedUpdateTransport
from ClipAI.platform.managed_update_transport import _response_chunks


@pytest.mark.integration
def test_http_stream_yields_available_bytes_without_waiting_for_the_whole_body():
    first_sent, finish_body = threading.Event(), threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "4")
            self.end_headers()
            self.wfile.write(b"a")
            self.wfile.flush()
            first_sent.set()
            finish_body.wait(2)
            self.wfile.write(b"bcd")
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_address[1]}/bundle", timeout=1) as response:
            assert first_sent.wait(1)
            with ThreadPoolExecutor(max_workers=1) as executor:
                first_chunk = executor.submit(lambda: next(_response_chunks(response)))
                try:
                    assert first_chunk.result(timeout=0.3) == b"a"
                finally:
                    finish_body.set()
    finally:
        finish_body.set()
        server.shutdown()
        server.server_close()
        thread.join(2)


class _Response:
    def __init__(self, content: bytes, *, url: str = "https://updates.example/catalog.json") -> None:
        self._content = BytesIO(content)
        self.headers = {"Content-Length": str(len(content))}
        self.status = 200
        self._url = url

    def read(self, size: int = -1) -> bytes:
        return self._content.read(size)

    def read1(self, size: int = -1) -> bytes:
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


def test_continuous_download_cannot_reset_whole_transfer_deadline(tmp_path):
    clock = [0.0]
    class Trickle(_Response):
        def read1(self, size=-1):
            clock[0] += 2.0
            return self._content.read(1)
    destination = tmp_path / "bundle.zip"
    destination.write_bytes(b"known-good")
    transport = UrllibManagedUpdateTransport(
        open_url=lambda *_args, **_kwargs: Trickle(b"abcdefgh"),
        bundle_deadline_sec=5,
        monotonic=lambda: clock[0],
    )
    with pytest.raises(ManagedUpdateFailure) as failure:
        transport.download_bundle(
            "https://updates.example/bundle.zip", destination,
            expected_size=8, expected_sha256=sha256(b"abcdefgh").hexdigest(),
        )
    assert failure.value.code is FailureCode.DOWNLOAD_FAILED
    assert clock[0] == 6
    assert destination.read_bytes() == b"known-good"
    assert list(tmp_path.glob(".*.tmp")) == []


def test_cancelled_download_cannot_publish_complete_bytes(tmp_path):
    preparation = ManagedUpdatePreparation()
    class CancelOnLastRead(_Response):
        def read1(self, size=-1):
            content = super().read1(size)
            preparation.cancellation.cancel()
            return content
    destination = tmp_path / "bundle.zip"
    transport = UrllibManagedUpdateTransport(
        open_url=lambda *_args, **_kwargs: CancelOnLastRead(b"abc"),
    )
    with pytest.raises(ManagedUpdateFailure) as failure:
        transport.download_bundle(
            "https://updates.example/bundle.zip", destination,
            expected_size=3, expected_sha256=sha256(b"abc").hexdigest(), preparation=preparation,
        )
    assert failure.value.code is FailureCode.DOWNLOAD_FAILED
    assert not destination.exists()
    assert list(tmp_path.glob(".*.tmp")) == []


@pytest.mark.integration
def test_cancelled_stalled_http_worker_settles_at_socket_bound(tmp_path):
    waiting_read, release_server = threading.Event(), threading.Event()
    preparation = ManagedUpdatePreparation()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "4")
            self.end_headers()
            self.wfile.write(b"a")
            self.wfile.flush()
            release_server.wait(2)
        def log_message(self, *_):
            pass
    class AdmittedResponse:
        def __init__(self, response):
            self.response = response
            self.status, self.headers = response.status, response.headers
            self.reads = 0
        def geturl(self):
            return "https://updates.example/bundle.zip"
        def read1(self, size):
            self.reads += 1
            if self.reads == 2:
                waiting_read.set()
            return self.response.read1(size)
        def __enter__(self):
            return self
        def __exit__(self, *_):
            self.response.close()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
    thread.start()
    destination = tmp_path / "bundle.zip"
    destination.write_bytes(b"known-good")
    transport = UrllibManagedUpdateTransport(
        open_url=lambda _request, *, timeout: AdmittedResponse(urlopen(
            f"http://127.0.0.1:{server.server_address[1]}/bundle", timeout=timeout
        )), bundle_timeout_sec=.2,
    )
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            work = executor.submit(
                transport.download_bundle, "https://updates.example/bundle.zip", destination,
                expected_size=4, expected_sha256=sha256(b"abcd").hexdigest(), preparation=preparation,
            )
            try:
                assert waiting_read.wait(1)
                preparation.cancellation.cancel()
                with pytest.raises(ManagedUpdateFailure) as failure:
                    work.result(timeout=1)
                assert failure.value.code is FailureCode.DOWNLOAD_FAILED
                assert destination.read_bytes() == b"known-good"
                assert list(tmp_path.glob(".*.tmp")) == []
            finally:
                release_server.set()
    finally:
        release_server.set()
        server.shutdown()
        server.server_close()
        thread.join(2)
