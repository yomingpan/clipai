"""Temporary runner diagnosis; only workspace shortcuts, no registry mutations."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ClipAI.platform.installation_windows import WindowsInstallationIntegration, install_process_containment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('baseline', 'utility-first', 'native-module-path', 'no-autoload'), required=True)
    args = parser.parse_args()
    root = Path.cwd() / 'release' / ('shortcut-probe-' + args.mode)
    root.mkdir(parents=True, exist_ok=False)
    (root / 'runtime').mkdir()
    (root / 'setup-engine').mkdir()
    shutil.copy2(Path(sys.base_prefix) / 'pythonw.exe', root / 'runtime/pythonw.exe')
    shutil.copy2(Path(__file__).resolve().parents[2] / 'ClipAI/ui/assets/clipai.ico', root / 'setup-engine/clipai.ico')
    environment = {key.upper(): value for key, value in os.environ.items()
                   if key.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PROGRAMDATA',
                                     'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP'}}
    environment['PATH'] = ''
    job = install_process_containment()
    assert job
    native = WindowsInstallationIntegration(product='ClipAI Probe', registry_name='Probe',
        root=root, shared=root, install_id='probe', version='3.7.18', work_root=root,
        environment=environment)
    original = subprocess.run

    def observed(command, **kwargs):
        code = base64.b64decode(command[-1]).decode('utf-16-le')
        if args.mode == 'no-autoload':
            code = code.replace("$taskIntent = Get-Content -LiteralPath $env:CLIPAI_SHORTCUT_INTENT -Raw -Encoding UTF8 | ConvertFrom-Json",
                "$taskAssembly = [Reflection.Assembly]::Load('System.Web.Extensions, Version=4.0.0.0, Culture=neutral, PublicKeyToken=31bf3856ad364e35')\n"
                "$taskIntent = [System.Web.Script.Serialization.JavaScriptSerializer]::new().DeserializeObject([IO.File]::ReadAllText($env:CLIPAI_SHORTCUT_INTENT, [Text.Encoding]::UTF8))")
            code = code.replace("New-Object -ComObject WScript.Shell", "[Activator]::CreateInstance([Type]::GetTypeFromProgID('WScript.Shell'))")
            code = code.replace("Split-Path -Parent $taskIntent.target", "[IO.Path]::GetDirectoryName($taskIntent.target)")
        # Console output does not invoke a PowerShell cmdlet or warm Utility.
        marker = lambda name: "[Console]::Out.WriteLine('[DEBUG-shortcut-3718] " + name + "')\n"
        code = marker('shell-ready') + code
        code = code.replace('$taskShell = ', marker('intent-read') + '$taskShell = ')
        code = code.replace('$taskLink = $taskShell.CreateShortcut', marker('com-ready') + '$taskLink = $taskShell.CreateShortcut')
        code = code.replace('if ($taskIntent.create)', marker('link-open') + 'if ($taskIntent.create)')
        code = code.replace('$taskLink.Save()', '$taskLink.Save()\n' + marker('link-saved'))
        if args.mode == 'utility-first':
            code = "Import-Module ($PSHOME + '/Modules/Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psd1')\n" + code
        if args.mode == 'native-module-path':
            kwargs['env'] = dict(kwargs['env'], PSModulePath=str(Path(environment['SYSTEMROOT']) / 'System32/WindowsPowerShell/v1.0/Modules'))
        command = [*command[:-1], base64.b64encode(code.encode('utf-16-le')).decode()]
        started = time.monotonic()
        output = b''
        try:
            result = original(command, **kwargs)
            output = result.stdout
            return result
        except subprocess.TimeoutExpired as error:
            output = error.stdout or b''
            raise
        finally:
            print(json.dumps({'mode': args.mode, 'seconds': round(time.monotonic() - started, 3),
                'stages': [line for line in output.decode('utf-8', errors='replace').splitlines()
                           if line.startswith('[DEBUG-shortcut-3718]')]}), flush=True)

    subprocess.run = observed
    for index in range(3):
        native._shortcut(root / f'probe-{index}.lnk', 'launch', create=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
