"""Download pinned A-stage experiments, verify bytes, and unpack into new scratch.

No downloaded program is executed here. This is not the production bootstrap
or updater. Sources are fixed in candidates.json; no latest resolution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import tarfile
import urllib.request
import uuid
from zipfile import ZipFile


INPUTS = Path(__file__).with_name("candidates.json")


def require_safe_member(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
        raise ValueError("unsafe archive member")


def extract(archive: Path, destination: Path, archive_format: str) -> None:
    destination.mkdir(exist_ok=False)
    if archive_format == "tar.gz":
        with tarfile.open(archive, "r:gz") as source:
            members = source.getmembers()
            for member in members:
                require_safe_member(member.name)
                if not (member.isfile() or member.isdir()):
                    raise ValueError("archive contains a link or special file")
            if sum(member.size for member in members) > 512 * 1024 * 1024:
                raise ValueError("expanded archive too large for this spike")
            source.extractall(destination, members=members, filter="data")
    elif archive_format == "zip":
        with ZipFile(archive) as source:
            for member in source.infolist():
                require_safe_member(member.filename)
                if stat.S_ISLNK(member.external_attr >> 16):
                    raise ValueError("archive contains a link")
            if sum(member.file_size for member in source.infolist()) > 512 * 1024 * 1024:
                raise ValueError("expanded archive too large for this spike")
            source.extractall(destination)
    else:
        raise ValueError("unsupported spike archive format")


def fetch(component: str, output_root: Path) -> Path:
    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))
    selected = inputs[component]
    output_root.mkdir(parents=True, exist_ok=True)
    # Windows mkdtemp(mode=0700) can prevent a restricted validation process
    # from reading artifacts created by the download process. Inherit the
    # workspace ACL, as the runtime probe does, and still reserve exclusively.
    root = (output_root / f"{component}-{uuid.uuid4().hex}").resolve()
    root.mkdir(exist_ok=False)
    evidence = {"component": component, "input": selected,
                "status": "failed", "distribution_admission": "not_covered"}
    try:
        archive = root / "download.archive"
        digest = hashlib.sha256()
        size = 0
        request = urllib.request.Request(selected["url"], headers={"User-Agent": "ClipAI-A-stage-spike"})
        with urllib.request.urlopen(request, timeout=30) as response, archive.open("xb") as target:
            if not response.url.startswith("https://"):
                raise ValueError("non-HTTPS download redirect")
            while data := response.read(1024 * 1024):
                size += len(data)
                if size > selected["size"]:
                    raise ValueError("download exceeds fixed asset size")
                digest.update(data)
                target.write(data)
        if (size, digest.hexdigest()) != (selected["size"], selected["sha256"]):
            raise ValueError("download does not match fixed asset identity")
        extract(archive, root / "unpacked", selected["format"])
        evidence.update(status="passed", verified_size=size, verified_sha256=digest.hexdigest())
    finally:
        (root / "input-evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
        )
    return root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component", choices=("runtime", "verifier"), required=True)
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/first-install-candidates"))
    args = parser.parse_args()
    root = fetch(args.component, args.output_root)
    print(json.dumps({"candidate_root": str(root), "distribution_admission": "not_covered"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
