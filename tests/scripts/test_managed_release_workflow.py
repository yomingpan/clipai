from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def test_tag_workflow_builds_complete_candidate_without_publication() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    required = (
        "contents: read",
        'python-version: "3.12"',
        "piptools compile",
        "--generate-hashes",
        "--constraint constraints\\windows.txt",
        "--prepare-lock",
        "--require-hashes",
        "python -m pip wheel",
        "--wheel-dir release\\wheelhouse",
        "python -m scripts.build_managed_release",
        "CLIPAI_MANAGED_UPDATE_PRIVATE_KEY",
        "CLIPAI_MANAGED_UPDATE_KEY_ID",
        "CLIPAI_MANAGED_UPDATE_TRUSTED_KEYRING",
        '$privateKeyContent.TrimEnd("`r", "`n") + "`n"',
        "/inheritance:r",
        "[Security.Principal.WindowsIdentity]::GetCurrent().Name",
        "ssh-keygen.exe -y -f $privateKey",
        'throw "Managed update private key is invalid"',
        "clipai-managed-$version.zip",
        "releases/download/$tag/clipai-managed-$version.zip",
        "scripts\\verify_managed_update.py --stage managed-bundle",
        "scripts.build_setup_release",
        "scripts.verify_packaged_app",
        "scripts.verify_setup_extraction",
        "scripts.verify_release_assets",
        "--technical-candidate",
        "if: always()",
    )
    for marker in required:
        assert marker in workflow

    assert workflow.count("python -m scripts.build_managed_release") == 2
    assert "python -m pip download" not in workflow
    assert "--only-binary=:all:" not in workflow

    assert "gh release create" not in workflow
    assert "gh release edit" not in workflow
    assert "--draft=false" not in workflow
    gate = workflow.index("scripts.verify_release_assets")
    upload = workflow.index("actions/upload-artifact")
    assert gate < upload
    assert workflow.count("python -m build") == 1
    assert "release/setup/output/**" in workflow



def test_tag_workflow_pins_every_action_to_an_immutable_commit() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    action_references = re.findall(r"^\s*- uses: ([^\s#]+)(?:\s+#\s*(.+))?$", workflow, re.MULTILINE)

    assert action_references
    for reference, version_comment in action_references:
        assert re.fullmatch(r"actions/[^@]+@[0-9a-f]{40}", reference), reference
        assert re.fullmatch(r"v\d+(?:\.\d+){0,2}", version_comment), reference


def test_validation_branch_cannot_read_official_signing_secret_or_publish() -> None:
    import yaml
    # BaseLoader avoids YAML 1.1 interpreting the Actions `on` key as True.
    workflow = yaml.load((ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert workflow["on"]["push"]["branches"] == ["release-validation/**"]
    assert workflow["on"]["push"]["tags"] == ["v*"]
    assert workflow["permissions"] == {"contents": "read"}
    steps = workflow["jobs"]["build-verify-candidate"]["steps"]
    secret_steps = [step for step in steps if "secrets." in str(step)]
    assert len(secret_steps) == 1
    assert secret_steps[0]["if"] == "github.ref_type == 'tag'"
    ephemeral = next(step for step in steps if step.get("name") == "Prepare ephemeral validation authority")
    assert ephemeral["if"] == "github.ref_type == 'branch'"
    assert "'ssh-keygen.exe', '-q', '-t', 'ed25519'" in ephemeral["run"]
    assert "CLIPAI_VALIDATION_KEY_ID" in ephemeral["run"]
    assert sum("--payload-root" in step.get("run", "") for step in steps) == 1
    assert sum("--bundle " in step.get("run", "") and "build_setup_release" in step.get("run", "") for step in steps) == 1
    cleanup = steps[-1]
    assert cleanup["if"] == "always()"
    assert "signing-key.pub" in cleanup["run"]
