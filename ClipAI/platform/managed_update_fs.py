from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re
import uuid
from typing import Any
from zipfile import ZipFile


class ManagedUpdateFileError(ValueError):
    pass


def native_path(path: str | Path) -> Path:
    """Return an absolute Windows extended-length path when applicable."""
    resolved = Path(path).resolve()
    value = str(resolved)
    if os.name != "nt" or value.startswith("\\\\?\\"):
        return resolved
    if value.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + value[2:])
    return Path("\\\\?\\" + value)


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


def unlink_file(path: str | Path) -> None:
    try:
        native_path(path).unlink(missing_ok=True)
    except OSError as exc:
        raise ManagedUpdateFileError("unable to remove managed update file") from exc


def extract_prefixed_zip(
    archive_path: str | Path,
    destination_root: str | Path,
    *,
    prefix: str = "clipai-managed-v1/",
) -> tuple[Path, ...]:
    """Extract a regular-file-only archive after validating every member."""
    destination = Path(destination_root).resolve()
    native_path(destination).mkdir(parents=True, exist_ok=True)
    planned: list[tuple[object, Path]] = []
    seen: set[str] = set()
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
            if normalized in seen:
                raise ManagedUpdateFileError("archive contains duplicate member")
            seen.add(normalized)
            file_type = (member.external_attr >> 16) & 0o170000
            if file_type not in (0, 0o100000):
                raise ManagedUpdateFileError("archive contains non-regular member")
            output = require_contained(destination, destination.joinpath(*relative.parts))
            planned.append((member, output))

        extracted: list[Path] = []
        for member, output in planned:
            native_path(output.parent).mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as source:
                atomic_write_bytes(output, source.read())
            extracted.append(output)
    return tuple(extracted)
