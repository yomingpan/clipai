from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
import threading

from ClipAI.core.models import (
    RecipeActiveRevision,
    RecipeBuiltinUpdateDecision,
    RecipeRevision,
    RecipeRevisionSnapshot,
)


class JsonRecipeRevisionStore:
    def __init__(
        self,
        path: str | Path = "data/recipe_revisions.json",
    ) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()

    def load(self) -> RecipeRevisionSnapshot:
        with self._lock:
            if not self._path.exists():
                return RecipeRevisionSnapshot()
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict) or payload.get("schema_version") != 1:
                    raise ValueError("unsupported schema")
                revisions = tuple(
                    RecipeRevision(**item) for item in payload.get("revisions", ())
                )
                active = tuple(
                    RecipeActiveRevision(**item) for item in payload.get("active", ())
                )
                decisions = tuple(
                    RecipeBuiltinUpdateDecision(**item)
                    for item in payload.get("builtin_update_decisions", ())
                )
                return RecipeRevisionSnapshot(1, revisions, active, decisions)
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"corrupt Recipe revision store: {self._path}"
                ) from exc

    def save(self, snapshot: RecipeRevisionSnapshot) -> None:
        payload = {
            "schema_version": snapshot.schema_version,
            "revisions": [asdict(item) for item in snapshot.revisions],
            "active": [asdict(item) for item in snapshot.active],
            "builtin_update_decisions": [
                asdict(item) for item in snapshot.builtin_update_decisions
            ],
        }
        serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    dir=self._path.parent,
                    prefix=f".{self._path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as handle:
                    temporary_path = Path(handle.name)
                    handle.write(serialized)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary_path, self._path)
            finally:
                if temporary_path is not None and temporary_path.exists():
                    temporary_path.unlink()
