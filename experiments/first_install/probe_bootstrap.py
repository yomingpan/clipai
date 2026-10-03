"""Developer-host A2 spike: run the existing installer in an isolated source snapshot.

Synthetic app/test keys only. This is not a trusted release bootstrap or Setup.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid


def child(root: Path, tool: Path) -> dict:
    # -I excludes the repository, user site and PYTHONPATH. Admit only the
    # explicitly copied snapshot, not any development site-packages directory.
    sys.path.insert(0, str(root / "source"))
    report = {"status": "failed", "phase": "imports"}
    key = root / "fixture-key"
    try:
        from ClipAI.core.managed_update import transaction_id
        from ClipAI.core.managed_update_commands import InstallManagedCommand
        from ClipAI.core.update_signing import TEST_KEY_ID
        from ClipAI.platform.candidate_environment import OfflineCandidateEnvironmentBuilder
        from ClipAI.platform.managed_installer import FilesystemManagedInstaller
        from ClipAI.platform.managed_release_builder import ManagedReleaseBuilder, OpenSshManifestSigner
        from ClipAI.platform.update_signature import Ed25519ManifestVerifier
        import os

        environment = dict(os.environ)
        report["phase"] = "fixture_key"
        result = subprocess.run(
            [str(tool), "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
            env=environment, capture_output=True, timeout=20, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise RuntimeError("fixture key generation failed")
        public = key.with_suffix(".pub").read_text(encoding="ascii").strip()
        keyring = root / "fixture-keyring.json"
        keyring.write_text(json.dumps({
            "schema_version": 1, "keyring_kind": "clipai-managed-update-trusted-keys-v1",
            "keys": [{"key_id": TEST_KEY_ID, "algorithm": "ssh-ed25519",
                      "public_key": public, "key_kind": "test_fixture"}],
        }), encoding="utf-8")
        report["phase"] = "signed_bundle"
        fixture = root / "fixture"
        bundle = ManagedReleaseBuilder(OpenSshManifestSigner(
            ssh_keygen=tool, private_key=key, work_root=root / "sign-work",
            environment=environment,
        )).build(
            payload_root=fixture / "payload", wheelhouse_root=fixture / "wheelhouse",
            requirements_lock=fixture / "requirements.lock", output_path=root / "bundle.zip",
            app_version="0.0.0", entrypoint="payload/main.py", python_requires=">=3.12,<3.13",
            key_id=TEST_KEY_ID,
        )
        report["phase"] = "existing_install_engine"
        install = root / "安裝 中文 空格"
        shared = root / "資料 中文 空格"
        FilesystemManagedInstaller(
            manifest_verifier=Ed25519ManifestVerifier(
                ssh_keygen=tool, trusted_keys={TEST_KEY_ID: public},
                work_root=root / "verify-work", environment=environment, allow_test_keys=True,
            ),
            candidate_builder=OfflineCandidateEnvironmentBuilder(environment=environment),
            trusted_keyring_path=keyring,
        ).install(InstallManagedCommand(
            shared_root=shared, install_root=install, transaction_id=transaction_id(uuid.uuid4().hex),
            expected_version="0.0.0", bundle_path=bundle.bundle_path,
            bundle_size=bundle.bundle_size, bundle_sha256=bundle.bundle_sha256,
            manifest_sha256=bundle.manifest_sha256, key_id=TEST_KEY_ID,
            managed_install_id="synthetic-bootstrap-probe", launcher_version="0.0.0",
            base_python=Path(sys.executable),
        ))
        report["phase"] = "installed_identity"
        state = json.loads((install / "install-state.json").read_text(encoding="utf-8"))
        marker = json.loads((install / "managed-install.json").read_text(encoding="utf-8"))
        assert state["current_version"] == "0.0.0" and state["revision"] == 0
        assert marker["managed_install_id"] == "synthetic-bootstrap-probe"
        assert (install / "launcher" / "managed-update-trusted-keys.json").is_file()
        report.update(status="passed", phase="complete", version_and_launcher_built=True,
                      marker_and_state_verified=True)
        # Report dependency names, never environment values or full source paths.
        report["external_python_imports"] = sorted({
            name.split(".")[0] for name in sys.modules
            if name.split(".")[0] not in sys.stdlib_module_names
            and name.split(".")[0] not in {"ClipAI", "__main__"}
            and getattr(sys.modules[name], "__file__", None)
        })
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        if isinstance(exc, ModuleNotFoundError):
            report["missing_module"] = exc.name
    finally:
        key.unlink(missing_ok=True)
        key.with_suffix(".pub").unlink(missing_ok=True)
        report["fixture_private_key_removed"] = not key.exists()
    return report


def probe(runtime: Path, tools: Path, output: Path) -> tuple[Path, dict]:
    from experiments.first_install.probe_runtime import copy_runtime, fixture_candidate, isolated_environment
    import packaging

    runtime, tools, output = runtime.resolve(), tools.resolve(), output.resolve()
    for source in (runtime, tools):
        if source == output or source.is_relative_to(output) or output.is_relative_to(source):
            raise ValueError("input and output roots must be disjoint")
    if not (tools / "ssh-keygen.exe").is_file():
        raise ValueError("supply trusted unpacked verifier tools")
    root = output / f"bootstrap-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    report = {
        "schema_version": 1, "probe_kind": "first-install-local-bootstrap",
        "created_at": datetime.now(timezone.utc).isoformat(), "status": "failed",
        "synthetic_payload": True, "test_key_only": True, "empty_child_path": True,
        "bootstrap_source": "development_snapshot", "packaging_source": "development_snapshot",
        "clean_vm_gate": "not_covered", "trusted_release_bootstrap": "not_covered",
        "full_app_dependencies": "not_covered", "update_uninstall": "not_covered",
        "signature_and_license_admission": "not_covered",
    }
    started = time.perf_counter()
    try:
        copy_runtime(runtime, root / "runtime")
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
        repo = Path(__file__).resolve().parents[2]
        shutil.copytree(repo / "ClipAI", root / "source" / "ClipAI", ignore=ignore)
        shutil.copy2(repo / "main.py", root / "source" / "main.py")
        shutil.copytree(tools, root / "tools", ignore=ignore)
        fixture_candidate(root / "fixture")
        runner = root / "runner.py"
        shutil.copy2(Path(__file__), runner)
        environment = isolated_environment(root)
        python = root / "runtime" / "python.exe"

        def run(arguments):
            return subprocess.run([str(python), "-I", *arguments], env=environment,
                                  cwd=root, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=180, check=False,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

        baseline = run([str(runner), "--child", str(root)])
        report["without_packaging"] = json.loads(baseline.stdout)
        if report["without_packaging"].get("missing_module") != "packaging":
            raise RuntimeError("unexpected baseline dependency")
        shutil.copytree(Path(packaging.__file__).parent, root / "source" / "packaging", ignore=ignore)
        inventory = sorted((root / "source").rglob("*.py"))
        digest = hashlib.sha256()
        for path in inventory:
            digest.update(path.relative_to(root / "source").as_posix().encode())
            digest.update(b"\0" + path.read_bytes())
        report["source_snapshot_sha256"] = digest.hexdigest()
        report["packaging_version"] = packaging.__version__
        # Import-only probe must never start the desktop runtime.
        entry = run(["-c", "import sys;sys.path.insert(0,sys.argv[1]);\ntry: import main\nexcept ModuleNotFoundError as e: print(e.name)", str(root / "source")])
        report["existing_main_missing_module"] = entry.stdout.strip()
        report["existing_main_import_exit_code"] = entry.returncode
        completed = run([str(runner), "--child", str(root)])
        report["engine"] = json.loads(completed.stdout)
        if completed.returncode or report["engine"]["status"] != "passed":
            raise RuntimeError("isolated installer failed")
        report["status"] = "passed"
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        report["error_type"] = type(exc).__name__
    finally:
        # Also remove these exact operation-owned files if the child timed out.
        (root / "fixture-key").unlink(missing_ok=True)
        (root / "fixture-key.pub").unlink(missing_ok=True)
        report["fixture_private_key_removed"] = not (root / "fixture-key").exists()
    report["elapsed_sec"] = round(time.perf_counter() - started, 3)
    destination = root / "report.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return destination, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", type=Path)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--tools-root", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/first-install-bootstrap"))
    args = parser.parse_args()
    if args.child:
        result = child(args.child, args.child / "tools" / "ssh-keygen.exe")
        print(json.dumps(result))
        return 0 if result["status"] == "passed" else 1
    if args.runtime_root is None or args.tools_root is None:
        parser.error("--runtime-root and --tools-root are required")
    path, result = probe(args.runtime_root, args.tools_root, args.output_root)
    print(json.dumps({"status": result["status"], "report": str(path)}))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
