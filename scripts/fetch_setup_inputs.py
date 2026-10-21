"""Fetch only the reviewed, hash-pinned bootstrap input set (never latest)."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import urllib.request
from ClipAI.platform.managed_update_fs import file_sha256


def fetch(inputs: Path, output: Path, *, install_compiler: bool = False) -> None:
    data = json.loads(inputs.read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=False)
    downloads = [("runtime.archive", data["runtime"]),
                 ("compiler-installer.exe", data["compiler"])]
    for expected in data.get("corresponding_sources", {}).values():
        filename = expected["filename"]
        if (not filename or Path(filename).name != filename
                or filename in (".", "..") or "\\" in filename or ":" in filename):
            raise ValueError("unsafe corresponding source filename")
        downloads.append(("sources/" + filename, expected))
    for filename, expected in downloads:
        if not expected["url"].startswith("https://"):
            raise ValueError("pinned inputs require HTTPS")
        target = output / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(expected["url"], timeout=30) as source, target.open("xb") as destination:
            if not source.url.startswith("https://"):
                raise ValueError("bootstrap download redirected outside HTTPS")
            size = 0
            while block := source.read(1024 * 1024):
                size += len(block)
                if size > expected["size"]:
                    raise ValueError("bootstrap download exceeds pinned size")
                destination.write(block)
        if size != expected["size"] or file_sha256(target) != expected["sha256"]:
            raise ValueError("bootstrap download identity mismatch")
    if install_compiler:
        # CI-only tooling installation; actual compiler files are rechecked by
        # SetupReleaseBuilder before execution. No global PATH mutation.
        result = subprocess.run([str((output / "compiler-installer.exe").resolve()), "/VERYSILENT",
            "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/NOICONS", f"/DIR={output.resolve() / 'compiler'}"],
            timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise RuntimeError("pinned compiler installation failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--install-compiler", action="store_true")
    args = parser.parse_args()
    fetch(args.inputs, args.output, install_compiler=args.install_compiler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
