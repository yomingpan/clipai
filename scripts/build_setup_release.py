"""Build Setup from the existing catalog-bound bundle, without rebuilding it."""
from __future__ import annotations

import argparse
import io
import os
import re
from pathlib import Path
import subprocess
import tarfile
from zipfile import ZipFile

from ClipAI.platform.setup_release_builder import SetupBuildRequest, SetupReleaseBuilder


def verify_source_commit(bundle: Path, commit: str) -> None:
    """Bind packaged first-party code and payload to a real Git source commit."""
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("source commit must be a full SHA")
    completed = subprocess.run(["git", "archive", commit], capture_output=True, check=True, timeout=30)
    with tarfile.open(fileobj=io.BytesIO(completed.stdout)) as tree:
        source = {m.name: tree.extractfile(m).read() for m in tree.getmembers() if m.isfile()}
    with ZipFile(bundle) as archive:
        app = [n for n in archive.namelist() if n.startswith("clipai-managed-v1/wheelhouse/clipai-") and n.endswith(".whl")]
        if len(app) != 1:
            raise ValueError("one source-bound app wheel is required")
        with ZipFile(io.BytesIO(archive.read(app[0]))) as wheel:
            packaged = [(n, wheel.read(n)) for n in wheel.namelist() if n.startswith("ClipAI/") or n == "main.py"]
        required = {n for n in source if n.startswith("ClipAI/") and n.endswith((".py", ".ico", ".html"))} | {"main.py"}
        if {n for n, _ in packaged} != required:
            raise ValueError("app wheel does not contain the complete first-party source set")
        for name in archive.namelist():
            if name.startswith("clipai-managed-v1/payload/") and not name.endswith("/"):
                packaged.append((name.removeprefix("clipai-managed-v1/payload/"), archive.read(name)))
    for name, content in packaged:
        expected = source.get(name)
        # Git checkout can convert text newlines on Windows. Those are the only
        # differences allowed; package resources and executable bytes stay exact.
        if name.endswith((".py", ".yaml", ".yml", ".json", ".md", ".html", ".txt")):
            content = content.replace(b"\r\n", b"\n")
            expected = expected.replace(b"\r\n", b"\n") if expected is not None else None
        if content != expected:
            raise ValueError(f"packaged source does not match commit: {name}")
    names = {name for name, _ in packaged}
    if "main.py" not in names or "ClipAI/app/first_install_bootstrap.py" not in names:
        raise ValueError("bootstrap source is absent from wheel")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("bundle", "catalog", "keyring", "inputs", "runtime-archive", "compiler", "output-root"):
        parser.add_argument("--" + option, required=True, type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--technical-candidate", action="store_true")
    args = parser.parse_args()
    if not args.technical_candidate:
        tagged = subprocess.run(["git", "rev-parse", "--verify", f"refs/tags/{args.tag}^{{commit}}"],
                                capture_output=True, text=True, check=True, timeout=10)
        if tagged.stdout.strip() != args.source_commit:
            raise ValueError("tag does not identify the release source commit")
    verify_source_commit(args.bundle, args.source_commit)
    setup = SetupReleaseBuilder(environment=dict(os.environ)).build(SetupBuildRequest(
        args.bundle, args.catalog, args.keyring, args.inputs, args.runtime_archive,
        args.compiler, Path(__file__).resolve().parents[1] / "packaging/windows/setup.iss",
        args.output_root, args.tag, args.source_commit, args.technical_candidate,
    ))
    print(f"setup={setup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
