"""Create/read/remove a uniquely named native integration; never launch an app."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

from ClipAI.platform.installation_windows import WindowsInstallationIntegration, current_user_desktop


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    token = uuid.uuid4().hex
    work = repo / "artifacts/first-install-diagnostic" / f"shortcuts-{token}"
    root = work / "program"
    (root / "setup-engine").mkdir(parents=True)
    shutil.copy2(repo / "ClipAI/ui/assets/clipai.ico", root / "setup-engine/clipai.ico")
    product = f"ClipAI Verification {token}"
    integration = WindowsInstallationIntegration(
        product=product, registry_name=product, root=root, shared=work / "data", install_id=token,
        version="3.7.8", work_root=work, environment=dict(os.environ))
    desktop = current_user_desktop() / f"{product}.lnk"
    try:
        integration.create()
        paths = [integration.group / f"{product}.lnk", integration.group / "Uninstall.lnk", desktop]
        intent = work / "inspect.json"
        intent.write_text(json.dumps([str(p) for p in paths]), encoding="utf-8")
        code = r"""
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$paths = Get-Content -LiteralPath $env:CLIPAI_INSPECT -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($path in $paths) {
  $link = $shell.CreateShortcut($path)
  if ($link.IconLocation -ne ($env:CLIPAI_ICON + ',0')) { throw 'Incorrect icon' }
  if ($link.TargetPath -ne $env:CLIPAI_TARGET) { throw 'Incorrect target' }
}
"""
        result = subprocess.run([
            str(Path(os.environ["SYSTEMROOT"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"),
            "-NoProfile", "-NonInteractive", "-EncodedCommand",
            base64.b64encode(code.encode("utf-16-le")).decode()],
            env={**os.environ, "CLIPAI_INSPECT": str(intent), "CLIPAI_ICON": str(integration.icon),
                 "CLIPAI_TARGET": str(root / "runtime/pythonw.exe")},
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
        if result.returncode:
            raise RuntimeError("native_shortcut_inspection_failed")
        integration.validate_removal()
    finally:
        integration.remove()
    if desktop.exists() or integration.group.exists():
        raise RuntimeError("native_integration_cleanup_failed")
    proof = {"shortcut_count": 3, "clipai_icon_verified": True,
             "desktop_created": True, "owned_removal": "passed", "app_launched": False}
    (work / "proof.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"proof": str(work / "proof.json"), **proof}))


if __name__ == "__main__":
    main()
