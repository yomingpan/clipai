from __future__ import annotations

from ClipAI.app.inline_dictation import InlineDictationCoordinator
from ClipAI.core.models import PasteTarget


TARGET = PasteTarget("hwnd:1", 1, "Editor", "private", 1)


class ProviderExecution:
    def __init__(self):
        self.work = None
        self.success = None
        self.failure = None
        self.cancelled = None

    def start(self, _operation_id, work, success, failure, cancelled):
        self.work, self.success, self.failure, self.cancelled = work, success, failure, cancelled

    def cancel(self, _operation_id):
        return True


def test_raw_inline_dictation_pastes_without_provider():
    provider = ProviderExecution()
    pasted = []
    coordinator = InlineDictationCoordinator(
        provider_execution=provider, executor=None, refine_action=None,
        binding=lambda: None, paste=lambda text, target, _interaction_id, _operation_id: pasted.append((text, target)),
        on_refine_settled=lambda *_args: None,
    )

    coordinator.submit("spoken words", TARGET, refine=False, operation_id="paste-1")

    assert pasted == [("spoken words", TARGET)]
    assert provider.work is None


def test_unavailable_refinement_preserves_original_dictation_without_pasting():
    pasted, settled = [], []
    coordinator = InlineDictationCoordinator(
        provider_execution=ProviderExecution(), executor=None, refine_action=None,
        binding=lambda: None, paste=lambda text, target, _interaction_id, _operation_id: pasted.append((text, target)),
        on_refine_settled=lambda *args: settled.append(args),
    )

    assert not coordinator.submit("spoken words", TARGET, refine=True, operation_id="refine-1")

    assert pasted == []
    assert settled == [("", "refine-1", "", True)]


def test_refinement_failure_requires_explicit_recovery_before_paste():
    provider = ProviderExecution()
    pasted, settled = [], []
    coordinator = InlineDictationCoordinator(
        provider_execution=provider, executor=object(), refine_action=object(),
        binding=lambda: object(), paste=lambda text, target, _interaction_id, _operation_id: pasted.append((text, target)),
        on_refine_settled=lambda *args: settled.append(args),
    )

    assert coordinator.submit("spoken words", TARGET, refine=True, operation_id="refine-1")
    assert pasted == []
    assert settled == []
    provider.failure(RuntimeError("offline"))

    assert pasted == []
    assert settled == [("", "refine-1", "", True)]


def test_refinement_success_returns_processed_text_without_direct_paste():
    provider = ProviderExecution()
    pasted, settled = [], []
    coordinator = InlineDictationCoordinator(
        provider_execution=provider, executor=object(), refine_action=object(),
        binding=lambda: object(), paste=lambda text, target, _interaction_id, _operation_id: pasted.append((text, target)),
        on_refine_settled=lambda *args: settled.append(args),
    )

    coordinator.submit("spoken words", TARGET, refine=True, operation_id="refine-1")
    provider.success("polished words")

    assert pasted == []
    assert settled == [("", "refine-1", "polished words", False)]


def test_empty_refinement_result_never_uses_raw_text_as_automatic_fallback():
    provider = ProviderExecution()
    pasted, settled = [], []
    coordinator = InlineDictationCoordinator(
        provider_execution=provider, executor=object(), refine_action=object(),
        binding=lambda: object(), paste=lambda text, target, _interaction_id, _operation_id: pasted.append((text, target)),
        on_refine_settled=lambda *args: settled.append(args),
    )
    coordinator.submit("spoken words", TARGET, refine=True, interaction_id="inline-1", operation_id="refine-1")
    provider.success("   ")
    assert pasted == []
    assert settled == [("inline-1", "refine-1", "   ", True)]


def test_refinement_binding_failure_settles_without_claiming_provider_admission():
    provider = ProviderExecution()
    settled = []

    def unavailable_binding():
        raise OSError("provider settings unavailable")

    coordinator = InlineDictationCoordinator(
        provider_execution=provider, executor=object(), refine_action=object(),
        binding=unavailable_binding,
        paste=lambda *_args: raise_unexpected_paste(),
        on_refine_settled=lambda *args: settled.append(args),
    )

    assert not coordinator.submit("spoken words", TARGET, refine=True, interaction_id="inline-1", operation_id="refine-1")
    assert provider.work is None
    assert settled == [("inline-1", "refine-1", "", True)]


def raise_unexpected_paste() -> None:
    raise AssertionError("refinement failure must not paste")
