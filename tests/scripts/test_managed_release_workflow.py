from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def test_tag_workflow_builds_and_publishes_complete_managed_release() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    required = (
        "contents: write",
        'python-version: "3.12"',
        "piptools compile",
        "--generate-hashes",
        "--constraint constraints\\windows.txt",
        "--prepare-lock",
        "--require-hashes",
        "--only-binary=:all:",
        "python -m scripts.build_managed_release",
        "CLIPAI_MANAGED_UPDATE_PRIVATE_KEY",
        "CLIPAI_MANAGED_UPDATE_KEY_ID",
        "CLIPAI_MANAGED_UPDATE_TRUSTED_KEYRING",
        "clipai-managed-$version.zip",
        "releases/download/$tag/clipai-managed-$version.zip",
        "scripts\\verify_managed_update.py --stage managed-bundle",
        "gh release create",
        "--draft",
        "gh release edit",
        "--draft=false",
        "if: always()",
    )
    for marker in required:
        assert marker in workflow

    assert workflow.count("python -m scripts.build_managed_release") == 2

    create = workflow.index("gh release create")
    publish = workflow.index("gh release edit")
    gate = workflow.index("scripts\\verify_managed_update.py --stage managed-bundle")
    assert gate < create < publish


def test_tag_workflow_pins_every_action_to_an_immutable_commit() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    action_references = re.findall(r"^\s*- uses: ([^\s#]+)(?:\s+#\s*(.+))?$", workflow, re.MULTILINE)

    assert action_references
    for reference, version_comment in action_references:
        assert re.fullmatch(r"actions/[^@]+@[0-9a-f]{40}", reference), reference
        assert re.fullmatch(r"v\d+(?:\.\d+){0,2}", version_comment), reference
