import json
import os
from pathlib import Path
import subprocess

import pytest

from ClipAI.core.managed_update import transaction_id
from ClipAI.core.update_ports import CandidateBuildRequest, CandidateEnvironmentBuilder
from ClipAI.platform.candidate_environment import CandidateBuildError, OfflineCandidateEnvironmentBuilder


class Runner:
    def __init__(self, root: Path, version: str = "3.8.0") -> None:
        self.root = root
        self.version = version
        self.calls: list[tuple[list[str], dict[str, str]]] = []

    def __call__(self, command, environment, timeout):
        self.calls.append((list(command), dict(environment)))
        if command[2:4] == ["-m", "venv"]:
            python = self.root / ".venv" / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"python")
        stdout = ""
        if "importlib.metadata" in command[-1]:
            stdout = json.dumps({"version": self.version, "executable": str((self.root / ".venv" / "Scripts" / "python.exe").resolve())})
        return subprocess.CompletedProcess(command, 0, stdout, "")


def _request(tmp_path: Path) -> CandidateBuildRequest:
    (tmp_path / "wheelhouse").mkdir()
    (tmp_path / "requirements.lock").write_text("clipai==3.8.0", encoding="utf-8")
    (tmp_path / "payload").mkdir()
    (tmp_path / "payload" / "main.py").write_text("", encoding="utf-8")
    base = tmp_path / "base-python.exe"
    base.write_bytes(b"python")
    return CandidateBuildRequest(transaction_id("tx-1"), tmp_path.resolve(), base.resolve(), "3.8.0", "payload/main.py")


def test_offline_builder_uses_clean_isolated_commands_and_returns_proven_identity(tmp_path: Path):
    request = _request(tmp_path)
    runner = Runner(tmp_path)
    builder: CandidateEnvironmentBuilder = OfflineCandidateEnvironmentBuilder(environment={**os.environ, "VIRTUAL_ENV": "parent", "PYTHONPATH": "pollution", "PIP_INDEX_URL": "https://index"}, runner=runner)
    result = builder.build(request)
    assert result.version == "3.8.0"
    assert result.entrypoint == tmp_path / "payload" / "main.py"
    install, environment = runner.calls[1]
    assert "--no-index" in install
    assert "--find-links" in install
    assert "VIRTUAL_ENV" not in environment and "PYTHONPATH" not in environment
    assert environment["PIP_NO_INDEX"] == "1"
    assert all(call[0][1] == "-I" for call in runner.calls)


def test_builder_rejects_version_or_executable_mismatch(tmp_path: Path):
    request = _request(tmp_path)
    with pytest.raises(CandidateBuildError, match="does not match"):
        OfflineCandidateEnvironmentBuilder(environment={}, runner=Runner(tmp_path, "3.9.0")).build(request)


def test_builder_requires_complete_verified_bundle_inputs(tmp_path: Path):
    base = tmp_path / "python.exe"
    base.write_bytes(b"")
    request = CandidateBuildRequest(transaction_id("tx"), tmp_path.resolve(), base.resolve(), "3.8.0", "payload/main.py")
    with pytest.raises(CandidateBuildError, match="incomplete"):
        OfflineCandidateEnvironmentBuilder(environment={}, runner=Runner(tmp_path)).build(request)
