from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ClipAI.platform.recipe_revisions import JsonRecipeRevisionStore
from ClipAI.services.action_catalog import ActionCatalog
from ClipAI.services.recipe_revisions import RecipeRevisionCoordinator


@dataclass(frozen=True)
class RecipeConfigurationOverlay:
    """Result of composing the local personal overlay onto built-in Actions."""

    revisions: RecipeRevisionCoordinator | None
    warning: str = ""


def load_recipe_configuration_overlay(
    actions: ActionCatalog,
    path: str | Path = "data/recipe_revisions.json",
) -> RecipeConfigurationOverlay:
    """Load the only personal-prompt overlay into the authoritative catalog."""
    try:
        revisions = RecipeRevisionCoordinator(
            actions,
            JsonRecipeRevisionStore(path),
        )
    except ValueError:
        return RecipeConfigurationOverlay(
            None,
            "個人 Recipe 版本資料無法讀取；目前已使用內建 Recipe，並停用套用功能。原檔案仍保留在本機。",
        )
    return RecipeConfigurationOverlay(revisions)
