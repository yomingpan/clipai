from __future__ import annotations

from pathlib import Path

from ClipAI.platform.dotenv_preferences import DotenvModelPreferenceStore
from ClipAI.core.models import EnvironmentSetting


def test_dotenv_model_store_updates_only_requested_value_and_preserves_context(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("# keys\nOPENAI_API_KEY=secret\nOPENAI_MODEL=old\nOTHER=value\n", encoding="utf-8")
    DotenvModelPreferenceStore(path).save_model("OPENAI_MODEL", "new")
    assert path.read_text(encoding="utf-8") == "# keys\nOPENAI_API_KEY=secret\nOPENAI_MODEL=new\nOTHER=value\n"


def test_dotenv_model_store_appends_missing_value(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("OPENAI_API_KEY=secret\n", encoding="utf-8")
    DotenvModelPreferenceStore(path).save_model("OPENAI_MODEL", "new")
    assert path.read_text(encoding="utf-8") == "OPENAI_API_KEY=secret\nOPENAI_MODEL=new\n"


def test_dotenv_store_atomically_updates_multiple_settings(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("# keep\nOPENAI_API_KEY=secret\nCLIPAI_PROVIDER=openai\n", encoding="utf-8")
    store = DotenvModelPreferenceStore(path)
    store.save_settings((EnvironmentSetting("CLIPAI_PROVIDER", "gemini"), EnvironmentSetting("GEMINI_MODEL", "flash")))
    assert path.read_text(encoding="utf-8") == "# keep\nOPENAI_API_KEY=secret\nCLIPAI_PROVIDER=gemini\nGEMINI_MODEL=flash\n"
    assert store.read_settings()["OPENAI_API_KEY"] == "secret"
