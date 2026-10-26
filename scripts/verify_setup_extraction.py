"""Run compiled Setup in read-only payload proof mode; never install or remove."""
import argparse
import json
from pathlib import Path
import subprocess
import uuid
from ClipAI.platform.managed_update_fs import atomic_write_json, file_sha256


def verify(assets: Path) -> Path:
    proof = json.loads((assets / "provenance.json").read_text())
    setup = assets / proof["setup"]["filename"]
    if file_sha256(setup) != proof["setup"]["sha256"]:
        raise ValueError("Setup identity mismatch")
    receipt = assets / ("extracted-" + uuid.uuid4().hex + ".txt")
    result = subprocess.run([str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/VERIFYONLY=1",
                             f"/VERIFICATIONOUTPUT={receipt}"], timeout=120,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        if result.returncode != 0 or receipt.read_text() != proof["bundle"]["sha256"]:
            raise RuntimeError("compiled Setup payload verification failed")
    finally:
        receipt.unlink(missing_ok=True)
    output = assets / "setup-extraction.json"
    atomic_write_json(output, {"status": "passed", "evidence_level": "local-native-extraction",
                              "installation_tested": False, "clean_vm": False,
                              "bundle_sha256": proof["bundle"]["sha256"], "setup_sha256": file_sha256(setup)})
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    args = parser.parse_args()
    print(verify(args.assets.resolve()))
