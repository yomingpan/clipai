from pathlib import Path

import pytest

from ClipAI.platform.managed_release_builder import write_offline_wheelhouse_lock
from ClipAI.platform.managed_update_fs import file_sha256


def fixture(tmp_path: Path):
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    (wheels / "clipai-3.7.9-py3-none-any.whl").write_bytes(b"app wheel")
    dependency = wheels / "langdetect-1.0.9-py3-none-any.whl"
    dependency.write_bytes(b"locally built wheel, not the source archive")
    lock = tmp_path / "dependencies.lock"
    lock.write_text("langdetect==1.0.9 --hash=sha256:" + "a" * 64 + "\n", encoding="utf-8")
    return wheels, dependency, lock, tmp_path / "requirements.lock"


def test_source_archive_hash_is_replaced_by_actual_built_wheel_hash(tmp_path):
    wheels, dependency, lock, output = fixture(tmp_path)
    write_offline_wheelhouse_lock(dependency_lock=lock, wheelhouse=wheels, output_path=output, app_version="3.7.9")
    assert f"langdetect==1.0.9 --hash=sha256:{file_sha256(dependency)}" in output.read_text()
    assert "a" * 64 not in output.read_text()
    assert "a" * 64 in lock.read_text()  # original source admission remains intact


@pytest.mark.parametrize("fault", ["missing", "extra", "version", "duplicate", "unhashed"])
def test_sealing_cannot_change_resolved_package_set(tmp_path, fault):
    wheels, dependency, lock, output = fixture(tmp_path)
    if fault == "missing":
        dependency.unlink()
    elif fault == "extra":
        (wheels / "unwanted-1.0-py3-none-any.whl").write_bytes(b"extra")
    elif fault == "version":
        dependency.rename(wheels / "langdetect-2.0-py3-none-any.whl")
    elif fault == "duplicate":
        (wheels / "langdetect-1.0.9-py2.py3-none-any.whl").write_bytes(b"second")
    else:
        lock.write_text("langdetect==1.0.9\n")
    with pytest.raises(ValueError):
        write_offline_wheelhouse_lock(dependency_lock=lock, wheelhouse=wheels, output_path=output, app_version="3.7.9")
    assert not output.exists()


def test_windows_python312_markers_select_only_target_dependencies(tmp_path):
    wheels, _, lock, output = fixture(tmp_path)
    lock.write_text('langdetect==1.0.9 ; sys_platform == "win32" --hash=sha256:' + "a" * 64 +
                    '\nnot-on-windows==1.0 ; sys_platform == "linux" --hash=sha256:' + "b" * 64 + "\n")
    write_offline_wheelhouse_lock(dependency_lock=lock, wheelhouse=wheels, output_path=output, app_version="3.7.9")
    assert "not-on-windows" not in output.read_text()
