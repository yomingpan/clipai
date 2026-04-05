from __future__ import annotations

from pathlib import Path


def test_rewrite_complete_no_longer_overrides_legacy_ollama_model() -> None:
    content = Path("config/actions.yaml").read_text(encoding="utf-8")
    assert "id: rewrite_complete" in content
    assert "model: gemma3:1b" not in content
