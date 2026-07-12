from __future__ import annotations

import os
from pathlib import Path
import tempfile


class DotenvModelPreferenceStore:
    def __init__(self, path: str | Path = ".env") -> None:
        self._path = Path(path)

    def save_model(self, env_name: str, model: str) -> None:
        original = self._path.read_text(encoding="utf-8") if self._path.exists() else ""
        newline = "\r\n" if "\r\n" in original else "\n"
        trailing_newline = original.endswith(("\n", "\r"))
        replacement = f"{env_name}={model}"
        lines = original.splitlines()
        updated = False
        for index, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith("#") or "=" not in stripped:
                continue
            if stripped.split("=", 1)[0].strip() == env_name:
                lines[index] = replacement
                updated = True
                break
        if not updated:
            lines.append(replacement)
            trailing_newline = True
        content = newline.join(lines) + (newline if trailing_newline else "")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=self._path.parent,
            prefix=f".{self._path.name}.", suffix=".tmp", delete=False,
        )
        temp_path = Path(handle.name)
        try:
            with handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self._path)
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise
