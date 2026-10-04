from dataclasses import replace
import io
import json
from pathlib import Path
import subprocess
import tarfile
from zipfile import ZipFile

import pytest

from ClipAI.core.managed_update import ManagedUpdateFailure
from ClipAI.platform.managed_release_builder import ManagedReleaseBuilder, write_release_publication
from ClipAI.platform.managed_update_fs import file_sha256
from ClipAI.platform import setup_release_builder as module
from ClipAI.platform.setup_release_builder import SetupBuildRequest, SetupReleaseBuilder


class Signer:
    def sign(self, manifest):
        return b"fixture signature"


def identity(path):
    return {"size": path.stat().st_size, "sha256": file_sha256(path)}


@pytest.fixture
def build_request(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime.tar.gz"
    with tarfile.open(runtime, "w:gz") as archive:
        for name in ("python/python.exe", "python/pythonw.exe", "python/LICENSE.txt"):
            m = tarfile.TarInfo(name)
            m.size = 7
            archive.addfile(m, io.BytesIO(b"fixture"))
    verifier = tmp_path / "verifier.zip"
    with ZipFile(verifier, "w") as archive:
        for name in ("ssh-keygen.exe", "libcrypto.dll", "LICENSE.txt", "NOTICE.txt"):
            archive.writestr("OpenSSH-Win64/" + name, b"fixture")
    compiler = tmp_path / "compiler/ISCC.exe"
    compiler.parent.mkdir()
    compiler.write_bytes(b"compiler fixture")
    (compiler.parent / "license.txt").write_bytes(b"license")
    inputs = tmp_path / "inputs.json"
    inputs.write_text(json.dumps({"platform": "windows-x64", "python_abi": "cp312",
        "distribution_admission": "approved", "runtime": {**identity(runtime), "runtime_version": "3.12.14"},
        "verifier": identity(verifier), "compiler": {"files": {"ISCC.exe": identity(compiler)}}}))
    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "main.py").write_bytes(b"entry fixture")
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    with ZipFile(wheelhouse / "clipai-3.7.8-py3-none-any.whl", "w") as archive:
        archive.writestr("ClipAI/app/first_install_bootstrap.py", b"wheel bootstrap fixture")
        archive.writestr("ClipAI/ui/assets/clipai.ico", b"icon")
    with ZipFile(wheelhouse / "packaging-26.0-py3-none-any.whl", "w") as archive:
        archive.writestr("packaging/__init__.py", b"packaging fixture")
    lock = tmp_path / "requirements.lock"
    lock.write_bytes(b"fixture lock")
    release = ManagedReleaseBuilder(Signer()).build(payload_root=payload, wheelhouse_root=wheelhouse,
        requirements_lock=lock, output_path=tmp_path / "bundle.zip", app_version="3.7.8",
        entrypoint="payload/main.py", python_requires=">=3.12,<3.13", key_id="release-2026")
    keyring = tmp_path / "keys.json"
    keyring.write_text(json.dumps({"schema_version": 1, "keyring_kind": "clipai-managed-update-trusted-keys-v1",
        "keys": [{"key_id": "release-2026", "algorithm": "ssh-ed25519", "public_key": "ssh-ed25519 AAAAfixture", "key_kind": "production"}]}))
    catalog = tmp_path / "catalog.json"
    write_release_publication(result=release, catalog_path=catalog, trusted_keyring=keyring,
        trusted_keyring_output=tmp_path / "published-keys.json", app_version="3.7.8",
        bundle_url="https://github.com/yomingpan/clipai/releases/download/v3.7.8/clipai-managed-3.7.8.zip",
        key_id="release-2026", minimum_launcher_version="3.7.3", generated_at="2026-10-04T00:00:00+00:00")
    monkeypatch.setattr(module.Ed25519ManifestVerifier, "verify", lambda *a, **kw: None)
    def compile(command, **kwargs):
        assert command[0] == str(compiler)
        assert kwargs["env"]["PATH"] == ""
        definitions = dict(arg[2:].split("=", 1) for arg in command[1:-1])
        path = Path(definitions["OutputRoot"]) / (definitions["OutputName"] + ".exe")
        path.write_bytes(b"compiled fixture")
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(module.subprocess, "run", compile)
    wizard = tmp_path / "setup.iss"
    wizard.write_bytes(b"wizard fixture")
    (tmp_path / "entry.py").write_bytes(b"entry fixture")
    return SetupBuildRequest(tmp_path / "bundle.zip", catalog, keyring, inputs, runtime, verifier,
                             compiler, wizard, tmp_path / "candidate", "v3.7.8", "a" * 40)


def test_setup_consumes_identical_bundle_and_wheel_bootstrap(build_request):
    setup = SetupReleaseBuilder(environment={}).build(build_request)
    root = build_request.output_root
    assert setup.is_file()
    assert (root / "stage/bundle.zip").read_bytes() == build_request.bundle.read_bytes()
    assert (root / "stage/setup-engine/ClipAI/app/first_install_bootstrap.py").read_bytes() == b"wheel bootstrap fixture"
    proof = json.loads((root / "output/provenance.json").read_text())
    assert proof["bundle"] == identity(build_request.bundle)
    assert proof["release_ready"] is False
    assert proof["setup"]["sha256"] == file_sha256(setup)


