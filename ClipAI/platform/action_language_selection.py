from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile

from ClipAI.core.errors import ActionLanguagePackError
from ClipAI.core.models import ActionLanguagePackSelectionRead


_PACK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class JsonActionLanguagePackSelectionStore:
    """Privacy-minimal atomic persistence for the next-start pack ID."""

    def __init__(self, path: str | Path = "data/action_language_pack.json") -> None:
        self._path = Path(path)

    def load(self) -> ActionLanguagePackSelectionRead:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return ActionLanguagePackSelectionRead(None)
        except (OSError, UnicodeError, json.JSONDecodeError):
            return ActionLanguagePackSelectionRead(
                None,
                "action_language.selection_unreadable",
            )
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version",
            "selected_pack_id",
        }:
            return ActionLanguagePackSelectionRead(
                None,
                "action_language.selection_invalid",
            )
        selected = payload.get("selected_pack_id")
        if payload.get("schema_version") != 1 or not isinstance(selected, str):
            return ActionLanguagePackSelectionRead(
                None,
                "action_language.selection_invalid",
            )
        if _PACK_ID.fullmatch(selected) is None:
            return ActionLanguagePackSelectionRead(
                None,
                "action_language.selection_invalid",
            )
        return ActionLanguagePackSelectionRead(selected)

    def save(self, pack_id: str) -> None:
        if _PACK_ID.fullmatch(pack_id) is None:
            raise ValueError("action language pack id is invalid")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self._path.parent,
                    prefix=f".{self._path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as handle:
                    json.dump(
                        {"schema_version": 1, "selected_pack_id": pack_id},
                        handle,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                    temporary_path = Path(handle.name)
                os.replace(temporary_path, self._path)
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
        except OSError as exc:
            raise ActionLanguagePackError(
                "selection_save_failed",
                "selection.selected_pack_id",
                "Unable to save the Action Language selection.",
            ) from exc
