import pytest

from ClipAI.platform.update_bundle import BundleValidationError, parse_install_manifest
from ClipAI.platform.update_signature import SIGNING_NAMESPACE


def _manifest(**updates: object) -> dict[str, object]:
    lock_hash = "a" * 64
    payload: dict[str, object] = {
        "schema_version": 1,
        "app_version": "3.8.0",
        "bundle_format": "clipai-managed-v1",
        "entrypoint": "payload/main.py",
        "python_requires": ">=3.12,<3.13",
        "requirements_lock_sha256": lock_hash,
        "files": [
            {"path": "payload/main.py", "size": 10, "sha256": "b" * 64, "role": "payload"},
            {"path": "requirements.lock", "size": 20, "sha256": lock_hash, "role": "metadata"},
            {"path": "wheelhouse/clipai.whl", "size": 30, "sha256": "c" * 64, "role": "wheel"},
        ],
        "signing_namespace": SIGNING_NAMESPACE,
        "key_id": "release-2026",
    }
    payload.update(updates)
    return payload


def test_install_manifest_accepts_complete_offline_bundle_inventory():
    manifest = parse_install_manifest(_manifest())
    assert manifest.entrypoint == "payload/main.py"
    assert manifest.files[-1].path.startswith("wheelhouse/")


@pytest.mark.parametrize(
    "mutation, message",
    [
        ({"entrypoint": "payload/missing.py"}, "entrypoint"),
        ({"files": _manifest()["files"][:2]}, "wheelhouse"),
        ({"files": [{"path": "data/user.json", "size": 1, "sha256": "d" * 64, "role": "payload"}]}, "user-owned"),
        ({"entrypoint": "../main.py"}, "contained"),
        ({"signing_namespace": "other"}, "namespace"),
    ],
)
def test_install_manifest_fails_closed(mutation: dict[str, object], message: str):
    with pytest.raises(BundleValidationError, match=message):
        parse_install_manifest(_manifest(**mutation))
