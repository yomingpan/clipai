"""Package an admitted managed bundle; never resolve, build or sign app content."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
import fnmatch
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
from zipfile import ZipFile

from packaging.utils import parse_wheel_filename
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from ClipAI.core.update_bundle import BundleAdmissionRequest
from ClipAI.platform.managed_update_fs import (
    atomic_write_json, extract_prefixed_zip, file_sha256, regular_file_inventory,
)
from ClipAI.platform.trusted_release_keys import load_trusted_release_keyring
from ClipAI.platform.update_catalog import parse_catalog
from ClipAI.platform.update_signature import Ed25519ManifestVerifier
from ClipAI.platform.verified_managed_bundle import VerifiedManagedBundleStager


@dataclass(frozen=True)
class SetupBuildRequest:
    bundle: Path
    catalog: Path
    keyring: Path
    inputs: Path
    runtime_archive: Path
    compiler: Path
    wizard: Path
    output_root: Path
    tag: str
    source_commit: str
    technical_candidate: bool = False


def _identity(path: Path) -> dict[str, object]:
    return {"size": path.stat().st_size, "sha256": file_sha256(path)}


def _require_identity(path: Path, expected: dict) -> None:
    if _identity(path) != {k: expected[k] for k in ("size", "sha256")}:
        raise ValueError("pinned input identity mismatch")


def _extract_runtime(archive: Path, root: Path) -> None:
    # Validate the entire fixed archive before filtering, including excluded
    # members. Write the runtime once, directly into its final stage location.
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        seen: set[str] = set()
        for member in members:
            path = PurePosixPath(member.name)
            if (not member.name.startswith("python/") or path.is_absolute()
                    or ".." in path.parts or "\\" in member.name or ":" in member.name
                    or not (member.isfile() or member.isdir())
                    or member.name.casefold() in seen):
                raise ValueError("unsafe runtime archive")
            seen.add(member.name.casefold())
        if sum(m.size for m in members) > 512 * 1024 * 1024:
            raise ValueError("runtime archive exceeds size limit")
        # Compatible with the project's Python 3.10 tooling as well as 3.12.
        for member in members:
            parts = PurePosixPath(member.name).parts[1:]
            if any(fnmatch.fnmatch(part, pattern) for part in parts
                   for pattern in ("site-packages", "__pycache__", "*.pyc")):
                continue
            target = root.joinpath(*parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as stream, target.open("xb") as output:
                    shutil.copyfileobj(stream, output)


class SetupReleaseBuilder:
    """Fixed-input Windows packaging adapter around the existing stager."""

    def __init__(self, *, environment: Mapping[str, str]) -> None:
        self._environment = _environment(environment)

    def build(self, request: SetupBuildRequest) -> Path:
        inputs = json.loads(request.inputs.read_text(encoding="utf-8"))
        if inputs["platform"] != "windows-x64" or inputs["python_abi"] != "cp312":
            raise ValueError("unsupported bootstrap platform/ABI")
        if not request.technical_candidate and inputs["distribution_admission"] != "approved":
            raise ValueError("bootstrap distribution admission is pending")
        if inputs["verifier"] != {"profile": "cryptography-ed25519-sshsig-v1", "version": "50.0.2"}:
            raise ValueError("unsupported manifest verifier input")
        if re.fullmatch(r"[0-9a-f]{40}", request.source_commit) is None:
            raise ValueError("source commit must be a full SHA")
        catalog = parse_catalog(request.catalog.read_bytes())
        if len(catalog.releases) != 1:
            raise ValueError("one fixed publication release is required")
        release = catalog.releases[0]
        if request.tag != "v" + release.version or Version(release.version).is_devrelease:
            raise ValueError("tag and publication version must match")
        expected_url = (f"https://github.com/yomingpan/clipai/releases/download/{request.tag}/"
                        f"clipai-managed-{release.version}.zip")
        if release.bundle_url != expected_url:
            raise ValueError("catalog must reference the immutable tag asset")
        keys = load_trusted_release_keyring(request.keyring).verification_keys()
        if not request.technical_candidate and release.key_id.startswith(("local-", "test-")):
            raise ValueError("local candidate keys cannot authorize official packaging")
        for path, component in ((request.runtime_archive, "runtime"),):
            _require_identity(path, inputs[component])
        if request.compiler.name.lower() != "iscc.exe":
            raise ValueError("the pinned Inno compiler is required")
        compiler_files = inputs["compiler"]["files"]
        if not compiler_files or "ISCC.exe" not in compiler_files:
            raise ValueError("compiler component inventory is required")
        for name, identity in compiler_files.items():
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
                raise ValueError("unsafe compiler input path")
            _require_identity(request.compiler.parent.joinpath(*relative.parts), identity)
        additional_notices = {}
        for name, identity in inputs.get("additional_notices", {}).items():
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
                raise ValueError("unsafe notice input path")
            source = request.inputs.parent.joinpath("third-party-notices", *relative.parts)
            _require_identity(source, identity)
            additional_notices[name] = source
        root = request.output_root.resolve()
        root.mkdir(parents=True, exist_ok=False)
        frozen_wizard = root / "setup.iss"
        shutil.copyfile(request.wizard, frozen_wizard)
        frozen_entry = root / "setup-entry.py"
        shutil.copyfile(request.wizard.with_name("entry.py"), frozen_entry)
        adapter_identity = _identity(Path(__file__))
        stage = root / "stage"
        stage.mkdir()
        _extract_runtime(request.runtime_archive, stage / "runtime")
        environment = self._environment
        transaction = root / "admission"
        transaction.mkdir()
        admitted_archive = transaction / "bundle.zip"
        shutil.copyfile(request.bundle, admitted_archive)
        verified = VerifiedManagedBundleStager(manifest_verifier=Ed25519ManifestVerifier(trusted_keys=keys)).stage(BundleAdmissionRequest(transaction, admitted_archive, release.bundle_size,
                                        release.bundle_sha256, release.manifest_sha256,
                                        release.version, release.key_id))
        if (str(Version(release.version)) != release.version
                or Version(release.minimum_launcher_version) > Version(release.version)
                or not SpecifierSet(verified.manifest.python_requires).contains(inputs["runtime"]["runtime_version"])):
            raise ValueError("bootstrap runtime/launcher is incompatible with release")
        wheelhouse = verified.staging_root / "wheelhouse"
        wheels = list(wheelhouse.glob("*.whl"))
        selected = {}
        for wheel in wheels:
            name, version, _, _ = parse_wheel_filename(wheel.name)
            if name in ("clipai", "packaging", "cryptography", "cffi", "pycparser"):
                if (name in selected or (name == "clipai" and str(version) != release.version)
                        or (name == "cryptography" and str(version) != inputs["verifier"]["version"])):
                    raise ValueError("ambiguous or mismatched bootstrap wheels")
                selected[name] = wheel
        if set(selected) != {"clipai", "packaging", "cryptography", "cffi", "pycparser"}:
            raise ValueError("admitted app, packaging and verifier dependency wheels are required")
        engine = stage / "setup-engine"
        engine.mkdir()
        for wheel in selected.values():
            extract_prefixed_zip(wheel, engine, prefix="", maximum_uncompressed_size=64 * 1024 * 1024)
        for name, source in additional_notices.items():
            target = engine / "third-party-notices" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        shutil.copyfile(engine / "ClipAI/ui/assets/clipai.ico", engine / "clipai.ico")
        shutil.copyfile(request.keyring, engine / "managed-update-trusted-keys.json")
        shutil.copyfile(admitted_archive, stage / "bundle.zip")
        _require_identity(stage / "bundle.zip", {"size": release.bundle_size, "sha256": release.bundle_sha256})
        product = "ClipAI Candidate" if request.technical_candidate else "ClipAI"
        product_id = "ClipAI.LocalAcceptance.Candidate" if request.technical_candidate else "ClipAI.Desktop"
        metadata = {"schema_version": 1, "kind": "clipai-setup-candidate", "product": product,
                    "registry_name": product_id, "version": release.version, "key_id": release.key_id,
                    "official_release": False, "release": {"bundle_sha256": release.bundle_sha256,
                    "bundle_size": release.bundle_size, "manifest_sha256": release.manifest_sha256}}
        atomic_write_json(engine / "candidate.json", metadata)
        shutil.copyfile(frozen_entry, engine / "entry.py")
        # Ship component notices and an exact inventory, while retaining the
        # separate admission gate for completeness/license review.
        notices = root / "output/notices"
        notices.mkdir(parents=True)
        for component, component_root in (("runtime", stage / "runtime"), ("bootstrap", engine)):
            for name in regular_file_inventory(component_root):
                if _notice_name(name):
                    target = notices / component / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(component_root / name, target)
        for wheel in wheels:
            with ZipFile(wheel) as archive:
                for name in archive.namelist():
                    if _notice_name(name) and not name.endswith("/"):
                        path = PurePosixPath(name)
                        if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
                            raise ValueError("unsafe wheel notice path")
                        target = notices / "wheels" / wheel.name / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(archive.read(name))
        shutil.copyfile(request.compiler.parent / "license.txt", notices / "inno-license.txt")
        output_name = f"ClipAI-{'Candidate-' if request.technical_candidate else ''}Setup-{release.version}-windows-x64"
        welcome = ("Unsigned technical candidate. Isolated installation; public release gates are pending."
                   if request.technical_candidate else "Includes offline Python and dependencies. Cloud AI and updates require internet.")
        command = [str(request.compiler.resolve()), f"/DStageRoot={stage}", f"/DOutputRoot={root / 'output'}",
                   f"/DAppVersion={release.version}", f"/DProductName={product}", f"/DProductId={product_id}",
                   f"/DBundleSha256={release.bundle_sha256}", f"/DKeyringSha256={file_sha256(request.keyring)}",
                   f"/DOutputName={output_name}", f"/DWelcomeText={welcome}", str(frozen_wizard)]
        result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=300,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            (root / "compiler-errors.txt").write_text((result.stdout + result.stderr)[-16000:], encoding="utf-8")
            raise RuntimeError("Setup compilation failed")
        setup = root / "output" / (output_name + ".exe")
        provenance = {"schema_version": 1, "kind": "clipai-setup-provenance-v1",
                      "tag": request.tag, "source_commit": request.source_commit,
                      "app_version": release.version, "launcher_version": release.version,
                      "technical_candidate": request.technical_candidate, "release_ready": False,
                      "authenticode": "unsigned", "distribution_admission": inputs["distribution_admission"],
                      "inputs": inputs, "catalog": _identity(request.catalog), "keyring": _identity(request.keyring),
                      "bundle": _identity(stage / "bundle.zip"), "manifest_sha256": release.manifest_sha256,
                      "requirements_lock": _identity(verified.staging_root / "requirements.lock"),
                      "wheels": {w.name: _identity(w) for w in wheels}, "setup": {"filename": setup.name, **_identity(setup)},
                      "wizard": _identity(frozen_wizard),
                      "packaging_adapter": adapter_identity,
                      "source_binding": "caller_verified_git_content", "tag_verified": not request.technical_candidate,
                      "stage_files": {n: _identity(stage / n) for n in regular_file_inventory(stage)}}
        atomic_write_json(root / "output/provenance.json", provenance)
        shutil.copyfile(request.catalog, root / "output/catalog.json")
        shutil.copyfile(request.keyring, root / "output/managed-update-trusted-keys.json")
        shutil.copyfile(stage / "bundle.zip", root / "output" / f"clipai-managed-{release.version}.zip")
        return setup


def _notice_name(name: str) -> bool:
    path = PurePosixPath(name.lower())
    return any(part in ("licenses", "licences", "notices") for part in path.parts) or any(token in path.name for token in
               ("license", "licence", "notice", "copying", "copyright", "lgpl", "gpl", "terms"))


def _environment(environment: Mapping[str, str]) -> dict[str, str]:
    result = {k: v for k, v in environment.items() if k.upper() in {
        "SYSTEMROOT", "WINDIR", "COMSPEC", "PROGRAMDATA", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"}}
    result.update(PATH="", PYTHONDONTWRITEBYTECODE="1", PIP_NO_INDEX="1")
    return result
