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
    compiler = tmp_path / "compiler/ISCC.exe"
    compiler.parent.mkdir()
    compiler.write_bytes(b"compiler fixture")
    (compiler.parent / "license.txt").write_bytes(b"license")
    inputs = tmp_path / "inputs.json"
    notice = tmp_path / "third-party-notices/dependency-LICENSE.txt"
    notice.parent.mkdir()
    notice.write_bytes(b"upstream notice fixture")
    inputs.write_text(json.dumps({"platform": "windows-x64", "python_abi": "cp312",
        "distribution_admission": "approved", "runtime": {**identity(runtime), "runtime_version": "3.12.14"},
        "verifier": {"profile": "cryptography-ed25519-sshsig-v1", "version": "50.0.2"},
        "compiler": {"files": {"ISCC.exe": identity(compiler)}},
        "additional_notices": {"dependency-LICENSE.txt": identity(notice)}}))
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
    for name, version in (("cryptography", "50.0.2"), ("cffi", "2.1.0"), ("pycparser", "3.0")):
        with ZipFile(wheelhouse / f"{name}-{version}-py3-none-any.whl", "w") as archive:
            archive.writestr(f"{name}/__init__.py", b"verifier fixture")
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
    return SetupBuildRequest(tmp_path / "bundle.zip", catalog, keyring, inputs, runtime,
                             compiler, wizard, tmp_path / "candidate", "v3.7.8", "a" * 40)


def test_setup_consumes_identical_bundle_and_wheel_bootstrap(build_request):
    setup = SetupReleaseBuilder(environment={}).build(build_request)
    root = build_request.output_root
    assert setup.is_file()
    assert (root / "stage/runtime/python.exe").read_bytes() == b"fixture"
    assert not (root / "runtime-source").exists()
    assert (root / "stage/bundle.zip").read_bytes() == build_request.bundle.read_bytes()
    assert (root / "stage/setup-engine/ClipAI/app/first_install_bootstrap.py").read_bytes() == b"wheel bootstrap fixture"
    proof = json.loads((root / "output/provenance.json").read_text())
    assert proof["bundle"] == identity(build_request.bundle)
    assert proof["release_ready"] is False
    assert proof["setup"]["sha256"] == file_sha256(setup)
    assert (root / "stage/setup-engine/third-party-notices/dependency-LICENSE.txt").read_bytes() == b"upstream notice fixture"
    assert not (root / "stage/tools/ssh-keygen.exe").exists()
    for dependency in ("cryptography", "cffi", "pycparser"):
        assert (root / f"stage/setup-engine/{dependency}/__init__.py").read_bytes() == b"verifier fixture"


def test_unrecognized_verifier_profile_cannot_be_shipped(build_request):
    inputs = json.loads(build_request.inputs.read_text())
    inputs["verifier"]["profile"] = "unreviewed-fallback"
    build_request.inputs.write_text(json.dumps(inputs))
    with pytest.raises(ValueError, match="verifier input"):
        SetupReleaseBuilder(environment={}).build(build_request)
    assert not build_request.output_root.exists()


def test_changed_pinned_notice_blocks_packaging_before_execution(build_request):
    (build_request.inputs.parent / "third-party-notices/dependency-LICENSE.txt").write_bytes(b"substituted")
    with pytest.raises(ValueError, match="identity mismatch"):
        SetupReleaseBuilder(environment={}).build(build_request)
    assert not build_request.output_root.exists()


@pytest.mark.parametrize("name", ["pygame/docs/generated/LGPL.txt", "python/tcl/tk8.6/license.terms", "vendor/licenses/SDL.txt"])
def test_upstream_notice_locations_are_recognized(name):
    assert module._notice_name(name)


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


@pytest.mark.parametrize("component", ["runtime_archive", "compiler"])
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


@pytest.mark.parametrize("change", ["none", "missing", "substituted"])
def test_corresponding_source_bytes_are_required_in_release_assets(build_request, change):
    from scripts.verify_release_assets import verify
    source = build_request.inputs.parent / "dependency-source.tar.gz"
    source.write_bytes(b"corresponding source fixture")
    inputs = json.loads(build_request.inputs.read_text())
    inputs["corresponding_sources"] = {"dependency": {"filename": source.name, **identity(source)}}
    build_request.inputs.write_text(json.dumps(inputs))
    assets = candidate_assets(build_request)
    (assets / "sources").mkdir()
    target = assets / "sources" / source.name
    if change != "missing":
        target.write_bytes(source.read_bytes() if change == "none" else b"substituted")
    if change == "none":
        assert verify(assets)["status"] == "passed"
    else:
        with pytest.raises((ValueError, FileNotFoundError)):
            verify(assets)


@pytest.mark.parametrize("asset", ["setup", "bundle", "catalog.json", "managed-update-trusted-keys.json", "packaged-smoke.json", "setup-extraction.json"])
def test_asset_or_evidence_substitution_blocks_candidate(build_request, asset):
    from scripts.verify_release_assets import verify
    assets = candidate_assets(build_request)
    proof = json.loads((assets / "provenance.json").read_text())
    name = proof["setup"]["filename"] if asset == "setup" else ("clipai-managed-3.7.8.zip" if asset == "bundle" else asset)
    (assets / name).write_bytes(b"{}")
    rejection = ManagedUpdateFailure if asset == "bundle" else (ValueError, KeyError)
    with pytest.raises(rejection):
        verify(assets)


