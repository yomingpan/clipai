from __future__ import annotations

from ClipAI.app.runtime_recipe_improvement import RecipeImprovementRuntimeModule
from ClipAI.core.commands import (
    ApplyRecipeCandidate,
    BeginRecipeImprovement,
    GenerateRecipeCandidate,
    OpenRecipeImprovement,
    RetryFailedRecipeTests,
    RunRecipeCandidateTests,
    SetRecipeComparisonVerdict,
)
from ClipAI.core.models import (
    LLMRequest,
    LLMResult,
    RecipeCandidateProposal,
    RecipeImprovementOverview,
    RecipeManualTestCase,
    RecipePromptCandidate,
    RecipeRevision,
    ResolvedAction,
)
from ClipAI.providers.fake import FakeProvider
from ClipAI.services.provider_binding import ProviderExecutionBinding


class FakeEvidenceService:
    def __init__(self, overview: RecipeImprovementOverview) -> None:
        self.value = overview
        self.calls = 0

    def overview(self) -> RecipeImprovementOverview:
        self.calls += 1
        return self.value

    def action(self, action_id, press_type):
        return ResolvedAction(
            action_id,
            "Rewrite",
            "system",
            "{input}",
            press_type,
            "selection_or_clipboard",
            "popup",
            0.1,
            version_id="v1",
        )

    def evidence(self, action_id, press_type):
        return ()

    def selected_records(self, action_id, press_type, feedback_ids):
        return ()


class RecordingPresenter:
    def __init__(self) -> None:
        self.shown = []

    def show_recipe_improvement(self, state) -> None:
        self.shown.append(state)

    def set_recipe_improvement(self, state) -> None:
        self.shown.append(state)


class RecordingSupervisor:
    def __init__(self) -> None:
        self.work = {}
        self.cancelled = []

    def submit(self, operation_id, work, on_error) -> None:
        self.work[operation_id] = work

    def cancel(self, operation_id) -> None:
        self.cancelled.append(operation_id)


class FakeCandidateService:
    def build_request(self, action, evidence, *, directions, user_direction, model):
        return LLMRequest((), model, 0.1)

    def parse_proposal(self, action, result, *, iteration):
        return RecipeCandidateProposal(
            "prompt",
            "更清楚。",
            RecipePromptCandidate(
                action.id,
                action.press_type,
                action.version_id,
                iteration,
                "new system",
                "new {input}",
                "更清楚。",
                result.provider,
                result.model,
            ),
        )


class CompletingProvider(FakeProvider):
    def complete(self, request, cancellation):
        return LLMResult("{}", "openai", request.model)


class FailFourthCompletionProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__()
        self.completion_count = 0

    def complete(self, request, cancellation):
        self.completion_count += 1
        if self.completion_count == 4:
            raise RuntimeError("temporary provider failure")
        return LLMResult(
            f"result-{self.completion_count}",
            "openai",
            request.model,
        )


class FakeRevisions:
    def __init__(self) -> None:
        self.applied = []

    def apply(self, candidate, validation_summary):
        self.applied.append((candidate, validation_summary))
        return RecipeRevision(
            "revision-1",
            candidate.action_id,
            candidate.press_type,
            candidate.parent_version,
            "v2",
            "2026-07-27T00:00:00+00:00",
            candidate.system_prompt,
            candidate.prompt,
            validation_summary,
        )


def test_open_recipe_improvement_reads_fresh_evidence_and_presents_it() -> None:
    overview = RecipeImprovementOverview(())
    evidence = FakeEvidenceService(overview)
    presenter = RecordingPresenter()
    module = RecipeImprovementRuntimeModule(evidence, presenter)

    module.handle(OpenRecipeImprovement())

    assert evidence.calls == 1
    assert presenter.shown[0].stage == "overview"
    assert presenter.shown[0].overview == overview


