import json

import pytest

from ClipAI.platform.update_catalog import CatalogValidationError, parse_catalog, select_update


def _catalog(*releases: dict[str, object], **updates: object) -> bytes:
    payload: dict[str, object] = {
        "schema_version": 1,
        "catalog_kind": "clipai-managed-update-v1",
        "channel": "stable",
        "generated_at": "2026-09-13T00:00:00Z",
        "releases": list(releases),
    }
    payload.update(updates)
    return json.dumps(payload).encode()


def _release(version: str = "3.8.0", **updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "version": version,
        "bundle_url": f"https://releases.example/clipai-{version}.zip",
        "bundle_sha256": "a" * 64,
        "bundle_size": 123,
        "manifest_sha256": "b" * 64,
        "key_id": "release-2026",
        "minimum_launcher_version": "1.0",
    }
    payload.update(updates)
    return payload


def test_catalog_selects_newest_eligible_upgrade():
    catalog = parse_catalog(_catalog(_release("3.8.0"), _release("3.9.0")))
    selected = select_update(catalog, installed_version="3.7.3", launcher_version="1.0")
    assert selected is not None
    assert selected.version == "3.9.0"


def test_catalog_returns_none_for_equal_or_older_releases():
    catalog = parse_catalog(_catalog(_release("3.7.3"), _release("3.6.0")))
    assert select_update(catalog, installed_version="3.7.3", launcher_version="1.0") is None


@pytest.mark.parametrize(
    "content, message",
    [
        (_catalog(_release(), extra=True), "fields"),
        (_catalog(_release("3.8.0rc1")), "prerelease"),
        (_catalog(_release(bundle_url="http://example/bundle.zip")), "HTTPS"),
        (_catalog(_release(bundle_sha256="A" * 64)), "SHA-256"),
        (_catalog(_release(bundle_size=2 * 1024 * 1024 * 1024 + 1)), "supported range"),
        (_catalog(_release("3.8.0"), _release("3.8.0")), "duplicate"),
        (_catalog(_release(), catalog_kind="other"), "identity"),
    ],
)
def test_catalog_fails_closed_on_schema_or_policy_violation(content: bytes, message: str):
    with pytest.raises(CatalogValidationError, match=message):
        parse_catalog(content)


def test_catalog_honors_minimum_launcher_version():
    catalog = parse_catalog(_catalog(_release(minimum_launcher_version="2.0")))
    assert select_update(catalog, installed_version="3.7.3", launcher_version="1.9") is None
