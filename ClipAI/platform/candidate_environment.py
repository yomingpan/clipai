from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import json
from pathlib import Path, PurePosixPath
import subprocess

from packaging.version import InvalidVersion, Version

from ClipAI.core.update_ports import CandidateBuildRequest, CandidateEnvironment
from ClipAI.platform.managed_update_fs import native_path, remove_tree, require_contained


RunCommand = Callable[[Sequence[str], Mapping[str, str], float], subprocess.CompletedProcess[str]]


class CandidateBuildError(RuntimeError):
    pass


def _run(command: Sequence[str], environment: Mapping[str, str], timeout_sec: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=dict(environment),
        timeout=timeout_sec,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


class OfflineCandidateEnvironmentBuilder:
    """Create and prove one candidate using only its verified wheelhouse."""

    def __init__(self, *, environment: Mapping[str, str], runner: RunCommand = _run, timeout_sec: float = 120.0) -> None:
        self._environment = _isolated_environment(environment)
        self._runner = runner
        self._timeout_sec = timeout_sec

    def build(self, request: CandidateBuildRequest) -> CandidateEnvironment:
        root = request.candidate_root.resolve()
        if not root.is_absolute() or not request.base_python.is_absolute():
            raise CandidateBuildError("candidate paths must be absolute")
        wheelhouse = require_contained(root, root / "wheelhouse")
        lock = require_contained(root, root / "requirements.lock")
        entrypoint = require_contained(root, root.joinpath(*PurePosixPath(request.entrypoint).parts))
        if not native_path(wheelhouse).is_dir() or not native_path(lock).is_file() or not native_path(entrypoint).is_file():
            raise CandidateBuildError("candidate bundle inputs are incomplete")
        expected = _normalized_version(request.expected_version)
        venv = require_contained(root, root / ".venv")
        remove_tree(venv)
        self._checked([str(request.base_python), "-I", "-m", "venv", str(native_path(venv))], "venv creation")
        python = venv / "Scripts" / "python.exe"
        if not native_path(python).is_file():
            raise CandidateBuildError("venv creation did not produce candidate Python")
        self._checked(
            [str(native_path(python)), "-I", "-m", "pip", "install", "--no-index", "--disable-pip-version-check", "--find-links", str(native_path(wheelhouse)), "--requirement", str(native_path(lock))],
            "offline installation",
        )
        probe = self._checked(
            [str(native_path(python)), "-I", "-c", "import importlib.metadata,json,sys; print(json.dumps({'version':importlib.metadata.version('clipai'),'executable':sys.executable}))"],
            "candidate identity probe",
        )
        try:
            identity = json.loads(probe.stdout.strip())
            actual_version = _normalized_version(identity["version"])
            actual_executable = Path(identity["executable"]).resolve()
        except (KeyError, TypeError, json.JSONDecodeError, CandidateBuildError) as exc:
            raise CandidateBuildError("candidate identity probe returned invalid evidence") from exc
        if actual_version != expected or str(actual_executable).casefold() != str(python.resolve()).casefold():
            raise CandidateBuildError("candidate identity does not match expected version or executable")
        return CandidateEnvironment(root, python, entrypoint, actual_version)

    def _checked(self, command: list[str], purpose: str) -> subprocess.CompletedProcess[str]:
        try:
            completed = self._runner(command, self._environment, self._timeout_sec)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CandidateBuildError(f"{purpose} did not complete") from exc
        if completed.returncode != 0:
            raise CandidateBuildError(f"{purpose} failed with exit code {completed.returncode}")
        return completed


def _isolated_environment(environment: Mapping[str, str]) -> dict[str, str]:
    blocked = {"VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "PIP_CONFIG_FILE", "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL"}
    isolated = {key: value for key, value in environment.items() if key.upper() not in blocked}
    isolated.update({"PYTHONNOUSERSITE": "1", "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"})
    return isolated


def _normalized_version(value: str) -> str:
    try:
        parsed = Version(value)
    except InvalidVersion as exc:
        raise CandidateBuildError("candidate version is invalid") from exc
    if str(parsed) != value:
        raise CandidateBuildError("candidate version is not normalized")
    return value
