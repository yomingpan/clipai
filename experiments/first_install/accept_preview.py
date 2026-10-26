"""Bounded local acceptance. Mutates only the explicitly selected product.

Run on a Windows developer host, never claim clean-VM or public-release proof.
Existing roots/registration are rejected before starting. Formal ClipAI also
requires an absent shared root; user data must not become test data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
import winreg


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setup", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--product", choices=("ClipAI Preview", "ClipAI Candidate", "ClipAI"), default="ClipAI Preview")
    parser.add_argument("--version", default="3.7.8")
    args = parser.parse_args()
    setup = args.setup.resolve(strict=True)
    root = (Path(os.environ["LOCALAPPDATA"]) / "Programs" / args.product).resolve()
    shared = (Path(os.environ["LOCALAPPDATA"]) / args.product).resolve()
    product_id = "ClipAI.Desktop" if args.product == "ClipAI" else "ClipAI.LocalAcceptance." + ("Candidate" if args.product == "ClipAI Candidate" else "Preview")
    registry = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" + product_id
    if args.product in ("ClipAI Candidate", "ClipAI") and shared.exists():
        raise RuntimeError("Existing product data must not be modified by acceptance")
    if root.exists():
        raise RuntimeError("Existing Preview installation must not be modified by acceptance")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry):
            raise RuntimeError("Existing Preview registration")
    except FileNotFoundError:
        pass
    args.output.mkdir(parents=True, exist_ok=False)
    env = {**os.environ, "PATH": ""}
    results: dict[str, object] = {"setup_sha256": hashlib.sha256(setup.read_bytes()).hexdigest(),
                                "install_root": str(root), "shared_root": str(shared),
                                "clean_vm": False, "path_empty": True,
                                "preexisting_shared_data_retained": shared.exists(), "steps": []}

    def record(name: str, **values: object) -> None:
        results["steps"].append({"name": name, **values})
        (args.output / "acceptance.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(name, values, flush=True)

    def run_setup(name: str, *, remove: bool = False, success: bool = True) -> None:
        started = time.monotonic()
        command = [str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                   f"/LOG={args.output.resolve() / (name + '.log')}"]
        if remove:
            command.append("/REMOVE=1")
        result = subprocess.run(command, env=env, timeout=600, check=False)
        record(name, exit_code=result.returncode, elapsed_seconds=round(time.monotonic() - started, 2))
        if (result.returncode == 0) != success:
            log = args.output / (name + ".log")
            if log.is_file():
                # Only the explicitly requested Setup log from this owned test.
                content = log.read_bytes()
                encoding = "utf-16" if content.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
                print(content.decode(encoding, errors="replace")[-12000:], flush=True)
            raise RuntimeError(f"Unexpected Setup settlement: {name}")

    def check() -> Path:
        command = [str(root / "runtime/python.exe"), "-I", str(root / "setup-engine/entry.py"),
                   "selfcheck", "--quiet", "--install-root", str(root), "--shared-root", str(shared)]
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError("Installed identity selfcheck failed")
        python = root / "versions" / args.version / ".venv/Scripts/python.exe"
        result = subprocess.run([str(python), "-I", "-c",
            "import main, tkinter, clr; r=tkinter.Tk(); r.withdraw(); r.update(); r.destroy(); print('FULL_APP_IMPORTS_AND_TK_PASSED')"],
            env=env, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError("Full desktop dependency loading failed")
        result = subprocess.run([str(python), "-I", str(Path(__file__).with_name("desktop_startup_probe.py").resolve()),
            "--install-root", str(root), "--shared-root", str(shared), "--version", args.version],
            env=env, capture_output=True, text=True, timeout=60)
        (args.output / "desktop-startup.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode not in (0, 2):
            raise RuntimeError("Full desktop runtime startup failed; see desktop-startup.txt")
        record("desktop_runtime_startup", passed=result.returncode == 0,
               skipped_user_app_running=result.returncode == 2)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry) as key:
            assert winreg.QueryValueEx(key, "InstallLocation")[0] == str(root)
        group = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs" / args.product
        assert (group / (args.product + ".lnk")).is_file() and (group / "Uninstall.lnk").is_file()
        record("installed_selfcheck_and_native_integration", passed=True,
               installed_logical_bytes=sum(p.stat().st_size for p in root.rglob("*") if p.is_file()))
        return python

    run_setup("install")
    python = check()
    marker = (root / "managed-install.json").read_bytes()
    run_setup("duplicate_install_rejected", success=False)
    assert (root / "managed-install.json").read_bytes() == marker
    # This child is created by this test; no user process is terminated.
    child = subprocess.Popen([str(python), "-I", "-c", "import time; time.sleep(45)"], env=env)
    try:
        run_setup("active_private_process_removal_rejected", remove=True, success=False)
        assert (root / "managed-install.json").read_bytes() == marker
    finally:
        child.terminate()
        child.wait(timeout=10)
    sentinel = shared / f"acceptance-retained-{uuid.uuid4().hex}.txt"
    content = b"synthetic acceptance data; never an API credential"
    sentinel.write_bytes(content)
    # Test maintenance from the same Setup when the application venv is broken.
    if not python.resolve().is_relative_to(root):
        raise RuntimeError("Unexpected executable location")
    python.rename(python.with_suffix(".broken"))
    run_setup("remove_with_broken_app_venv", remove=True)
    assert not root.exists() and sentinel.read_bytes() == content
    run_setup("reinstall_retaining_data")
    check()
    assert sentinel.read_bytes() == content
    record("retained_data_reinstall", passed=True)
    run_setup("final_remove", remove=True)
    assert not root.exists() and sentinel.read_bytes() == content
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry):
            raise AssertionError("Registration remains after successful removal")
    except FileNotFoundError:
        pass
    sentinel.unlink()
    record("final_settlement", passed=True, test_sentinel_removed=True,
           shared_transaction_evidence_retained=True, live_desktop_action="manual_acceptance_pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
