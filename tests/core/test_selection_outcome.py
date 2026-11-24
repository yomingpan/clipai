import pytest

from ClipAI.core.models import (
    SelectionCaptureOutcome, SelectionGuidanceCategory, SelectionOutcomeClass,
    SelectionReason, selection_guidance_category,
)


def test_only_modifier_timeout_requires_modifier_release():
    for reason in SelectionReason:
        outcome = SelectionCaptureOutcome(reason=reason.value)
        expected = reason is SelectionReason.MODIFIER_TIMEOUT
        assert outcome.needs_modifier_release is expected
        assert outcome.classification is (
            SelectionOutcomeClass.NEEDS_MODIFIER_RELEASE if expected
            else SelectionOutcomeClass.UNRESOLVED
        )


@pytest.mark.parametrize('reason', ['uia_unsupported', 'uia_timeout', 'source_changed', 'copy_empty', ''])
def test_unresolved_is_not_modifier_release(reason):
    assert SelectionCaptureOutcome(reason=reason).classification is SelectionOutcomeClass.UNRESOLVED


def test_every_reason_has_guidance():
    from ClipAI.core.models import _REASON_GUIDANCE
    assert set(_REASON_GUIDANCE) == set(SelectionReason)
    assert all(isinstance(value, SelectionGuidanceCategory) for value in _REASON_GUIDANCE.values())


@pytest.mark.parametrize('reason', ['uia_text_failed', 'uia_provider_failed', 'uia_focus_restore_failed'])
def test_worker_failures_are_engine_guidance(reason):
    assert selection_guidance_category(reason) is SelectionGuidanceCategory.ENGINE


@pytest.mark.parametrize('reason', ['', 'something_new'])
def test_unknown_reason_has_no_selection_guidance(reason):
    assert selection_guidance_category(reason) is SelectionGuidanceCategory.NO_SELECTION


def test_status_takes_precedence_over_diagnostic_reason():
    assert SelectionCaptureOutcome('text', 'selected', reason='modifier_timeout').classification is SelectionOutcomeClass.SELECTED
    assert SelectionCaptureOutcome(status='cancelled', reason='modifier_timeout').classification is SelectionOutcomeClass.CANCELLED
