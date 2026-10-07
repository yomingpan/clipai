"""A2 local runtime spike; never evidence of a clean-VM or real ClipAI install.

Run from the repository with its development environment:
  .venv/Scripts/python.exe -m experiments.first_install.probe_runtime \
      --runtime-root <trusted-unpacked-python-root>

The host imports the existing candidate builder. Only the copied interpreter
runs the child probes. No downloads, registry mutation, or recursive deletion.
"""

from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid
from zipfile import ZipFile, ZIP_DEFLATED

from ClipAI.core.managed_update import transaction_id
from ClipAI.core.update_ports import CandidateBuildRequest
from ClipAI.platform.candidate_environment import OfflineCandidateEnvironmentBuilder
from ClipAI.platform.managed_update_fs import atomic_write_json


VERSION = "0.0.0"
PROBE_CODE = """
import ctypes, importlib.metadata, importlib.util, json, sqlite3, ssl, struct
import sys, sysconfig, tkinter
print(json.dumps({
    'version': sys.version.split()[0],
    'bits': struct.calcsize('P') * 8,
    'platform': sysconfig.get_platform(),
    'base_prefix': sys.base_prefix,
    'executable': sys.executable,
    'tcl': tkinter.Tcl().eval('info patchlevel'),
    'openssl': ssl.OPENSSL_VERSION,
    'foreign_packaging_visible': importlib.util.find_spec('packaging') is not None,
}))
"""


def isolated_environment(work_root: Path) -> dict[str, str]:
    """Keep OS essentials; exclude credentials, Python/PIP/Tcl and user PATH."""
    result = {
        key: value for key, value in os.environ.items()
        # Portable Win32-OpenSSH exits 255 before diagnostics if PROGRAMDATA is
        # absent. Preserve that OS location without exposing user credentials.
        if key.upper() in {"SYSTEMROOT", "WINDIR", "COMSPEC", "PROGRAMDATA"}
    }
    temporary = work_root / "temp"
    temporary.mkdir()
    result.update({
        "PATH": "", "TEMP": str(temporary), "TMP": str(temporary),
        "PYTHONNOUSERSITE": "1", "PIP_CONFIG_FILE": os.devnull,
        "PIP_NO_INDEX": "1", "PIP_NO_INPUT": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    })
    return result


def copy_runtime(source: Path, target: Path) -> None:
    """Copy a base distribution, never a venv or its installed packages."""
    source, target = source.resolve(), target.resolve()
    if source == target or target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError("runtime source and probe target must be disjoint")
    if not (source / "python.exe").is_file() or (source / "pyvenv.cfg").exists():
        raise ValueError("supply a trusted unpacked Windows base runtime, not a venv")
    ignored = {"site-packages", "__pycache__"}
    for root, directories, files in os.walk(source, followlinks=False):
        directories[:] = [name for name in directories if name not in ignored]
        for name in [*directories, *files]:
            path = Path(root) / name
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise ValueError("runtime contains a link or junction; copying refused")
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(*ignored, "*.pyc"))


def fixture_candidate(root: Path) -> None:
    """A tiny synthetic distribution named clipai for the existing builder probe.

    It does not contain the ClipAI app and cannot prove app/package readiness.
    """
    wheelhouse = root / "wheelhouse"
    wheelhouse.mkdir(parents=True)
    dist = f"clipai-{VERSION}.dist-info"
    contents = {
        "clipai_runtime_probe/__init__.py": b"SYNTHETIC_RUNTIME_PROBE = True\n",
        f"{dist}/METADATA": (
            f"Metadata-Version: 2.1\nName: clipai\nVersion: {VERSION}\n"
            "Requires-Python: >=3.12,<3.13\n\nSynthetic runtime probe only.\n"
        ).encode(),
        f"{dist}/WHEEL": (
            "Wheel-Version: 1.0\nGenerator: clipai-runtime-spike\n"
            "Root-Is-Purelib: true\nTag: py3-none-any\n"
        ).encode(),
    }
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name, data in contents.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
        writer.writerow([name, f"sha256={digest}", len(data)])
    writer.writerow([f"{dist}/RECORD", "", ""])
    contents[f"{dist}/RECORD"] = record.getvalue().encode()
    wheel = wheelhouse / f"clipai-{VERSION}-py3-none-any.whl"
    with ZipFile(wheel, "x", compression=ZIP_DEFLATED) as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    (root / "requirements.lock").write_text(
        f"clipai=={VERSION} --hash=sha256:{digest}\n", encoding="ascii"
    )
    payload = root / "payload"
    payload.mkdir()
    (payload / "main.py").write_text(
        "from clipai_runtime_probe import SYNTHETIC_RUNTIME_PROBE\n"
        "assert SYNTHETIC_RUNTIME_PROBE\n" + PROBE_CODE, encoding="utf-8"
    )


