from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from ClipAI.core.managed_update import transaction_id
from ClipAI.core.update_bundle import InstallManifest, ManifestFile, VerifiedManagedBundle
from ClipAI.core.update_ports import CandidateEnvironment
from ClipAI.platform.candidate_environment import CandidateBuildError
from ClipAI.platform.prepared_managed_payload import PreparedManagedPayloadMaterializer
from ClipAI.platform.update_bundle import BundleValidationError


class _Builder:
    def __init__(self, *, wrong_evidence: bool = False) -> None:
        self.requests = []
        self.wrong_evidence = wrong_evidence

    def build(self, request):
        self.requests.append(request)
        python = request.candidate_root / ".venv" / "Scripts" / "python.exe"
        python.parent.mkdir(parents=True)
        python.write_bytes(b"")
        return CandidateEnvironment(
            request.candidate_root,
            python.with_name("pythonw.exe") if self.wrong_evidence else python,
            request.candidate_root / request.entrypoint,
            request.expected_version,
        )


def _verified(tmp_path: Path) -> VerifiedManagedBundle:
    staging = tmp_path / "verified-bundle"
    files = {
        "payload/main.py": b"print('ready')\n",
        "requirements.lock": b"clipai==2.0\n",
        "wheelhouse/clipai.whl": b"wheel",
    }
    inventory = []
    for relative, content in files.items():
        path = staging / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        role = "payload" if relative.startswith("payload/") else "wheel" if relative.startswith("wheelhouse/") else "metadata"
        inventory.append(ManifestFile(relative, len(content), sha256(content).hexdigest(), role))
    manifest = InstallManifest(
        "2.0", "clipai-managed-v1", "payload/main.py", ">=3.11",
        sha256(files["requirements.lock"]).hexdigest(), tuple(inventory),
        "clipai.managed-update.manifest.v1", "release-key",
    )
    return VerifiedManagedBundle(staging, manifest)


def test_materializer_copies_verified_content_and_derives_build_identity(tmp_path: Path):
    verified = _verified(tmp_path)
    target = tmp_path / "install" / "launcher"
    base_python = tmp_path / "base-python.exe"
    builder = _Builder()

    candidate = PreparedManagedPayloadMaterializer(candidate_builder=builder).prepare(
        verified,
        target_root=target,
        transaction_id=transaction_id("tx-1"),
        base_python=base_python,
    )

    assert candidate == CandidateEnvironment(target, target / ".venv" / "Scripts" / "python.exe", target / "payload" / "main.py", "2.0")
    assert candidate.entrypoint.read_bytes() == b"print('ready')\n"
    assert len(builder.requests) == 1
    assert builder.requests[0].transaction_id == transaction_id("tx-1")
    assert builder.requests[0].base_python == base_python
    assert builder.requests[0].expected_version == verified.manifest.app_version
    assert builder.requests[0].entrypoint == verified.manifest.entrypoint


def test_materializer_rechecks_copied_inventory_before_build(tmp_path: Path):
    verified = _verified(tmp_path)
    (verified.staging_root / "payload" / "main.py").write_bytes(b"changed after verification")
    builder = _Builder()

    with pytest.raises(BundleValidationError):
        PreparedManagedPayloadMaterializer(candidate_builder=builder).prepare(
            verified,
            target_root=tmp_path / "candidate",
            transaction_id=transaction_id("tx-1"),
            base_python=tmp_path / "base-python.exe",
        )

    assert builder.requests == []


def test_materializer_rejects_builder_evidence_for_another_executable(tmp_path: Path):
    builder = _Builder(wrong_evidence=True)

    with pytest.raises(CandidateBuildError):
        PreparedManagedPayloadMaterializer(candidate_builder=builder).prepare(
            _verified(tmp_path),
            target_root=tmp_path / "candidate",
            transaction_id=transaction_id("tx-1"),
            base_python=tmp_path / "base-python.exe",
        )
