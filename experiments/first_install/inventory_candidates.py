"""Read-only A-stage native/notice inventory for the pinned candidate archives.

Does not execute candidate binaries or decide redistribution/signing admission.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import uuid
from zipfile import ZipFile

from experiments.first_install.fetch_candidates import INPUTS, require_safe_member


SIGNATURE_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$taskInput = Get-Content -LiteralPath $env:CLIPAI_INVENTORY_INPUT -Raw | ConvertFrom-Json
$taskSignatures = @(
    foreach ($taskFile in $taskInput) {
        $taskSignature = Get-AuthenticodeSignature -LiteralPath $taskFile.absolute
        [PSCustomObject]@{
            path = $taskFile.relative
            status = $taskSignature.Status.ToString()
            signer_subject = $(if ($taskSignature.SignerCertificate) { $taskSignature.SignerCertificate.Subject } else { $null })
        }
    }
)
ConvertTo-Json -InputObject $taskSignatures -Depth 4 -Compress
"""


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def notice_name(name: str) -> bool:
    basename = PurePosixPath(name).name.casefold()
    return any(basename == stem or basename.startswith(stem + ".")
               for stem in ("license", "licence", "copying", "notice", "copyright"))


def selected_records(archive: Path, component: str) -> tuple[list[dict], list[dict], list[dict]]:
    """Inventory the actual runtime-copy profile and the verifier-only profile.

    Read bytes from the admitted archive; site-packages is excluded by the
    existing runtime copier. Runtime import libraries/headers are not native
    executables. OpenSSH server/service scripts are not required by verification.
    """
    native, notices, wheel_notices = [], [], []

    def collect(name: str, content: bytes) -> None:
        require_safe_member(name)
        relative = PurePosixPath(name).relative_to(
            "python" if component == "runtime" else "OpenSSH-Win64"
        ).as_posix()
        if component == "runtime" and "site-packages" in PurePosixPath(relative).parts:
            return
        if component == "verifier" and relative not in {"ssh-keygen.exe", "libcrypto.dll", "LICENSE.txt", "NOTICE.txt"}:
            return
        identity = {"path": relative, "size": len(content), "sha256": digest(content)}
        if PurePosixPath(relative).suffix.casefold() in {".exe", ".dll", ".pyd"}:
            native.append(identity)
        if notice_name(relative):
            notices.append(identity)
        if relative.startswith("Lib/ensurepip/_bundled/") and relative.endswith(".whl"):
            with ZipFile(io.BytesIO(content)) as wheel:
                for member in wheel.infolist():
                    if notice_name(member.filename):
                        data = wheel.read(member)
                        wheel_notices.append({"wheel": relative, "path": member.filename,
                                              "size": len(data), "sha256": digest(data)})

    if component == "runtime":
        with tarfile.open(archive, "r:gz") as source:
            for member in source:
                if member.isfile():
                    stream = source.extractfile(member)
                    assert stream is not None
                    collect(member.name, stream.read())
    else:
        with ZipFile(archive) as source:
            for member in source.infolist():
                if not member.is_dir():
                    collect(member.filename, source.read(member))
    return sorted(native, key=lambda row: row["path"]), sorted(notices, key=lambda row: row["path"]), wheel_notices


def inventory(component: str, candidate_root: Path, output_root: Path) -> tuple[Path, dict]:
    selected = json.loads(INPUTS.read_text(encoding="utf-8"))[component]
    archive = candidate_root.resolve() / "download.archive"
    if archive.stat().st_size != selected["size"] or digest(archive.read_bytes()) != selected["sha256"]:
        raise ValueError("archive does not match the pinned input")
    root = candidate_root.resolve() / "unpacked" / ("python" if component == "runtime" else "OpenSSH-Win64")
    native, notices, wheel_notices = selected_records(archive, component)
    for row in [*native, *notices]:
        path = root.joinpath(*PurePosixPath(row["path"]).parts)
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            raise ValueError("candidate link refused")
        if path.stat().st_size != row["size"] or digest(path.read_bytes()) != row["sha256"]:
            raise ValueError("unpacked file differs from admitted archive")
    run_root = output_root.resolve() / f"inventory-{component}-{uuid.uuid4().hex}"
    run_root.mkdir(parents=True, exist_ok=False)
    task_input = run_root / "signature-input.json"
    task_input.write_text(json.dumps([
        {"relative": row["path"], "absolute": str(root.joinpath(*PurePosixPath(row["path"]).parts))}
        for row in native
    ]), encoding="utf-8")
    report = {
        "schema_version": 1, "probe_kind": "first-install-candidate-inventory",
        "created_at": datetime.now(timezone.utc).isoformat(), "component": component,
        "status": "failed", "archive_sha256": selected["sha256"],
        "selected_files_match_archive": True, "profile": "runtime_copy_excluding_site_packages" if component == "runtime" else "verifier_only",
        "native_files": native, "notice_files": notices, "bundled_wheel_notices": wheel_notices,
        "distribution_admission": "not_covered", "notice_component_mapping": "not_covered",
        "clean_vm_gate": "not_covered", "final_signed_asset": "not_covered",
    }
    try:
        shell = Path(os.environ["SYSTEMROOT"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        environment = {"SYSTEMROOT": os.environ["SYSTEMROOT"], "CLIPAI_INVENTORY_INPUT": str(task_input)}
        completed = subprocess.run(
            [str(shell), "-NoProfile", "-NonInteractive", "-EncodedCommand",
             base64.b64encode(SIGNATURE_SCRIPT.encode("utf-16-le")).decode("ascii")],
            env=environment, capture_output=True, text=True, timeout=180, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode:
            raise RuntimeError("native signature inventory failed")
        signatures = json.loads(completed.stdout)
        signatures = signatures if isinstance(signatures, list) else [signatures]
        by_path = {row["path"]: row for row in signatures}
        if len(by_path) != len(native) or set(by_path) != {row["path"] for row in native}:
            raise ValueError("signature inventory does not match selected files")
        for row in native:
            row["authenticode"] = by_path[row["path"]]["status"]
            row["signer_subject"] = by_path[row["path"]]["signer_subject"]
        report["authenticode_counts"] = dict(Counter(row["authenticode"] for row in native))
        report["status"] = "passed"
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        report["error_type"] = type(exc).__name__
    finally:
        task_input.unlink(missing_ok=True)
        report_path = run_root / "report.json"
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report_path, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component", required=True, choices=("runtime", "verifier"))
    parser.add_argument("--candidate-root", required=True, type=Path)
    parser.add_argument("--output-root", default=Path("artifacts/first-install-inventory"), type=Path)
    args = parser.parse_args()
    path, report = inventory(args.component, args.candidate_root, args.output_root)
    print(json.dumps({"status": report["status"], "report": str(path),
                      "native_count": len(report["native_files"]),
                      "authenticode_counts": report.get("authenticode_counts")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
