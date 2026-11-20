from pathlib import Path

import pytest

from experiments.first_install.probe_runtime import copy_runtime, isolated_environment, probe
from experiments.first_install.fetch_candidates import extract, require_safe_member


def test_probe_child_environment_excludes_credentials_and_machine_configuration(tmp_path, monkeypatch):
    for name in ("GEMINI_API_KEY", "PYTHONHOME", "TCL_LIBRARY", "PIP_EXTRA_INDEX_URL", "PATH"):
        monkeypatch.setenv(name, "must-not-reach-child")
    monkeypatch.setenv("PROGRAMDATA", "required-native-os-location")

    environment = isolated_environment(tmp_path)

    assert not {"GEMINI_API_KEY", "PYTHONHOME", "TCL_LIBRARY", "PIP_EXTRA_INDEX_URL"} & environment.keys()
    assert environment["PATH"] == ""
    assert environment["PIP_NO_INDEX"] == "1"
    assert environment["PROGRAMDATA"] == "required-native-os-location"
    assert Path(environment["TEMP"]).parent == tmp_path


def test_copy_rejects_nested_target_before_mutating_source(tmp_path):
    (tmp_path / "python.exe").write_bytes(b"source")

    with pytest.raises(ValueError, match="disjoint"):
        copy_runtime(tmp_path, tmp_path / "nested")

    assert not (tmp_path / "nested").exists()
    assert (tmp_path / "python.exe").read_bytes() == b"source"


def test_copy_does_not_adopt_a_venv_as_a_portable_runtime(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "python.exe").write_bytes(b"venv")
    (source / "pyvenv.cfg").write_text("home = original-runtime\n")
    target = tmp_path / "target"

    with pytest.raises(ValueError, match="not a venv"):
        copy_runtime(source, target)

    assert not target.exists()


def test_failed_probe_preserves_old_work_and_never_claims_vm_success(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    previous = output / "previous-owned-run"
    previous.mkdir()
    evidence = previous / "report.json"
    evidence.write_bytes(b"preserve")

    report_path, report = probe(tmp_path / "missing-runtime", output)

    assert report["status"] == "failed"
    assert report["phase"] == "copy_base_runtime"
    assert report["clean_vm_gate"] == "not_covered"
    assert report["synthetic_payload"] is True
    assert report_path.is_file()
    assert evidence.read_bytes() == b"preserve"


@pytest.mark.parametrize("name", ("../outside", "/absolute", "C:/outside", "folder\\outside", "a/../../escape"))
def test_candidate_archive_rejects_escaping_member_names(name):
    with pytest.raises(ValueError, match="unsafe"):
        require_safe_member(name)


def test_candidate_archive_is_validated_before_extracting_any_member(tmp_path):
    from zipfile import ZipFile

    archive = tmp_path / "untrusted.zip"
    with ZipFile(archive, "w") as source:
        source.writestr("safe/file", b"safe")
        source.writestr("../escape", b"escape")
    destination = tmp_path / "unpacked"

    with pytest.raises(ValueError, match="unsafe"):
        extract(archive, destination, "zip")

    assert not list(destination.iterdir())
    assert not (tmp_path / "escape").exists()
