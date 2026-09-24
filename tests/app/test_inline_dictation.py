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


def test_raw_inline_dictation_pastes_without_provider():
    provider = ProviderExecution()
    pasted = []
    coordinator = InlineDictationCoordinator(
        provider_execution=provider, executor=None, refine_action=None,
        binding=lambda: None, paste=lambda text, target: pasted.append((text, target)),
        on_refine_settled=lambda _workflow_id: None,
    )

    coordinator.submit("spoken words", TARGET, refine=False)

    assert pasted == [("spoken words", TARGET)]
    assert provider.work is None


def test_unavailable_refinement_preserves_original_dictation():
    pasted = []
    coordinator = InlineDictationCoordinator(
        provider_execution=ProviderExecution(), executor=None, refine_action=None,
        binding=lambda: None, paste=lambda text, target: pasted.append((text, target)),
        on_refine_settled=lambda _workflow_id: None,
    )

    coordinator.submit("spoken words", TARGET, refine=True)

    assert pasted == [("spoken words", TARGET)]


def test_refinement_failure_pastes_original_and_settles_after_callback():
    provider = ProviderExecution()
    pasted, settled = [], []
    coordinator = InlineDictationCoordinator(
        provider_execution=provider, executor=object(), refine_action=object(),
        binding=lambda: object(), paste=lambda text, target: pasted.append((text, target)),
        on_refine_settled=lambda _workflow_id: settled.append(True),
    )

    coordinator.submit("spoken words", TARGET, refine=True)
    assert pasted == []
    assert settled == []
    provider.failure(RuntimeError("offline"))

    assert pasted == [("spoken words", TARGET)]
    assert settled == [True]


def test_refinement_success_pastes_processed_text_once():
    provider = ProviderExecution()
    pasted, settled = [], []
    coordinator = InlineDictationCoordinator(
        provider_execution=provider, executor=object(), refine_action=object(),
        binding=lambda: object(), paste=lambda text, target: pasted.append((text, target)),
        on_refine_settled=lambda _workflow_id: settled.append(True),
    )

    coordinator.submit("spoken words", TARGET, refine=True)
    provider.success("polished words")

    assert pasted == [("polished words", TARGET)]
    assert settled == [True]