def test_begin_captures_provider_and_requires_explicit_privacy_consent() -> None:
    presenter = RecordingPresenter()
    module = RecipeImprovementRuntimeModule(
        FakeEvidenceService(RecipeImprovementOverview(())),
        presenter,
        binding_reader=lambda: ProviderExecutionBinding(
            CompletingProvider(), "openai", "gpt-current"
        ),
    )

    module.handle(BeginRecipeImprovement("rewrite", "short"))
    module.handle(
        GenerateRecipeCandidate(
            selected_feedback_ids=(),
            directions=("更清楚",),
            user_direction="保留結論",
            privacy_consent=False,
            operation_id="generate-1",
        )
    )

    assert presenter.shown[-2].provider == "openai"
    assert presenter.shown[-2].model == "gpt-current"
    assert presenter.shown[-1].stage == "evidence"
    assert "同意" in presenter.shown[-1].message


def test_generation_projects_pending_then_candidate_for_same_operation() -> None:
    presenter = RecordingPresenter()
    supervisor = RecordingSupervisor()
    queued = []
    module = RecipeImprovementRuntimeModule(
        FakeEvidenceService(RecipeImprovementOverview(())),
        presenter,
        binding_reader=lambda: ProviderExecutionBinding(
            CompletingProvider(), "openai", "gpt-current"
        ),
        candidate_service=FakeCandidateService(),
        supervisor=supervisor,
        enqueue=queued.append,
    )
    module.handle(BeginRecipeImprovement("rewrite", "short"))

    module.handle(
        GenerateRecipeCandidate(
            selected_feedback_ids=(),
            directions=("更清楚",),
            user_direction="保留結論",
            privacy_consent=True,
            operation_id="generate-1",
        )
    )

    pending = presenter.shown[-1]
    assert pending.stage == "generating"
    assert pending.request_count == 1
    assert pending.provider == "openai"
    assert pending.model == "gpt-current"
    supervisor.work["generate-1"]()
    module.handle(queued.pop())
    assert presenter.shown[-1].stage == "candidate"
    assert presenter.shown[-1].candidate.prompt == "new {input}"


def test_manual_comparison_runs_sequentially_and_clear_win_hot_applies() -> None:
    presenter = RecordingPresenter()
    supervisor = RecordingSupervisor()
    queued = []
    revisions = FakeRevisions()
    module = RecipeImprovementRuntimeModule(
        FakeEvidenceService(RecipeImprovementOverview(())),
        presenter,
        binding_reader=lambda: ProviderExecutionBinding(
            CompletingProvider(), "openai", "gpt-current"
        ),
        candidate_service=FakeCandidateService(),
        supervisor=supervisor,
        enqueue=queued.append,
        revisions=revisions,
    )
    module.handle(BeginRecipeImprovement("rewrite", "short"))
    module.handle(
        GenerateRecipeCandidate((), ("更清楚",), "保留結論", True, "generate-1")
    )
    supervisor.work["generate-1"]()
    module.handle(queued.pop())

    module.handle(
        RunRecipeCandidateTests(
            (),
            (RecipeManualTestCase("manual-1", "input", "保留結論"),),
            "test-1",
        )
    )

    assert presenter.shown[-1].stage == "testing"
    assert presenter.shown[-1].request_count == 2
    supervisor.work["test-1"]()
    while queued:
        module.handle(queued.pop(0))
    assert presenter.shown[-1].stage == "review"
    assert len(presenter.shown[-1].comparisons) == 1
    candidate = presenter.shown[-1].candidate
    module.handle(
        SetRecipeComparisonVerdict(
            "manual-1",
            "candidate_better",
            candidate.parent_version,
            candidate.iteration,
        )
    )
    assert presenter.shown[-1].apply_gate.mode == "direct"
    module.handle(
        ApplyRecipeCandidate(
            False,
            "apply-1",
            candidate.parent_version,
            candidate.iteration,
        )
    )
    assert presenter.shown[-2].stage == "applying"
    assert presenter.shown[-2].operation_id == "apply-1"
    assert presenter.shown[-1].stage == "applied"
    assert "不需要重新啟動" in presenter.shown[-1].message
    assert revisions.applied[0][1] == "1／1 個比較偏好新版本"


