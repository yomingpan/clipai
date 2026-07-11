from __future__ import annotations

from ClipAI.app.config_schema import ProviderCatalog
from ClipAI.core.models import ReadinessIssue
from ClipAI.providers.settings import ProviderCredential


def assess_provider_readiness(
    providers: ProviderCatalog,
    credential: ProviderCredential | None,
) -> tuple[ReadinessIssue, ...]:
    """Return non-fatal readiness issues for the selected provider."""
    if providers.active == "fake":
        return ()
    settings = providers.active_settings()
    assert settings is not None
    if credential is not None and credential.value:
        return ()
    return (
        ReadinessIssue(
            code="provider.missing_api_key",
            feature="llm",
            message=f"Set {settings.api_key_env} and restart ClipAI to use {providers.active}.",
        ),
    )