@pytest.mark.parametrize("field", ["bundle_sha256", "manifest_sha256", "version", "bundle_size"])
def test_catalog_substitution_is_rejected_before_compile(build_request, field):
    catalog = json.loads(build_request.catalog.read_text())
    release = catalog["releases"][0]
    release[field] = "b" * 64 if field.endswith("sha256") else ("3.7.9" if field == "version" else release[field] + 1)
    build_request.catalog.write_text(json.dumps(catalog))
    with pytest.raises((ManagedUpdateFailure, ValueError)):
        SetupReleaseBuilder(environment={}).build(build_request)
    assert not list(build_request.output_root.glob("output/*.exe"))


def test_different_keyring_cannot_bypass_stager(build_request, monkeypatch):
    def reject(*args, **kwargs):
        raise ValueError("signature rejected")
    monkeypatch.setattr(module.Ed25519ManifestVerifier, "verify", reject)
    with pytest.raises(ManagedUpdateFailure):
        SetupReleaseBuilder(environment={}).build(build_request)


@pytest.mark.parametrize("component", ["runtime_archive", "verifier_archive", "compiler"])
def test_modified_pinned_input_is_rejected_before_execution(build_request, component):
    getattr(build_request, component).write_bytes(b"substitution")
    with pytest.raises(ValueError, match="identity mismatch"):
        SetupReleaseBuilder(environment={}).build(build_request)
    assert not build_request.output_root.exists()


def test_unapproved_distribution_blocks_official_but_allows_isolated_technical(build_request):
    inputs = json.loads(build_request.inputs.read_text())
    inputs["distribution_admission"] = "pending"
    build_request.inputs.write_text(json.dumps(inputs))
    with pytest.raises(ValueError, match="admission"):
        SetupReleaseBuilder(environment={}).build(build_request)
    setup = SetupReleaseBuilder(environment={}).build(replace(build_request, technical_candidate=True))
    metadata = json.loads((build_request.output_root / "stage/setup-engine/candidate.json").read_text())
    assert metadata["product"] == "ClipAI Candidate"
    assert "Candidate" in setup.name


def test_no_overwrite_of_candidate_output(build_request):
    build_request.output_root.mkdir()
    sentinel = build_request.output_root / "user.txt"
    sentinel.write_text("keep")
    with pytest.raises(FileExistsError):
        SetupReleaseBuilder(environment={}).build(build_request)
    assert sentinel.read_text() == "keep"


@pytest.mark.parametrize("tag,commit", [("v3.7.9", "a" * 40), ("v3.7.8", "short")])
def test_invalid_source_identity_is_rejected(build_request, tag, commit):
    with pytest.raises(ValueError):
        SetupReleaseBuilder(environment={}).build(replace(build_request, tag=tag, source_commit=commit))


def candidate_assets(build_request, *, technical=False):
    SetupReleaseBuilder(environment={}).build(replace(build_request, technical_candidate=technical))
    assets = build_request.output_root / "output"
    proof = json.loads((assets / "provenance.json").read_text())
    for name in ("packaged-smoke.json", "setup-extraction.json"):
        (assets / name).write_text(json.dumps({"status": "passed", "setup_sha256": proof["setup"]["sha256"],
                                              "bundle_sha256": proof["bundle"]["sha256"]}))
    return assets


def test_complete_candidate_passes_asset_check(build_request):
    from scripts.verify_release_assets import verify
    assert verify(candidate_assets(build_request))["release_ready"] is False


@pytest.mark.parametrize("asset", ["setup", "bundle", "catalog.json", "managed-update-trusted-keys.json", "packaged-smoke.json", "setup-extraction.json"])
def test_asset_or_evidence_substitution_blocks_candidate(build_request, asset):
    from scripts.verify_release_assets import verify
    assets = candidate_assets(build_request)
    proof = json.loads((assets / "provenance.json").read_text())
    name = proof["setup"]["filename"] if asset == "setup" else ("clipai-managed-3.7.8.zip" if asset == "bundle" else asset)
    (assets / name).write_bytes(b"{}")
    with pytest.raises((ValueError, KeyError)):
        verify(assets)


def test_technical_candidate_cannot_pass_publication_gate(build_request):
    from scripts.verify_release_assets import verify
    with pytest.raises(ValueError, match="cannot be published"):
        verify(candidate_assets(build_request, technical=True), require_release_ready=True)


def test_unsigned_candidate_without_acceptance_cannot_pass_publication_gate(build_request):
    from scripts.verify_release_assets import verify
    with pytest.raises(ValueError, match="acceptance"):
        verify(candidate_assets(build_request), require_release_ready=True)


def test_runtime_symlink_is_rejected_before_extraction(tmp_path):
    archive = tmp_path / "linked.tar.gz"
    with tarfile.open(archive, "w:gz") as target:
        member = tarfile.TarInfo("python/python.exe")
        member.type = tarfile.SYMTYPE
        member.linkname = "../../user-file"
        target.addfile(member)
    destination = tmp_path / "extracted"
    with pytest.raises(ValueError, match="unsafe runtime"):
        module._extract_runtime(archive, destination)
    assert not destination.exists()
