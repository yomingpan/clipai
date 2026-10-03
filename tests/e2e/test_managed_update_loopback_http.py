from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import threading
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

import pytest

from ClipAI.core.managed_update import FailureCode, ManagedUpdateFailure, transaction_id
from ClipAI.core.update_bundle import BundleAdmissionRequest
from ClipAI.core.update_signing import TEST_KEY_ID
from ClipAI.platform.managed_release_builder import ManagedReleaseBuilder, OpenSshManifestSigner
from ClipAI.platform.managed_release_source import HttpsManagedReleaseSource
from ClipAI.platform.managed_update_fs import (
    atomic_write_bytes,
    extract_prefixed_zip,
    file_sha256,
    native_path,
    read_bytes,
    regular_file_inventory,
    write_prefixed_zip,
)
from ClipAI.platform.managed_update_transport import UrllibManagedUpdateTransport
from ClipAI.platform.update_signature import Ed25519ManifestVerifier
from ClipAI.platform.verified_managed_bundle import VerifiedManagedBundleStager


@dataclass(frozen=True)
class _Release:
    bundle: Path
    bundle_sha256: str
    bundle_size: int
    manifest_sha256: str
    verifier: Ed25519ManifestVerifier


class _AdmittedResponse:
    def __init__(self, response, admitted_url: str) -> None:
        self._response = response
        self._admitted_url = admitted_url
        self.headers = response.headers
        self.status = response.status

    def read(self, size: int = -1) -> bytes:
        return self._response.read(size)

    def geturl(self) -> str:
        return self._admitted_url

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self._response.close()


def _loopback_http_open(request: Request, *, timeout: float):
    admitted = urlsplit(request.full_url)
    if admitted.scheme != "https" or admitted.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise AssertionError("loopback harness received a non-admitted URL")
    local_url = urlunsplit(("http", admitted.netloc, admitted.path, admitted.query, ""))
    forwarded = Request(
        local_url,
        headers=dict(request.header_items()),
        method=request.get_method(),
    )
    return _AdmittedResponse(urlopen(forwarded, timeout=timeout), request.full_url)


@contextmanager
def _release_server(release: _Release):
    responses: dict[str, tuple[str, bytes]] = {}
    requests: list[tuple[str, str | None, str | None]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requests.append((self.path, self.headers.get("Accept"), self.headers.get("User-Agent")))
            response = responses.get(self.path)
            if response is None:
                self.send_error(404)
                return
            content_type, content = response
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, _format: str, *_args) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    bundle_url = f"https://127.0.0.1:{port}/clipai.zip"
    responses["/catalog.json"] = ("application/json", json.dumps({
        "schema_version": 1,
        "catalog_kind": "clipai-managed-update-v1",
        "channel": "stable",
        "generated_at": "2026-09-13T00:00:00Z",
        "releases": [{
            "version": "2.0",
            "bundle_url": bundle_url,
            "bundle_sha256": release.bundle_sha256,
            "bundle_size": release.bundle_size,
            "manifest_sha256": release.manifest_sha256,
            "key_id": TEST_KEY_ID,
            "minimum_launcher_version": "1.0",
        }],
    }).encode("utf-8"))
    responses["/clipai.zip"] = ("application/octet-stream", read_bytes(release.bundle))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{port}/catalog.json", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def _build_release(tmp_path: Path, *, tamper_signature: bool = False) -> _Release:
    ssh_keygen = shutil.which("ssh-keygen")
    assert ssh_keygen is not None, "Windows OpenSSH ssh-keygen is required"
    private_key = tmp_path / "fixture-key"
    subprocess.run(
        [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)],
        check=True,
        capture_output=True,
    )
    payload = tmp_path / "payload"
    wheelhouse = tmp_path / "wheelhouse"
    payload.mkdir()
    wheelhouse.mkdir()
    atomic_write_bytes(payload / "main.py", b"print('loopback candidate')\n")
    atomic_write_bytes(wheelhouse / "clipai-2.0.whl", b"loopback-wheel")
    requirements_lock = tmp_path / "requirements.lock"
    requirements_lock.write_text("clipai==2.0\n", encoding="utf-8")
    signer = OpenSshManifestSigner(
        ssh_keygen=ssh_keygen,
        private_key=private_key,
        work_root=tmp_path / "sign-work",
        environment=dict(os.environ),
    )
    result = ManagedReleaseBuilder(signer).build(
        payload_root=payload,
        wheelhouse_root=wheelhouse,
        requirements_lock=requirements_lock,
        output_path=tmp_path / "clipai-2.0.zip",
        app_version="2.0",
        entrypoint="payload/main.py",
        python_requires=">=3.12,<3.13",
        key_id=TEST_KEY_ID,
    )
    bundle = result.bundle_path
    if tamper_signature:
        extracted = tmp_path / "tampered"
        extract_prefixed_zip(bundle, extracted)
        atomic_write_bytes(extracted / "install-manifest.json.sig", b"tampered-signature")
        members = {
            relative: read_bytes(extracted.joinpath(*PurePosixPath(relative).parts))
            for relative in regular_file_inventory(extracted)
        }
        bundle = tmp_path / "clipai-2.0-tampered.zip"
        write_prefixed_zip(bundle, members)
    public_key = private_key.with_suffix(".pub").read_text(encoding="ascii")
    verifier = Ed25519ManifestVerifier(
        ssh_keygen=ssh_keygen,
        trusted_keys={TEST_KEY_ID: public_key},
        work_root=tmp_path / "verify-work",
        environment=dict(os.environ),
        allow_test_keys=True,
    )
    return _Release(
        bundle,
        file_sha256(bundle),
        native_path(bundle).stat().st_size,
        result.manifest_sha256,
        verifier,
    )