def probe(runtime_root: Path, output_root: Path) -> tuple[Path, dict]:
    run_id = f"runtime-{uuid.uuid4().hex}"
    output_root = output_root.resolve()
    source = runtime_root.resolve()
    if output_root == source or output_root.is_relative_to(source) or source.is_relative_to(output_root):
        raise ValueError("runtime source and output root must be disjoint")
    # Every run reserves a fresh scratch directory; no retry ever removes old work.
    run_root = output_root / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    report = {
        "schema_version": 1, "probe_kind": "first-install-local-runtime",
        "run_id": run_id, "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "failed", "source_kind": "caller_supplied_development_runtime",
        "synthetic_payload": True, "content_recorded": False,
        "clean_vm_gate": "not_covered", "reboot": "not_covered",
        "os_network_isolation": "not_covered", "pip_network_policy": "no_index",
        "trusted_bootstrap": "not_covered", "managed_install_update_uninstall": "not_covered",
        "full_app_dependencies": "not_covered", "tk_window": "not_covered",
        "signature_and_license_admission": "not_covered", "steps": [],
    }
    report_path = run_root / "report.json"
    started = time.perf_counter()

    def run(command, environment, timeout_sec):
        step = {"index": len(report["steps"]), "status": "failed"}
        report["steps"].append(step)
        tick = time.perf_counter()
        try:
            result = subprocess.run(
                list(command), cwd=run_root, env=dict(environment),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=timeout_sec, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            step.update(exit_code=result.returncode,
                        status="passed" if result.returncode == 0 else "failed")
            # Deliberately do not persist raw child stderr or environment values.
            return result
        finally:
            step["elapsed_sec"] = round(time.perf_counter() - tick, 3)

    try:
        environment = isolated_environment(run_root)
        runtime = run_root / "固定工具 中文" / "python"
        report["phase"] = "copy_base_runtime"
        copy_runtime(source, runtime)
        python = runtime / "python.exe"
        report["runtime_executable_sha256"] = hashlib.sha256(python.read_bytes()).hexdigest()
        report["runtime_bytes"] = sum(path.stat().st_size for path in runtime.rglob("*") if path.is_file())
        report["phase"] = "base_runtime_probe"
        base = run([str(python), "-I", "-c", PROBE_CODE], environment, 30)
        if base.returncode:
            raise RuntimeError("base runtime probe failed")
        identity = json.loads(base.stdout)
        if (identity["bits"], identity["platform"]) != (64, "win-amd64"):
            raise ValueError("probe requires Windows x64")
        if identity["version"].split(".")[:2] != ["3", "12"]:
            raise ValueError("probe requires the planned Python 3.12 runtime")
        if Path(identity["base_prefix"]).resolve() != runtime or identity["foreign_packaging_visible"]:
            raise ValueError("copied base runtime is not isolated")
        report["runtime_identity"] = {key: identity[key] for key in ("version", "bits", "platform", "tcl", "openssl")}
        candidate_root = run_root / "版本 中文 空格" / "candidate"
        fixture_candidate(candidate_root)
        report["phase"] = "existing_offline_candidate_builder"
        candidate = OfflineCandidateEnvironmentBuilder(environment=environment, runner=run).build(
            CandidateBuildRequest(transaction_id(run_id), candidate_root, python, VERSION, "payload/main.py")
        )
        report["phase"] = "fresh_candidate_process"
        launched = run([str(candidate.python), "-I", str(candidate.entrypoint)], environment, 30)
        if launched.returncode:
            raise RuntimeError("candidate runtime probe failed")
        actual = json.loads(launched.stdout)
        if Path(actual["base_prefix"]).resolve() != runtime or Path(actual["executable"]).resolve() != candidate.python:
            raise ValueError("candidate uses an unexpected interpreter")
        if actual["foreign_packaging_visible"]:
            raise ValueError("candidate sees development site-packages")
        report.update(status="passed", phase="complete", empty_child_path=True)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        report["error_type"] = type(exc).__name__
    finally:
        report["elapsed_sec"] = round(time.perf_counter() - started, 3)
        atomic_write_json(report_path, report)
    return report_path, report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/first-install-runtime"))
    args = parser.parse_args(argv)
    if os.name != "nt":
        parser.error("this probe targets Windows x64")
    report_path, report = probe(args.runtime_root, args.output_root)
    print(json.dumps({"status": report["status"], "report": str(report_path), "clean_vm_gate": "not_covered"}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
