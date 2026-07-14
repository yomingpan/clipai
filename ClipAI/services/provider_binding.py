from __future__ import annotations

from dataclasses import dataclass

from ClipAI.core.models import ReadinessIssue
from ClipAI.core.ports import LLMProvider


@dataclass(frozen=True)
class ProviderExecutionBinding:
    """Provider dependencies captured when a workflow is created."""

    provider: LLMProvider
    provider_id: str
    model: str
    readiness_issues: tuple[ReadinessIssue, ...] = ()