def _download(tmp_path: Path, release_fixture: _Release):
    with _release_server(release_fixture) as (catalog_url, requests):
        source = HttpsManagedReleaseSource(
            catalog_url=catalog_url,
            transport=UrllibManagedUpdateTransport(open_url=_loopback_http_open),
        )
        release = source.discover(installed_version="1.0", launcher_version="1.0")
        assert release is not None
        tid = transaction_id("loopback-http")
        shared_root = (tmp_path / "shared").resolve()
        bundle = source.download(release, shared_root=shared_root, transaction_id=tid)
    assert requests == [
        ("/catalog.json", "application/json", "ClipAI-Managed-Update/1"),
        ("/clipai.zip", "application/octet-stream", "ClipAI-Managed-Update/1"),
    ]
    return release, shared_root, tid, bundle


@pytest.mark.integration
def test_loopback_catalog_download_and_real_signature_admission(tmp_path: Path) -> None:
    fixture = _build_release(tmp_path)
    release, shared_root, tid, bundle = _download(tmp_path, fixture)
    staged = VerifiedManagedBundleStager(manifest_verifier=fixture.verifier).stage(
        BundleAdmissionRequest(
            shared_root / "managed-update" / "transactions" / str(tid),
            bundle,
            release.bundle_size,
            release.bundle_sha256,
            release.manifest_sha256,
            release.version,
            release.key_id,
        )
    )
    assert staged.manifest.app_version == "2.0"
    assert read_bytes(staged.staging_root / "payload" / "main.py") == b"print('loopback candidate')\n"


@pytest.mark.integration
def test_loopback_signature_tampering_fails_closed(tmp_path: Path) -> None:
    fixture = _build_release(tmp_path, tamper_signature=True)
    release, shared_root, tid, bundle = _download(tmp_path, fixture)
    with pytest.raises(ManagedUpdateFailure) as failure:
        VerifiedManagedBundleStager(manifest_verifier=fixture.verifier).stage(
            BundleAdmissionRequest(
                shared_root / "managed-update" / "transactions" / str(tid),
                bundle,
                release.bundle_size,
                release.bundle_sha256,
                release.manifest_sha256,
                release.version,
                release.key_id,
            )
        )
    assert failure.value.code is FailureCode.SIGNATURE_INVALID
