from __future__ import annotations

from dataclasses import dataclass

from ClipAI.core.models import ProviderOption, ReadinessIssue
from ClipAI.core.ports import LLMProvider


@dataclass(frozen=True)
class ProviderExecutionBinding:
    """Provider dependencies captured when a workflow is created."""

    provider: LLMProvider
    provider_id: str
    model: str
    readiness_issues: tuple[ReadinessIssue, ...] = ()


@dataclass(frozen=True)
class ProviderRuntimeSnapshot:
    active_provider: str
    bindings: tuple[ProviderExecutionBinding, ...]
    options: tuple[ProviderOption, ...]
    gateway_name: str = ""
    gateway_base_url: str = ""