def test_technical_candidate_cannot_pass_publication_gate(build_request):
    from scripts.verify_release_assets import verify
    with pytest.raises(ValueError, match="cannot be published"):
        verify(candidate_assets(build_request, technical=True), require_release_ready=True)


def test_unsigned_candidate_without_acceptance_cannot_pass_publication_gate(build_request):
    from scripts.verify_release_assets import verify
    with pytest.raises(ValueError, match="acceptance"):
        verify(candidate_assets(build_request), require_release_ready=True)


def release_acceptance(assets, *, publisher_policy="unsigned"):
    from scripts.verify_release_assets import REQUIRED_GATES
    proof = json.loads((assets / "provenance.json").read_text())
    acceptance = assets / "acceptance.json"
    acceptance.write_text(json.dumps({
        "setup_sha256": proof["setup"]["sha256"],
        "bundle_sha256": proof["bundle"]["sha256"],
        "publisher_policy": publisher_policy,
        "gates": {gate: "passed" for gate in REQUIRED_GATES},
    }))
    return acceptance


def test_explicit_unsigned_release_checks_real_signature_status_and_retains_other_gates(build_request, monkeypatch):
    from scripts import verify_release_assets as verifier
    assets = candidate_assets(build_request)
    acceptance = release_acceptance(assets)
    checked = []
    def inspect(setup):
        checked.append(setup)
        return {"status": "NotSigned", "publisher": None, "timestamp": None}
    monkeypatch.setattr(verifier, "_inspect_signature", inspect)
    result = verifier.verify(assets, require_release_ready=True, acceptance=acceptance, publisher_policy="unsigned")
    assert result["release_ready"] is True
    assert result["publisher_policy"] == "unsigned"
    assert result["authenticode"] == "NotSigned"
    assert len(checked) == 1
    payload = json.loads(acceptance.read_text())
    payload["gates"]["native_admission"] = "pending"
    acceptance.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="gates"):
        verifier.verify(assets, require_release_ready=True, acceptance=acceptance, publisher_policy="unsigned")


@pytest.mark.parametrize("status", ["HashMismatch", "NotTrusted", "UnknownError", "Valid"])
def test_unsigned_policy_never_bypasses_invalid_or_unexpected_signature(build_request, monkeypatch, status):
    from scripts import verify_release_assets as verifier
    assets = candidate_assets(build_request)
    monkeypatch.setattr(verifier, "_inspect_signature", lambda setup: {"status": status})
    with pytest.raises(ValueError, match="unsigned"):
        verifier.verify(assets, require_release_ready=True, acceptance=release_acceptance(assets), publisher_policy="unsigned")


def test_unsigned_policy_requires_matching_recorded_acceptance(build_request):
    from scripts.verify_release_assets import verify
    assets = candidate_assets(build_request)
    with pytest.raises(ValueError, match="policy"):
        verify(assets, require_release_ready=True, acceptance=release_acceptance(assets, publisher_policy="signed"), publisher_policy="unsigned")


def test_default_signed_policy_does_not_silently_allow_unsigned(build_request):
    from scripts.verify_release_assets import verify
    assets = candidate_assets(build_request)
    with pytest.raises(ValueError, match="publisher"):
        verify(assets, require_release_ready=True, acceptance=release_acceptance(assets))


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


def test_runtime_is_filtered_directly_into_final_layout(tmp_path):
    archive = tmp_path / "runtime.tar.gz"
    keep = ("python.exe", "Lib/venv/scripts/nt/python.exe", "Lib/ensurepip/pip.whl",
            "tcl/tk8.6/license.terms", "LICENSE.txt")
    exclude = ("Lib/site-packages/untrusted.py", "Lib/__pycache__/cached.pyc",
               "Lib/cached.pyc", "Lib/nested/__pycache__/data.txt")
    with tarfile.open(archive, "w:gz") as target:
        for name in (*keep, *exclude):
            member = tarfile.TarInfo("python/" + name)
            member.size = len(name.encode())
            target.addfile(member, io.BytesIO(name.encode()))
    destination = tmp_path / "stage/runtime"

    module._extract_runtime(archive, destination)

    assert {path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()} == set(keep)
    for name in keep:
        assert (destination / name).read_bytes() == name.encode()


def test_excluded_runtime_member_is_still_validated_before_any_write(tmp_path):
    archive = tmp_path / "runtime.tar.gz"
    with tarfile.open(archive, "w:gz") as target:
        valid = tarfile.TarInfo("python/python.exe")
        valid.size = 4
        target.addfile(valid, io.BytesIO(b"safe"))
        hidden_link = tarfile.TarInfo("python/Lib/site-packages/hidden.py")
        hidden_link.type = tarfile.SYMTYPE
        hidden_link.linkname = "../../../user-file"
        target.addfile(hidden_link)
    destination = tmp_path / "stage/runtime"

    with pytest.raises(ValueError, match="unsafe runtime"):
        module._extract_runtime(archive, destination)
    assert not destination.exists()
