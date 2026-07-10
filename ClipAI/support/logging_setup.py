from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path


@dataclass(frozen=True)
class Diagnostics:
    flags: frozenset[str] = frozenset()

    def enabled(self, name: str) -> bool:
        return name in self.flags


@dataclass(frozen=True)
class LoggingSettings:
    enabled: bool = True
    level: str = "INFO"
    console: bool = False
    console_level: str = "INFO"
    file_enabled: bool = True
    file_path: str = "logs/clipai.log"
    file_level: str = "DEBUG"
    module_levels: tuple[tuple[str, str], ...] = ()
    diagnostics: Diagnostics = field(default_factory=Diagnostics)


def configure_logging(settings: LoggingSettings) -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    if not settings.enabled:
        root.addHandler(logging.NullHandler())
        return
    root.setLevel(_level(settings.level))
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    if settings.console:
        console = logging.StreamHandler()
        console.setLevel(_level(settings.console_level))
        console.setFormatter(formatter)
        root.addHandler(console)
    if settings.file_enabled:
        path = Path(settings.file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setLevel(_level(settings.file_level))
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    for module, level in settings.module_levels:
        logging.getLogger(module).setLevel(_level(level))


def _level(value: str) -> int:
    level = getattr(logging, value.upper(), None)
    if not isinstance(level, int):
        raise ValueError(f"unsupported logging level: {value}")
    return level

