from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ClipAI.app.config_loader import load_config_bundle
from ClipAI.app.config_schema import ConfigBundle
from ClipAI.app.language_pack_loader import (
    ActionLanguagePackLoader,
    load_feature_skeleton,
)
from ClipAI.app.language_pack_selection_backend import (
    AppActionLanguageSelectionBackend,
)
from ClipAI.core.errors import ActionLanguagePackError, ActionLanguagePackErrorCode
from ClipAI.core.models import (
    ActionLanguagePackRecovery,
    ActionLanguagePackSelectionState,
)
from ClipAI.core.ports import ActionLanguagePackSelectionStore
from ClipAI.services.action_language_packs import CompiledActionLanguagePack


@dataclass(frozen=True)
class ActionLanguageBootstrapResult:
    bundle: ConfigBundle
    state: ActionLanguagePackSelectionState
    selection_backend: AppActionLanguageSelectionBackend
    diagnostic_codes: tuple[str, ...] = ()


def bootstrap_action_language_config(
    selection_store: ActionLanguagePackSelectionStore,
    *,
    app_config_path: str | Path = "config/config.yaml",
    actions_path: str | Path = "config/actions.yaml",
    shortcuts_path: str | Path = "config/shortcuts.yaml",
    output_profiles_path: str | Path = "config/output_profiles.yaml",
    entry_panel_path: str | Path = "config/entry_panel.yaml",
) -> ActionLanguageBootstrapResult:
    config_dir = Path(actions_path).parent
    skeleton = load_feature_skeleton(
        config_dir,
        actions_path=actions_path,
        shortcuts_path=shortcuts_path,
        output_profiles_path=output_profiles_path,
    )
    loader = ActionLanguagePackLoader(config_dir, skeleton)
    registry = loader.load_registry()
    default_entry = registry.entry(registry.default_pack_id)

    # The default is the fail-closed recovery boundary and must be valid first.
    default_pack = loader.load(default_entry)
    valid: dict[str, CompiledActionLanguagePack] = {
        default_entry.pack_id: default_pack,
    }
    invalid: dict[str, ActionLanguagePackErrorCode] = {}
    diagnostics: list[str] = []
    for entry in registry.packs:
        if entry.pack_id == default_entry.pack_id:
            continue
        try:
            valid[entry.pack_id] = loader.load(entry)
        except ActionLanguagePackError as exc:
            invalid[entry.pack_id] = exc.reason
            diagnostics.append(
                f"action_language_pack.{entry.pack_id}.{exc.reason}"
            )

    selection = selection_store.load()
    if selection.diagnostic_code:
        diagnostics.append(selection.diagnostic_code)
    requested_pack_id = selection.selected_pack_id or registry.default_pack_id
    recovery: ActionLanguagePackRecovery | None = None
    active = valid.get(requested_pack_id)
    if active is None:
        active = default_pack
        reason = invalid.get(requested_pack_id, "pack_missing")
        recovery = ActionLanguagePackRecovery(
            requested_pack_id=requested_pack_id,
            reason=reason,
            diagnostic_code=f"action_language_pack.{reason}",
        )
        diagnostics.append(recovery.diagnostic_code)

    state = ActionLanguagePackSelectionState(
        available_packs=tuple(pack.descriptor for pack in valid.values()),
        active_pack=active.provenance.identity,
        selected_pack_id=requested_pack_id,
        recovery=recovery,
    )
    bundle = load_config_bundle(
        app_config_path=app_config_path,
        actions_path=actions_path,
        shortcuts_path=shortcuts_path,
        output_profiles_path=output_profiles_path,
        entry_panel_path=entry_panel_path,
        action_language_pack=active,
    )
    return ActionLanguageBootstrapResult(
        bundle=bundle,
        state=state,
        selection_backend=AppActionLanguageSelectionBackend(
            loader,
            registry,
            selection_store,
        ),
        diagnostic_codes=tuple(diagnostics),
    )
