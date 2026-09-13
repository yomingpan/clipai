from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import re

from ClipAI.core.application_paths import ApplicationPaths


_INSTANCE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def build_application_paths(
    application_root: str | Path,
    environment: Mapping[str, str],
) -> ApplicationPaths:
    """Resolve source-compatible paths; managed hosts inject a shared root."""
    app_root = Path(application_root).resolve()
    instance_name = environment.get("CLIPAI_INSTANCE_NAME", "default").strip()
    _validate_instance_name(instance_name)

    configured_shared = environment.get("CLIPAI_SHARED_ROOT", "").strip()
    if configured_shared:
        configured_shared_root = Path(configured_shared)
        if not configured_shared_root.is_absolute():
            raise ValueError("CLIPAI_SHARED_ROOT must be absolute")
        shared_root = configured_shared_root.resolve()
        if shared_root == app_root or shared_root.is_relative_to(app_root):
            raise ValueError("CLIPAI_SHARED_ROOT must be outside the application root")
        if instance_name != "default":
            shared_root = shared_root / "instances" / instance_name
        return _managed_paths(app_root, shared_root, instance_name)
    else:
        state_root = app_root / "data"
        secrets_file = app_root / ".env"
        logs_root = app_root / "logs"
        diagnostics_root = app_root / "diagnostics"
        update_root = state_root / "update"
        local_app_data = Path(
            environment.get("LOCALAPPDATA") or app_root / "AppData" / "Local"
        ).resolve()
        recent_actions_file = local_app_data / "ClipAI" / "recent_actions.json"

    return ApplicationPaths(
        application_root=app_root,
        config_root=app_root / "config",
        state_root=state_root,
        secrets_file=secrets_file,
        logs_root=logs_root,
        diagnostics_root=diagnostics_root,
        update_root=update_root,
        recent_actions_file=recent_actions_file,
        instance_name=instance_name,
    )


def build_managed_application_paths(
    application_root: str | Path,
    shared_root: str | Path,
    *,
    instance_name: str,
) -> ApplicationPaths:
    """Build runtime paths from an already resolved managed-instance root."""
    app_root = Path(application_root).resolve()
    shared = Path(shared_root)
    _validate_instance_name(instance_name)
    if not shared.is_absolute():
        raise ValueError("managed shared root must be absolute")
    shared = shared.resolve()
    if shared == app_root or shared.is_relative_to(app_root):
        raise ValueError("managed shared root must be outside the application root")
    return _managed_paths(app_root, shared, instance_name)


def _managed_paths(app_root: Path, shared_root: Path, instance_name: str) -> ApplicationPaths:
    state_root = shared_root / "state"
    return ApplicationPaths(
        application_root=app_root,
        config_root=app_root / "config",
        state_root=state_root,
        secrets_file=shared_root / "secrets" / ".env",
        logs_root=shared_root / "logs",
        diagnostics_root=shared_root / "diagnostics",
        update_root=shared_root / "update",
        recent_actions_file=state_root / "recent_actions.json",
        instance_name=instance_name,
    )


def _validate_instance_name(instance_name: str) -> None:
    if _INSTANCE_NAME.fullmatch(instance_name) is None:
        raise ValueError("CLIPAI_INSTANCE_NAME is invalid")


def resolve_runtime_file(configured_path: str | Path, root: Path, legacy_dir: str) -> Path:
    """Map a legacy relative category path into its injected owner root."""
    configured = Path(configured_path)
    if configured.is_absolute():
        return configured
    parts = configured.parts
    if parts and parts[0].casefold() == legacy_dir.casefold():
        configured = Path(*parts[1:])
    return root / configured
