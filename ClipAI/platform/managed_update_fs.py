from __future__ import annotations

from collections.abc import Iterable
import json
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import time
import uuid
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


class ManagedUpdateFileError(ValueError):
    pass


def canonical_path(path: str | Path) -> Path:
    """Return one absolute artifact/identity spelling without a long-path prefix."""
    value = str(Path(path).resolve())
    if os.name == "nt" and value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif os.name == "nt" and value.startswith("\\\\?\\"):
        value = value[4:]
    return Path(value).resolve()


def native_path(path: str | Path) -> Path:
    """Return an absolute Windows extended-length path when applicable."""
    resolved = canonical_path(path)
    value = str(resolved)
    if os.name != "nt" or value.startswith("\\\\?\\"):
        return resolved
    if value.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + value[2:])
    return Path("\\\\?\\" + value)


def directory_names(path: str | Path) -> tuple[str, ...]:
    """List direct child directories through the managed long-path boundary."""
    root = native_path(path)
    if not root.exists():
        return ()
    if not root.is_dir():
        raise ManagedUpdateFileError("managed update directory is not a directory")
    try:
        return tuple(sorted(
            child.name
            for child in root.iterdir()
            if child.is_dir() and not child.is_symlink()
        ))
    except OSError as exc:
        raise ManagedUpdateFileError("unable to list managed update directory") from exc


def require_contained(root: str | Path, candidate: str | Path) -> Path:
    resolved_root = Path(root).resolve()
    resolved_candidate = Path(candidate).resolve()
    if resolved_candidate == resolved_root or resolved_candidate.is_relative_to(resolved_root):
        return resolved_candidate
    raise ManagedUpdateFileError("path escapes managed root")


def read_bytes(path: str | Path, *, maximum_size: int | None = None) -> bytes:
    file_path = native_path(path)
    if maximum_size is not None and file_path.stat().st_size > maximum_size:
        raise ManagedUpdateFileError("file exceeds maximum size")
    return file_path.read_bytes()


def read_json(path: str | Path, *, maximum_size: int = 4 * 1024 * 1024) -> Any:
    try:
        return json.loads(read_bytes(path, maximum_size=maximum_size).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ManagedUpdateFileError("invalid UTF-8 JSON") from exc


def atomic_write_json(path: str | Path, payload: object) -> None:
    content = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    atomic_write_bytes(path, content)


def atomic_write_bytes(path: str | Path, content: bytes) -> None:
    destination = Path(path).resolve()
    native_path(destination.parent).mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.{uuid.uuid4().hex[:8]}.tmp"
    )
    try:
        with native_path(temporary).open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(native_path(temporary), native_path(destination))
    finally:
        try:
            native_path(temporary).unlink(missing_ok=True)
        except OSError:
            pass


def atomic_write_verified_chunks(
    path: str | Path,
    chunks: Iterable[bytes],
    *,
    expected_size: int,
    expected_sha256: str,
    maximum_size: int,
) -> Path:
    if expected_size <= 0 or maximum_size <= 0 or expected_size > maximum_size:
        raise ManagedUpdateFileError("stream size identity is invalid")
    if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise ManagedUpdateFileError("stream digest identity is invalid")
    destination = canonical_path(path)
    native_path(destination.parent).mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex[:8]}.tmp")
    digest = hashlib.sha256()
    written = 0
    try:
        with native_path(temporary).open("xb") as handle:
            for chunk in chunks:
                if not isinstance(chunk, bytes):
                    raise ManagedUpdateFileError("stream chunk is not bytes")
                if not chunk:
                    continue
                written += len(chunk)
                if written > expected_size or written > maximum_size:
                    raise ManagedUpdateFileError("stream exceeds size identity")
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if written != expected_size or digest.hexdigest() != expected_sha256:
            raise ManagedUpdateFileError("stream identity does not match")
        os.replace(native_path(temporary), native_path(destination))
        return destination
    except ManagedUpdateFileError:
        raise
    except OSError as exc:
        raise ManagedUpdateFileError("unable to atomically write verified stream") from exc
    finally:
        try:
            native_path(temporary).unlink(missing_ok=True)
        except OSError:
            pass


def unlink_file(path: str | Path) -> None:
    try:
        native_path(path).unlink(missing_ok=True)
    except OSError as exc:
        raise ManagedUpdateFileError("unable to remove managed update file") from exc


def remove_tree(path: str | Path, *, attempts: int = 5, delay_sec: float = 0.05) -> None:
    target = native_path(path)
    for attempt in range(attempts):
        try:
            shutil.rmtree(target)
            return
        except FileNotFoundError:
            return
        except OSError as exc:
            if getattr(exc, "winerror", None) != 145 or attempt + 1 == attempts:
                raise ManagedUpdateFileError("unable to remove managed update directory") from exc
            time.sleep(delay_sec)


