from dataclasses import replace

import pytest

from ClipAI.core.models import (
    ActionDefinition,
    ActionLanguagePackIdentity,
    ActionLanguageProvenance,
    ActionVersionContext,
    OutputProfile,
)
from ClipAI.services.action_catalog import ActionCatalog


def _action(*, name: str = "Explain") -> ActionDefinition:
    return ActionDefinition(
        id="explain",
        name=name,
        system_prompt="Explain faithfully.",
        prompt="Explain: {input}",
        press_variants={},
        output_profile="structured",
    )


def _context(
    *,
    pack_version: str = "1.0.0",
    profile_instruction: str = "Use sections.",
) -> ActionVersionContext:
    return ActionVersionContext(
        provenance=ActionLanguageProvenance(
            identity=ActionLanguagePackIdentity(
                pack_id="en-US",
                pack_version=pack_version,
                locale="en-US",
            ),
            feature_contract_hash="sha256:contract",
            resource_content_hash="sha256:resources",
        ),
        output_profiles=(
            OutputProfile(
                id="structured",
                instruction=profile_instruction,
                required_markers=("## Result",),
                presentation="markdown_sections",
            ),
        ),
    )


def _version(
    action: ActionDefinition | None = None,
    context: ActionVersionContext | None = None,
) -> str:
    return ActionCatalog(
        [action or _action()],
        version_context=context or _context(),
    ).resolve("explain", "short").version_id


def test_resolved_action_carries_typed_pack_provenance() -> None:
    context = _context()

    resolved = ActionCatalog(
        [_action()],
        version_context=context,
    ).resolve("explain", "short")

    assert resolved.action_language == context.provenance


@pytest.mark.parametrize(
    ("action", "context"),
    (
        (_action(name="Explain clearly"), _context()),
        (_action(), _context(profile_instruction="Use concise sections.")),
        (_action(), _context(pack_version="1.0.1")),
    ),
)
def test_version_changes_for_name_profile_or_pack_identity(
    action: ActionDefinition,
    context: ActionVersionContext,
) -> None:
    assert _version(action, context) != _version()


def test_version_changes_for_profile_markers_and_resource_hash() -> None:
    context = _context()
    profile = replace(context.output_profiles[0], required_markers=("## Answer",))
    marker_context = replace(context, output_profiles=(profile,))
    hash_context = replace(
        context,
        provenance=replace(
            context.provenance,
            resource_content_hash="sha256:changed",
        ),
    )

    assert _version(context=marker_context) != _version()
    assert _version(context=hash_context) != _version()


def test_version_context_rejects_unknown_effective_profile() -> None:
    with pytest.raises(ValueError, match="unknown version profile"):
        ActionCatalog(
            [_action()],
            version_context=replace(_context(), output_profiles=()),
        ).resolve("explain", "short")
