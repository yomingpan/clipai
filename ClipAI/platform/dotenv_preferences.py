from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile

from ClipAI.core.models import EnvironmentSetting

try:
    from dotenv import dotenv_values
except Exception:
    dotenv_values = None


class DotenvModelPreferenceStore:
    def __init__(self, path: str | Path = ".env") -> None:
        self._path = Path(path)

    def save_model(self, env_name: str, model: str) -> None:
        self.save_settings((EnvironmentSetting(env_name, model),))

    def save_settings(self, settings: tuple[EnvironmentSetting, ...]) -> None:
        if not settings:
            return
        original = self._path.read_text(encoding="utf-8") if self._path.exists() else ""
        newline = "\r\n" if "\r\n" in original else "\n"
        trailing_newline = original.endswith(("\n", "\r"))
        lines = original.splitlines()
        for setting in settings:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", setting.name):
                raise ValueError("environment setting name is invalid")
            if "\r" in setting.value or "\n" in setting.value:
                raise ValueError("environment setting value must be one line")
            replacement = f"{setting.name}={setting.value}"
            updated = False
            for index, line in enumerate(lines):
                stripped = line.lstrip()
                if stripped.startswith("#") or "=" not in stripped:
                    continue
                if stripped.split("=", 1)[0].strip() == setting.name:
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

    def read_settings(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        if dotenv_values is not None:
            return {str(key): str(value) for key, value in dotenv_values(self._path).items() if value is not None}
        values: dict[str, str] = {}
        for line in self._path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                name, value = stripped.split("=", 1)
                values[name.strip()] = value.strip().strip("'\"")
        return values
