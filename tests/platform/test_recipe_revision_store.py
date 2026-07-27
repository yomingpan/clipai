from __future__ import annotations

from ClipAI.core.models import RecipeActiveRevision, RecipeRevision
from ClipAI.platform.recipe_revisions import JsonRecipeRevisionStore
from ClipAI.services.recipe_revisions import RecipeRevisionSnapshot


def snapshot() -> RecipeRevisionSnapshot:
    revision = RecipeRevision(
        revision_id="revision-1",
        action_id="rewrite",
        press_type="short",
        parent_version="builtin",
        version_id="personal-v1",
        created_at="2026-07-27T00:00:00+00:00",
        system_prompt="Improved",
        prompt="Rewrite {input}",
        validation_summary="1／1 比較偏好新版本",
        provider="openai",
        model="gpt-test",
    )
    return RecipeRevisionSnapshot(
        revisions=(revision,),
        active=(RecipeActiveRevision("rewrite", "short", "revision-1"),),
    )


def test_missing_revision_file_loads_empty_snapshot(tmp_path) -> None:
    assert JsonRecipeRevisionStore(tmp_path / "revisions.json").load() == RecipeRevisionSnapshot()


def test_revision_snapshot_round_trips_as_utf8_json(tmp_path) -> None:
    path = tmp_path / "revisions.json"
    store = JsonRecipeRevisionStore(path)

    store.save(snapshot())

    assert store.load() == snapshot()
    assert "比較偏好" in path.read_text(encoding="utf-8")


def test_corrupt_revision_file_is_preserved_and_reported(tmp_path) -> None:
    path = tmp_path / "revisions.json"
    path.write_text("{broken", encoding="utf-8")

    try:
        JsonRecipeRevisionStore(path).load()
    except ValueError as exc:
        assert "corrupt Recipe revision store" in str(exc)
    else:
        raise AssertionError("corrupt store should fail")

    assert path.read_text(encoding="utf-8") == "{broken"