def test_each_action_variant_keeps_its_own_in_memory_draft() -> None:
    presenter = RecordingPresenter()
    module = RecipeImprovementRuntimeModule(
        FakeEvidenceService(RecipeImprovementOverview(())),
        presenter,
        binding_reader=lambda: ProviderExecutionBinding(
            CompletingProvider(), "openai", "gpt-current"
        ),
    )
    module.handle(BeginRecipeImprovement("rewrite", "short"))
    module.handle(
        GenerateRecipeCandidate(
            (),
            ("更清楚",),
            "short draft",
            False,
            "short-generate",
        )
    )
    module.handle(OpenRecipeImprovement())
    module.handle(BeginRecipeImprovement("rewrite", "long"))
    module.handle(
        GenerateRecipeCandidate(
            (),
            ("保留更多細節",),
            "long draft",
            False,
            "long-generate",
        )
    )
    module.handle(OpenRecipeImprovement())

    module.handle(BeginRecipeImprovement("rewrite", "short"))

    assert presenter.shown[-1].press_type == "short"
    assert presenter.shown[-1].user_direction == "short draft"
    assert presenter.shown[-1].directions == ("更清楚",)


def test_retry_failed_tests_preserves_previous_successful_comparisons() -> None:
    presenter = RecordingPresenter()
    supervisor = RecordingSupervisor()
    queued = []
    provider = FailFourthCompletionProvider()
    module = RecipeImprovementRuntimeModule(
        FakeEvidenceService(RecipeImprovementOverview(())),
        presenter,
        binding_reader=lambda: ProviderExecutionBinding(
            provider, "openai", "gpt-current"
        ),
        candidate_service=FakeCandidateService(),
        supervisor=supervisor,
        enqueue=queued.append,
    )
    module.handle(BeginRecipeImprovement("rewrite", "short"))
    module.handle(
        GenerateRecipeCandidate((), ("更清楚",), "", True, "generate-1")
    )
    supervisor.work["generate-1"]()
    module.handle(queued.pop())
    module.handle(
        RunRecipeCandidateTests(
            (),
            (
                RecipeManualTestCase("manual-1", "first", "保留結論"),
                RecipeManualTestCase("manual-2", "second", "不要冗長"),
            ),
            "test-1",
        )
    )
    supervisor.work["test-1"]()
    while queued:
        module.handle(queued.pop(0))

    first_review = presenter.shown[-1]
    assert tuple(item.test_id for item in first_review.comparisons) == (
        "manual-1",
        "manual-2",
    )
    assert not first_review.comparisons[0].error
    assert first_review.comparisons[1].error

    module.handle(RetryFailedRecipeTests("retry-1"))
    supervisor.work["retry-1"]()
    while queued:
        module.handle(queued.pop(0))

    final_review = presenter.shown[-1]
    assert final_review.stage == "review"
    assert tuple(item.test_id for item in final_review.comparisons) == (
        "manual-1",
        "manual-2",
    )
    assert all(not item.error for item in final_review.comparisons)


def test_candidate_is_rejected_before_testing_when_real_request_cannot_build() -> None:
    presenter = RecordingPresenter()
    supervisor = RecordingSupervisor()
    queued = []

    def reject_request(_action, _input_text, _model):
        raise ValueError("output profile is invalid")

    module = RecipeImprovementRuntimeModule(
        FakeEvidenceService(RecipeImprovementOverview(())),
        presenter,
        binding_reader=lambda: ProviderExecutionBinding(
            CompletingProvider(), "openai", "gpt-current"
        ),
        candidate_service=FakeCandidateService(),
        supervisor=supervisor,
        enqueue=queued.append,
        request_builder=reject_request,
    )
    module.handle(BeginRecipeImprovement("rewrite", "short"))
    module.handle(
        GenerateRecipeCandidate((), ("更清楚",), "", True, "generate-1")
    )
    supervisor.work["generate-1"]()
    module.handle(queued.pop())

    assert presenter.shown[-1].stage == "error"
    assert "無法建立有效請求" in presenter.shown[-1].message
    assert presenter.shown[-1].candidate is None