def regular_file_inventory(root: str | Path) -> tuple[str, ...]:
    resolved = Path(root).resolve()
    native_root = native_path(resolved)
    if not native_root.is_dir():
        raise ManagedUpdateFileError("managed update directory is missing")
    inventory: list[str] = []
    for directory, directory_names, file_names in os.walk(native_root):
        directory_names.sort()
        file_names.sort()
        current = Path(directory)
        for name in file_names:
            candidate = current / name
            if candidate.is_symlink() or not candidate.is_file():
                raise ManagedUpdateFileError("managed update tree contains non-regular file")
            inventory.append(candidate.relative_to(native_root).as_posix())
    return tuple(inventory)


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with native_path(path).open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def copy_regular_tree(source_root: str | Path, destination_root: str | Path) -> tuple[Path, ...]:
    source = Path(source_root).resolve()
    destination = Path(destination_root).resolve()
    copied: list[Path] = []
    for relative in regular_file_inventory(source):
        parts = PurePosixPath(relative).parts
        output = require_contained(destination, destination.joinpath(*parts))
        _copy_file_atomically(source.joinpath(*parts), output)
        copied.append(output)
    return tuple(copied)


def copy_file_atomically(
    source_path: str | Path,
    destination_path: str | Path,
    *,
    maximum_size: int,
) -> Path:
    source = Path(source_path).resolve()
    destination = Path(destination_path).resolve()
    if maximum_size <= 0:
        raise ManagedUpdateFileError("copy size limit must be positive")
    source_native = native_path(source)
    if source_native.is_symlink() or not source_native.is_file():
        raise ManagedUpdateFileError("managed update source is not a regular file")
    if source_native.stat().st_size > maximum_size:
        raise ManagedUpdateFileError("managed update source exceeds size limit")
    _copy_file_atomically(source, destination)
    return destination


def write_prefixed_zip(
    destination_path: str | Path,
    members: dict[str, bytes],
    *,
    prefix: str = "clipai-managed-v1/",
) -> None:
    destination = Path(destination_path).resolve()
    native_path(destination.parent).mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with ZipFile(native_path(temporary), "x", compression=ZIP_DEFLATED) as archive:
            for relative, content in sorted(members.items()):
                normalized = _normalized_archive_relative(relative)
                info = ZipInfo(prefix + normalized, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, content)
        os.replace(native_path(temporary), native_path(destination))
    finally:
        try:
            native_path(temporary).unlink(missing_ok=True)
        except OSError:
            pass


def extract_prefixed_zip(
    archive_path: str | Path,
    destination_root: str | Path,
    *,
    prefix: str = "clipai-managed-v1/",
    maximum_uncompressed_size: int = 2 * 1024 * 1024 * 1024,
) -> tuple[Path, ...]:
    """Extract a regular-file-only archive after validating every member."""
    destination = Path(destination_root).resolve()
    native_path(destination).mkdir(parents=True, exist_ok=True)
    planned: list[tuple[ZipInfo, Path]] = []
    seen: set[str] = set()
    total_size = 0
    with ZipFile(native_path(archive_path), "r") as archive:
        for member in archive.infolist():
            name = member.filename
            if not name.startswith(prefix):
                raise ManagedUpdateFileError("archive member has invalid prefix")
            relative_text = name[len(prefix) :]
            if not relative_text or name.endswith("/"):
                continue
            if "\\" in relative_text or re.match(r"^[A-Za-z]:", relative_text):
                raise ManagedUpdateFileError("archive member path is not normalized")
            relative = PurePosixPath(relative_text)
            if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
                raise ManagedUpdateFileError("archive member escapes payload root")
            normalized = relative.as_posix()
            collision_key = normalized.casefold()
            if collision_key in seen:
                raise ManagedUpdateFileError("archive contains duplicate member")
            seen.add(collision_key)
            file_type = (member.external_attr >> 16) & 0o170000
            if file_type not in (0, 0o100000):
                raise ManagedUpdateFileError("archive contains non-regular member")
            total_size += member.file_size
            if total_size > maximum_uncompressed_size:
                raise ManagedUpdateFileError("archive exceeds uncompressed size limit")
            output = require_contained(destination, destination.joinpath(*relative.parts))
            planned.append((member, output))

        extracted: list[Path] = []
        for member, output in planned:
            _extract_member_atomically(archive, member, output)
            extracted.append(output)
    return tuple(extracted)


def _normalized_archive_relative(value: str) -> str:
    if "\\" in value or re.match(r"^[A-Za-z]:", value):
        raise ManagedUpdateFileError("archive member path is not normalized")
    relative = PurePosixPath(value)
    if (
        not value
        or relative.is_absolute()
        or ".." in relative.parts
        or "." in relative.parts
        or relative.as_posix() != value
    ):
        raise ManagedUpdateFileError("archive member escapes payload root")
    return value


def _extract_member_atomically(archive: ZipFile, member: ZipInfo, destination: Path) -> None:
    output = destination.resolve()
    native_path(output.parent).mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex[:8]}.tmp")
    written = 0
    try:
        with archive.open(member, "r") as source, native_path(temporary).open("xb") as target:
            while chunk := source.read(1024 * 1024):
                written += len(chunk)
                if written > member.file_size:
                    raise ManagedUpdateFileError("archive member exceeds declared size")
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        if written != member.file_size:
            raise ManagedUpdateFileError("archive member size does not match")
        os.replace(native_path(temporary), native_path(output))
    finally:
        try:
            native_path(temporary).unlink(missing_ok=True)
        except OSError:
            pass


def _copy_file_atomically(source: Path, destination: Path) -> None:
    output = destination.resolve()
    native_path(output.parent).mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with native_path(source).open("rb") as source_handle, native_path(temporary).open("xb") as target:
            while chunk := source_handle.read(1024 * 1024):
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        os.replace(native_path(temporary), native_path(output))
    finally:
        try:
            native_path(temporary).unlink(missing_ok=True)
        except OSError:
            pass
