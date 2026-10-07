import hashlib
import io
import json

import pytest

from scripts.fetch_setup_inputs import fetch


def _inputs(tmp_path, *, source_name="pygame.tar.gz", source_hash=None):
    body = b"pinned upstream bytes"
    identity = {"url": "https://example.invalid/input", "size": len(body),
                "sha256": hashlib.sha256(body).hexdigest()}
    source = dict(identity, filename=source_name)
    if source_hash:
        source["sha256"] = source_hash
    path = tmp_path / "inputs.json"
    path.write_text(json.dumps({"runtime": identity, "compiler": identity,
                               "corresponding_sources": {"pygame": source}}))
    return path, body


def _network(monkeypatch, body):
    def open_source(url, timeout):
        response = io.BytesIO(body)
        response.url = url
        return response
    monkeypatch.setattr("scripts.fetch_setup_inputs.urllib.request.urlopen", open_source)


def test_pinned_corresponding_source_is_preserved_without_execution(tmp_path, monkeypatch):
    inputs, body = _inputs(tmp_path)
    _network(monkeypatch, body)
    monkeypatch.setattr("scripts.fetch_setup_inputs.subprocess.run",
                        lambda *a, **k: pytest.fail("source archives must not execute"))
    fetch(inputs, tmp_path / "output")
    assert (tmp_path / "output/sources/pygame.tar.gz").read_bytes() == body


def test_corresponding_source_hash_mismatch_is_rejected(tmp_path, monkeypatch):
    inputs, body = _inputs(tmp_path, source_hash="0" * 64)
    _network(monkeypatch, body)
    with pytest.raises(ValueError, match="identity mismatch"):
        fetch(inputs, tmp_path / "output")


@pytest.mark.parametrize("name", ["../outside", "C:/outside", "..\\outside", ".", ""])
def test_unsafe_source_destination_is_rejected_before_download(tmp_path, monkeypatch, name):
    inputs, _ = _inputs(tmp_path, source_name=name)
    monkeypatch.setattr("scripts.fetch_setup_inputs.urllib.request.urlopen",
                        lambda *a, **k: pytest.fail("unsafe input must fail before download"))
    with pytest.raises(ValueError, match="unsafe"):
        fetch(inputs, tmp_path / "output")
