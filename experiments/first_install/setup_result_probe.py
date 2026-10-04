"""Compile/run Setup with a harmless fixture engine and inspect final captions.

The fixture only prints phases and exits; it never installs/removes any app.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import uuid


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--compiler", type=Path, required=True)
    args = parser.parse_args()
    work = Path("artifacts/first-install-diagnostic").resolve() / f"setup-result-{uuid.uuid4().hex}"
    stage = work / "stage"
    stage.mkdir(parents=True)
    shutil.copytree(args.stage / "runtime", stage / "runtime")
    engine = stage / "setup-engine"
    engine.mkdir()
    shutil.copy2(args.stage / "setup-engine/clipai.ico", engine / "clipai.ico")
    script = work / "probe.iss"
    script.write_text('#include "' + str(args.script.resolve()) + '"\n' + r'''

<event('DeinitializeSetup')>
procedure CaptureFinalCaption;
begin
  SaveStringToFile(ExpandConstant('{param:PROOF}'),
    WizardForm.FinishedHeadingLabel.Caption + #13#10 + WizardForm.FinishedLabel.Caption, False);
end;
''', encoding="utf-8")
    output = work / "output"
    command = [str(args.compiler.resolve()), f"/DStageRoot={stage}", f"/DOutputRoot={output}",
               "/DAppVersion=3.7.8", str(script)]
    proofs = []
    for failure in (True, False):
        (engine / "entry.py").write_text(
            "print('CLIPAI_PHASE:" + ("failed:InstallationBusyError" if failure else "uninstalled:")
            + "', flush=True)\nraise SystemExit(" + ("1" if failure else "0") + ")\n", encoding="utf-8")
        compiled = subprocess.run(command, capture_output=True, text=True)
        if compiled.returncode:
            (work / "compile-errors.txt").write_text(compiled.stdout + compiled.stderr, encoding="utf-8")
            raise RuntimeError("probe_compilation_failed")
        proof = work / ("failure.txt" if failure else "success.txt")
        run = subprocess.run([str(output / "ClipAI-Preview-3.7.8-Setup.exe"), "/VERYSILENT",
                              "/SUPPRESSMSGBOXES", "/NORESTART", "/REMOVE=1", f"/PROOF={proof}",
                              f"/LOG={work / ('failure.log' if failure else 'success.log')}"],
                             timeout=120)
        caption = proof.read_text(encoding="utf-8-sig")
        expected = "Removal did not complete" if failure else "ClipAI Preview removed"
        passed = expected in caption and ("has finished installing" not in caption)
        proofs.append({"fixture": "failure" if failure else "success", "exit_code": run.returncode,
                       "caption_passed": passed, "caption": caption})
    (work / "proof.json").write_text(json.dumps(proofs, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"proof": str(work / "proof.json"), "results": proofs}))
    if not all(p["caption_passed"] and p["exit_code"] == (100 if p["fixture"] == "failure" else 0)
               for p in proofs):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
