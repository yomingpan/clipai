from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Literal, Protocol, TypeAlias, cast

from ClipAI.app.task_supervisor import TaskSupervisor
from ClipAI.core.commands import (
    BeginRecipeImprovement,
    ApplyRecipeCandidate,
    CancelRecipeImprovementOperation,
    GenerateRecipeCandidate,
    KeepPersonalRecipeVersion,
    OpenRecipeImprovement,
    OpenRecipeVersionHistory,
    RecipeCandidateCompleted,
    RecipeTestProgress,
    RecipeTestsCompleted,
    RefineRecipeCandidate,
    ReturnToRecipeCandidate,
    RetryFailedRecipeTests,
    RunRecipeCandidateTests,
    RestoreRecipeVersion,
    SetRecipeComparisonVerdict,
    TreatRecipeIssueAsPrompt,
)
from ClipAI.core.models import (
    ActionFeedbackRecord,
    LLMMessage,
    LLMRequest,
    LLMResult,
    PressType,
    PresentationDocument,
    RecipeComparisonResult,
    RecipeComparisonVerdict,
    RecipeEvidenceItem,
    RecipeImprovementOverview,
    RecipeImprovementState,
    ResolvedAction,
)
from ClipAI.core.ports import (
    OperationHandle,
    OperationTracker,
    RecipeImprovementPresenter,
    UserNotifier,
)
from ClipAI.core.state import CancellationToken
from ClipAI.services.provider_binding import ProviderExecutionBinding
from ClipAI.services.recipe_candidate import RecipeCandidateService
from ClipAI.services.recipe_comparison import RecipeComparisonPolicy
from ClipAI.services.recipe_revisions import RecipeRevisionCoordinator


RecipeImprovementRuntimeCommand: TypeAlias = (
    OpenRecipeImprovement
    | BeginRecipeImprovement
    | GenerateRecipeCandidate
    | RecipeCandidateCompleted
    | RunRecipeCandidateTests
    | RecipeTestProgress
    | RecipeTestsCompleted
    | SetRecipeComparisonVerdict
    | ApplyRecipeCandidate
    | CancelRecipeImprovementOperation
    | OpenRecipeVersionHistory
    | RestoreRecipeVersion
    | KeepPersonalRecipeVersion
    | RefineRecipeCandidate
    | ReturnToRecipeCandidate
    | TreatRecipeIssueAsPrompt
    | RetryFailedRecipeTests
)


class RecipeImprovementEvidence(Protocol):
    def overview(self) -> RecipeImprovementOverview: ...

    def action(self, action_id: str, press_type: PressType) -> ResolvedAction: ...

    def evidence(
        self,
        action_id: str,
        press_type: PressType,
    ) -> tuple[RecipeEvidenceItem, ...]: ...

    def selected_records(
        self,
        action_id: str,
        press_type: PressType,
        feedback_ids: tuple[str, ...],
    ) -> tuple[ActionFeedbackRecord, ...]: ...


@dataclass(frozen=True)
class _RecipeDraft:
    state: RecipeImprovementState
    action: ResolvedAction
    binding: ProviderExecutionBinding | None


class RecipeImprovementRuntimeModule:
    def __init__(
        self,
        evidence: RecipeImprovementEvidence,
        presenter: RecipeImprovementPresenter,
        *,
        binding_reader: Callable[[], ProviderExecutionBinding] | None = None,
        candidate_service: RecipeCandidateService | None = None,
        supervisor: TaskSupervisor | None = None,
        enqueue: Callable[[object], None] | None = None,
        request_builder: Callable[[ResolvedAction, str, str], LLMRequest] | None = None,
        revisions: RecipeRevisionCoordinator | None = None,
        comparison_policy: RecipeComparisonPolicy | None = None,
        revision_warning: str = "",
        notifier: UserNotifier | None = None,
        operation_tracker: OperationTracker | None = None,
        presentation_builder: Callable[
            [ResolvedAction, str],
            PresentationDocument | None,
        ]
        | None = None,
    ) -> None:
        self._evidence = evidence
        self._presenter = presenter
        self._binding_reader = binding_reader
        self._candidate_service = candidate_service or RecipeCandidateService()
        self._supervisor = supervisor
        self._enqueue = enqueue or (lambda _command: None)
        self._request_builder = request_builder or self._build_test_request
        self._revisions = revisions
        self._comparison_policy = comparison_policy or RecipeComparisonPolicy()
        self._revision_warning = revision_warning
        self._notifier = notifier
        self._operation_tracker = operation_tracker
        self._operation_handle: OperationHandle | None = None
        self._presentation_builder = presentation_builder or (
            lambda _action, _text: None
        )
        self._state: RecipeImprovementState | None = None
        self._action: ResolvedAction | None = None
        self._binding: ProviderExecutionBinding | None = None
        self._cancellation: CancellationToken | None = None
        self._privacy_confirmed = False
        self._reminded_versions: set[str] = set()
        self._force_prompt_issue = False
        self._drafts: dict[tuple[str, PressType], _RecipeDraft] = {}
        self._last_test_command: RunRecipeCandidateTests | None = None
        self._retry_preserved: tuple[RecipeComparisonResult, ...] = ()
        self._retry_order: tuple[str, ...] = ()

    @property
    def state(self) -> RecipeImprovementState | None:
        return self._state

    def start(self) -> None:
        if self._notifier is None:
            return
        due = tuple(
            item
            for item in self._evidence.overview().variants
            if item.reminder_recommended
            and item.current_version not in self._reminded_versions
        )
        if not due:
            return
        self._reminded_versions.update(item.current_version for item in due)
        self._notifier.notify(
            "ClipAI",
            f"有 {len(due)} 個 Recipe 已累積足夠的調整案例，可以開始改善。",
        )

    def stop(self) -> None:
        state = self._state
        if (
            state is not None
            and state.stage in {"generating", "testing"}
            and state.operation_id
        ):
            self._cancel_operation(
                CancelRecipeImprovementOperation(state.operation_id)
            )

    def handle(self, command: RecipeImprovementRuntimeCommand) -> None:
        if isinstance(command, OpenRecipeImprovement):
            self._open()
        elif isinstance(command, BeginRecipeImprovement):
            self._begin(command)
        elif isinstance(command, GenerateRecipeCandidate):
            self._generate(command)
        elif isinstance(command, RecipeCandidateCompleted):
            self._complete_candidate(command)
        elif isinstance(command, RunRecipeCandidateTests):
            self._run_tests(command)
        elif isinstance(command, RecipeTestProgress):
            self._test_progress(command)
        elif isinstance(command, RecipeTestsCompleted):
            self._complete_tests(command)
        elif isinstance(command, SetRecipeComparisonVerdict):
            self._set_verdict(command)
        elif isinstance(command, ApplyRecipeCandidate):
            self._apply_candidate(command)
        elif isinstance(command, CancelRecipeImprovementOperation):
            self._cancel_operation(command)
        elif isinstance(command, OpenRecipeVersionHistory):
            self._open_history(command)
        elif isinstance(command, RestoreRecipeVersion):
            self._restore_version(command)
        elif isinstance(command, KeepPersonalRecipeVersion):
            self._keep_personal_version(command)
        elif isinstance(command, RefineRecipeCandidate):
            self._refine_candidate(command)
        elif isinstance(command, ReturnToRecipeCandidate):
            self._return_to_candidate(command)
        elif isinstance(command, TreatRecipeIssueAsPrompt):
            self._treat_issue_as_prompt(command)
        elif isinstance(command, RetryFailedRecipeTests):
            self._retry_failed_tests(command)

    def _open(self) -> None:
        if self._state is not None and self._state.stage in {
            "generating",
            "testing",
        }:
            self._presenter.show_recipe_improvement(self._state)
            return
        state = RecipeImprovementState(
            "overview",
            self._evidence.overview(),
            message=self._revision_warning,
        )
        self._state = state
        self._presenter.show_recipe_improvement(state)

    def _begin(self, command: BeginRecipeImprovement) -> None:
        if self._state is not None and self._state.stage in {
            "generating",
            "testing",
        }:
            self._set(replace(self._state, message="請先完成或取消目前的改善作業。"))
            return
        action = self._evidence.action(command.action_id, command.press_type)
        draft_key = (command.action_id, command.press_type)
        draft = self._drafts.get(draft_key)
        if draft is not None and draft.state.current_version == action.version_id:
            self._action = draft.action
            self._binding = draft.binding
            self._set(draft.state)
            return
        self._drafts.pop(draft_key, None)
        if action.input_mode == "clipboard_image":
            self._set(
                RecipeImprovementState(
                    "evidence",
                    self._evidence.overview(),
                    action_id=action.id,
                    press_type=action.press_type,
                    action_name=action.name,
                    current_version=action.version_id,
                    current_system_prompt=action.system_prompt,
                    current_prompt=action.prompt,
                    can_generate=False,
                    message="目前僅支援文字 Recipe",
                )
            )
            return
        binding = self._binding_reader() if self._binding_reader is not None else None
        self._action = action
        self._binding = binding
        configured = binding is not None and not binding.readiness_issues
        self._set(
            RecipeImprovementState(
                "evidence",
                self._evidence.overview(),
                action_id=action.id,
                press_type=action.press_type,
                action_name=action.name,
                current_version=action.version_id,
                current_system_prompt=action.system_prompt,
                current_prompt=action.prompt,
                provider=binding.provider_id if binding else "",
                model=binding.model if binding else "",
                evidence=tuple(self._evidence.evidence(action.id, action.press_type)),
                privacy_confirmation_required=not self._privacy_confirmed,
                can_generate=configured,
                message=(
                    ""
                    if configured
                    else "尚未設定可用的 AI Provider，請先開啟 Settings and Models。"
                ),
            )
        )

    def _generate(self, command: GenerateRecipeCandidate) -> None:
        state = self._state
        action = self._action
        binding = self._binding
        if state is None or state.stage not in {"evidence", "candidate", "error"}:
            return
        if not command.privacy_consent:
            self._set(
                replace(
                    state,
                    stage="evidence",
                    selected_feedback_ids=command.selected_feedback_ids,
                    directions=command.directions,
                    user_direction=command.user_direction.strip(),
                    message="請先同意傳送所選內容，或取消這次改善。",
                )
            )
            return
        if not state.can_generate or action is None or binding is None:
            self._set(replace(state, stage="evidence", message="目前沒有可用的 AI Provider。"))
            return
        if not command.operation_id or self._supervisor is None:
            self._set(replace(state, stage="error", message="無法啟動候選產生作業。"))
            return
        try:
            records = self._evidence.selected_records(
                action.id,
                action.press_type,
                command.selected_feedback_ids,
            )
            request = self._candidate_service.build_request(
                action,
                records,
                directions=(
                    *command.directions,
                    *(
                        ("使用者已確認這是 Prompt 問題，請提出 Prompt 候選。",)
                        if self._force_prompt_issue
                        else ()
                    ),
                ),
                user_direction=command.user_direction,
                model=binding.model,
            )
        except ValueError as exc:
            self._set(replace(state, stage="evidence", message=str(exc)))
            return
        cancellation = CancellationToken()
        self._privacy_confirmed = True
        self._cancellation = cancellation
        iteration = max(1, state.iteration + 1)
        self._set(
            replace(
                state,
                stage="generating",
                selected_feedback_ids=command.selected_feedback_ids,
                directions=command.directions,
                user_direction=command.user_direction.strip(),
                iteration=iteration,
                operation_id=command.operation_id,
                request_count=1,
                privacy_confirmation_required=False,
                message="正在產生改善建議…",
            )
        )
        if self._operation_tracker is not None:
            self._operation_handle = self._operation_tracker.start(
                command.operation_id,
                "llm",
            )

        def work() -> None:
            try:
                result = binding.provider.complete(request, cancellation)
                self._enqueue(RecipeCandidateCompleted(command.operation_id, result))
            except BaseException as exc:
                self._enqueue(RecipeCandidateCompleted(command.operation_id, error=str(exc)))

        self._supervisor.submit(
            command.operation_id,
            work,
            lambda error: self._enqueue(
                RecipeCandidateCompleted(command.operation_id, error=str(error))
            ),
        )

    def _complete_candidate(self, command: RecipeCandidateCompleted) -> None:
        state = self._state
        action = self._action
        if (
            state is None
            or state.stage != "generating"
            or state.operation_id != command.operation_id
            or action is None
        ):
            return
        self._cancellation = None
        if command.error or command.result is None:
            self._finish_operation("fail")
            self._set(
                replace(
                    state,
                    stage="error",
                    operation_id="",
                    message=command.error or "AI Provider 沒有回傳結果，請重試。",
                )
            )
            return
        try:
            proposal = self._candidate_service.parse_proposal(
                action,
                command.result,
                iteration=state.iteration,
            )
        except ValueError as exc:
            self._finish_operation("fail")
            self._set(replace(state, stage="error", operation_id="", message=str(exc)))
            return
        if proposal.candidate is None:
            self._finish_operation("succeed")
            label = (
                "這些回饋較像 App／介面問題。"
                if proposal.classification == "app_issue"
                else "目前證據不足或彼此衝突。"
            )
            self._set(
                replace(
                    state,
                    stage="evidence",
                    operation_id="",
                    suspected_app_issue=proposal.classification == "app_issue",
                    message=f"{label} {proposal.explanation}",
                )
            )
            return
        try:
            candidate_action = replace(
                action,
                system_prompt=proposal.candidate.system_prompt,
                prompt=proposal.candidate.prompt,
            )
            binding = self._binding
            if binding is None:
                raise ValueError("captured provider is no longer available")
            self._request_builder(
                candidate_action,
                "ClipAI request validation",
                binding.model,
            )
        except (KeyError, ValueError) as exc:
            self._finish_operation("fail")
            self._set(
                replace(
                    state,
                    stage="error",
                    operation_id="",
                    message=f"候選無法建立有效請求：{exc}",
                )
            )
            return
        self._finish_operation("succeed")
        self._force_prompt_issue = False
        self._set(
            replace(
                state,
                stage="candidate",
                candidate=proposal.candidate,
                operation_id="",
                suspected_app_issue=False,
                message=proposal.explanation,
            )
        )
        if self._notifier is not None:
            self._notifier.notify("ClipAI", "Recipe 改善建議已準備完成。")

    def _run_tests(self, command: RunRecipeCandidateTests) -> None:
        state = self._state
        action = self._action
        binding = self._binding
        if (
            state is None
            or state.stage != "candidate"
            or state.candidate is None
            or action is None
            or binding is None
            or self._supervisor is None
        ):
            return
        total = len(command.selected_feedback_ids) + len(command.manual_cases)
        self._last_test_command = command
        try:
            self._comparison_policy.validate_test_count(total)
            records = self._evidence.selected_records(
                action.id,
                action.press_type,
                command.selected_feedback_ids,
            )
        except ValueError as exc:
            self._set(replace(state, message=str(exc)))
            return
        saved_by_id = {record.feedback_id: record for record in records}
        importance_by_id = dict(command.saved_case_importance)
        if any(
            record.input_text is None or record.result_text is None
            for record in records
        ):
            self._set(replace(state, message="測試只能使用已保存內容的回饋案例。"))
            return
        candidate_action = replace(
            action,
            system_prompt=state.candidate.system_prompt,
            prompt=state.candidate.prompt,
        )
        cancellation = CancellationToken()
        self._cancellation = cancellation
        request_count = len(records) + 2 * len(command.manual_cases)
        self._set(
            replace(
                state,
                stage="testing",
                operation_id=command.operation_id,
                request_count=request_count,
                test_progress=f"正在測試 0／{total}",
                comparisons=(),
                message="測試會依序執行，你可以隨時取消。",
            )
        )
        if self._operation_tracker is not None:
            self._operation_handle = self._operation_tracker.start(
                command.operation_id,
                "llm",
            )

        def work() -> None:
            comparisons: list[RecipeComparisonResult] = []
            cases: list[tuple[str, str, str, str, bool, str]] = []
            for feedback_id in command.selected_feedback_ids:
                record = saved_by_id[feedback_id]
                cases.append(
                    (
                        feedback_id,
                        record.input_text or "",
                        record.result_text or "",
                        importance_by_id.get(feedback_id, record.note),
                        True,
                        (
                            f"原本實際結果（由 {record.provider}/{record.model} 產生）"
                            if (
                                record.provider != binding.provider_id
                                or record.model != binding.model
                            )
                            else "原本實際結果"
                        ),
                    )
                )
            cases.extend(
                (
                    case.test_id,
                    case.input_text,
                    "",
                    case.importance,
                    False,
                    "目前版本（本次重新產生，結果可能有變動）",
                )
                for case in command.manual_cases
            )
            for index, (
                test_id,
                input_text,
                baseline,
                importance,
                saved,
                baseline_label,
            ) in enumerate(
                cases, start=1
            ):
                if cancellation.is_cancelled:
                    return
                self._enqueue(RecipeTestProgress(command.operation_id, index, total))
                try:
                    if not saved:
                        baseline = binding.provider.complete(
                            self._request_builder(action, input_text, binding.model),
                            cancellation,
                        ).text
                    candidate_result = binding.provider.complete(
                        self._request_builder(
                            candidate_action,
                            input_text,
                            binding.model,
                        ),
                        cancellation,
                    ).text
                    comparisons.append(
                        RecipeComparisonResult(
                            test_id,
                            input_text,
                            baseline,
                            candidate_result,
                            importance,
                            baseline_label,
                            "候選版本",
                            current_presentation=self._presentation_builder(
                                action,
                                baseline,
                            ),
                            candidate_presentation=self._presentation_builder(
                                candidate_action,
                                candidate_result,
                            ),
                        )
                    )
                except BaseException as exc:
                    comparisons.append(
                        RecipeComparisonResult(
                            test_id,
                            input_text,
                            baseline,
                            "",
                            importance,
                            baseline_label,
                            "候選版本",
                            error=str(exc),
                        )
                    )
            self._enqueue(
                RecipeTestsCompleted(command.operation_id, tuple(comparisons))
            )

        self._supervisor.submit(
            command.operation_id,
            work,
            lambda error: self._enqueue(
                RecipeTestsCompleted(command.operation_id, error=str(error))
            ),
        )

    def _test_progress(self, command: RecipeTestProgress) -> None:
        state = self._state
        if (
            state is not None
            and state.stage == "testing"
            and state.operation_id == command.operation_id
        ):
            self._set(
                replace(
                    state,
                    test_progress=f"正在測試 {command.current}／{command.total}",
                )
            )

    def _complete_tests(self, command: RecipeTestsCompleted) -> None:
        state = self._state
        if (
            state is None
            or state.stage != "testing"
            or state.operation_id != command.operation_id
        ):
            return
        self._cancellation = None
        comparisons = command.comparisons
        if self._retry_order:
            retried = {item.test_id: item for item in comparisons}
            preserved = {
                item.test_id: item for item in self._retry_preserved
            }
            comparisons = tuple(
                retried.get(test_id) or preserved[test_id]
                for test_id in self._retry_order
                if test_id in retried or test_id in preserved
            )
            self._retry_order = ()
            self._retry_preserved = ()
        successful = tuple(item for item in comparisons if not item.error)
        if command.error or not successful:
            self._finish_operation("fail")
            self._set(
                replace(
                    state,
                    stage="candidate",
                    operation_id="",
                    comparisons=comparisons,
                    message=command.error or "沒有成功的比較，請重試或更換案例。",
                )
            )
            return
        self._finish_operation("succeed")
        self._set(
            replace(
                state,
                stage="review",
                operation_id="",
                comparisons=comparisons,
                test_progress="",
                apply_gate=self._comparison_policy.apply_gate(()),
                message="請逐一選擇哪個結果比較好。",
            )
        )

    def _set_verdict(self, command: SetRecipeComparisonVerdict) -> None:
        state = self._state
        if (
            state is None
            or state.stage != "review"
            or not self._candidate_identity_matches(
                command.candidate_parent_version,
                command.candidate_iteration,
            )
        ):
            return
        if command.verdict not in {
            "current_better",
            "candidate_better",
            "both_need_work",
        }:
            return
        comparisons = tuple(
            replace(
                item,
                verdict=cast(RecipeComparisonVerdict, command.verdict),
                improvement_reasons=command.reasons,
                improvement_note=command.note.strip(),
            )
            if item.test_id == command.test_id and not item.error
            else item
            for item in state.comparisons
        )
        verdicts = tuple(
            item.verdict
            for item in comparisons
            if not item.error and item.verdict != "unreviewed"
        )
        successful_count = sum(not item.error for item in comparisons)
        gate = (
            self._comparison_policy.apply_gate(verdicts)
            if len(verdicts) == successful_count
            else self._comparison_policy.apply_gate(())
        )
        if gate.mode != "blocked" and self._revisions is None:
            gate = replace(
                gate,
                mode="blocked",
                message=(
                    self._revision_warning
                    or "個人 Recipe 版本儲存目前不可用，無法套用。"
                ),
            )
        self._set(replace(state, comparisons=comparisons, apply_gate=gate))

    def _apply_candidate(self, command: ApplyRecipeCandidate) -> None:
        state = self._state
        if (
            state is None
            or state.stage != "review"
            or state.candidate is None
            or self._revisions is None
            or not command.operation_id
            or not self._candidate_identity_matches(
                command.candidate_parent_version,
                command.candidate_iteration,
            )
        ):
            return
        gate = state.apply_gate
        if gate.mode == "blocked":
            self._set(replace(state, message=gate.message))
            return
        if gate.mode == "confirm" and not command.confirm_mixed_results:
            self._set(replace(state, message="比較結果不一致；請再次確認仍要套用。"))
            return
        self._set(
            replace(
                state,
                stage="applying",
                operation_id=command.operation_id,
                message="正在套用個人 Recipe 版本…",
            )
        )
        successful = sum(not item.error for item in state.comparisons)
        candidate_wins = sum(
            item.verdict == "candidate_better" for item in state.comparisons
        )
        try:
            revision = self._revisions.apply(
                state.candidate,
                f"{candidate_wins}／{successful} 個比較偏好新版本",
            )
        except (OSError, ValueError) as exc:
            self._set(
                replace(state, operation_id="", message=f"套用失敗：{exc}")
            )
            return
        self._action = self._evidence.action(state.action_id, state.press_type)
        self._drafts.pop((state.action_id, state.press_type), None)
        self._set(
            replace(
                state,
                stage="applied",
                operation_id="",
                overview=self._evidence.overview(),
                current_version=revision.version_id,
                message="已套用；新的執行會立即使用這個版本，不需要重新啟動。",
            )
        )

    def _cancel_operation(
        self,
        command: CancelRecipeImprovementOperation,
    ) -> None:
        state = self._state
        if (
            state is None
            or state.stage not in {"generating", "testing"}
            or state.operation_id != command.operation_id
        ):
            return
        if self._cancellation is not None:
            self._cancellation.cancel()
        if self._supervisor is not None:
            self._supervisor.cancel(command.operation_id)
        self._cancellation = None
        self._finish_operation("cancel")
        fallback: Literal["candidate", "evidence"] = (
            "candidate" if state.candidate is not None else "evidence"
        )
        self._set(
            replace(
                state,
                stage=fallback,
                operation_id="",
                test_progress="",
                message="已取消目前的作業。",
            )
        )

    def _open_history(self, command: OpenRecipeVersionHistory) -> None:
        action = self._evidence.action(command.action_id, command.press_type)
        history = (
            self._revisions.history(command.action_id, command.press_type)
            if self._revisions is not None
            else ()
        )
        self._action = action
        self._set(
            RecipeImprovementState(
                "history",
                self._evidence.overview(),
                action_id=action.id,
                press_type=action.press_type,
                action_name=action.name,
                current_version=action.version_id,
                current_system_prompt=action.system_prompt,
                current_prompt=action.prompt,
                revision_history=history,
                active_revision_id=(
                    self._revisions.active_revision_id(
                        action.id,
                        action.press_type,
                    )
                    if self._revisions is not None
                    else ""
                ),
                builtin_update_available=(
                    self._revisions.builtin_update_available(
                        action.id,
                        action.press_type,
                    )
                    if self._revisions is not None
                    else False
                ),
                message=self._revision_warning,
            )
        )

    def _restore_version(self, command: RestoreRecipeVersion) -> None:
        state = self._state
        if (
            state is None
            or state.stage != "history"
            or self._revisions is None
            or not command.confirmed
            or not command.operation_id
        ):
            return
        self._set(
            replace(
                state,
                stage="applying",
                operation_id=command.operation_id,
                message="正在還原選取的 Recipe 版本…",
            )
        )
        try:
            revision = self._revisions.restore(
                command.action_id,
                command.press_type,
                command.revision_id,
            )
        except (OSError, ValueError) as exc:
            self._set(
                replace(state, operation_id="", message=f"還原失敗：{exc}")
            )
            return
        self._action = self._evidence.action(
            command.action_id,
            command.press_type,
        )
        self._drafts.pop((command.action_id, command.press_type), None)
        self._set(
            replace(
                state,
                stage="applied",
                operation_id="",
                overview=self._evidence.overview(),
                current_version=revision.version_id,
                message="已還原選取的版本；新的執行會立即生效，不需要重新啟動。",
            )
        )

    def _keep_personal_version(
        self,
        command: KeepPersonalRecipeVersion,
    ) -> None:
        state = self._state
        if (
            state is None
            or state.stage != "history"
            or self._revisions is None
            or not command.operation_id
        ):
            return
        self._set(
            replace(
                state,
                stage="applying",
                operation_id=command.operation_id,
                message="正在保留目前的個人 Recipe 版本…",
            )
        )
        try:
            self._revisions.keep_personal_after_builtin_update(
                command.action_id,
                command.press_type,
            )
        except OSError as exc:
            self._set(
                replace(state, operation_id="", message=f"無法保存選擇：{exc}")
            )
            return
        self._set(
            replace(
                state,
                operation_id="",
                builtin_update_available=False,
                message="已保留目前的個人版本。",
            )
        )

    def _refine_candidate(self, command: RefineRecipeCandidate) -> None:
        state = self._state
        if (
            state is None
            or state.stage not in {"candidate", "review"}
            or not self._candidate_identity_matches(
                command.candidate_parent_version,
                command.candidate_iteration,
            )
        ):
            return
        comparison_feedback = "; ".join(
            part
            for item in state.comparisons
            if item.verdict == "both_need_work"
            for part in (
                ", ".join(item.improvement_reasons),
                item.improvement_note,
            )
            if part
        )
        self._set(
            replace(
                state,
                stage="evidence",
                comparisons=(),
                user_direction="\n".join(
                    part
                    for part in (
                        state.user_direction,
                        comparison_feedback,
                    )
                    if part
                ),
                message="已帶入比較中的原因與補充說明；請確認後產生下一個候選版本。",
            )
        )

    def _return_to_candidate(self, command: ReturnToRecipeCandidate) -> None:
        state = self._state
        if (
            state is None
            or state.candidate is None
            or not self._candidate_identity_matches(
                command.candidate_parent_version,
                command.candidate_iteration,
            )
        ):
            return
        self._set(
            replace(
                state,
                stage="candidate",
                comparisons=(),
                message=state.candidate.explanation,
            )
        )

    def _treat_issue_as_prompt(
        self,
        command: TreatRecipeIssueAsPrompt,
    ) -> None:
        state = self._state
        if (
            state is None
            or state.stage != "evidence"
            or not state.suspected_app_issue
            or command.action_version != state.current_version
        ):
            return
        self._force_prompt_issue = True
        self._set(
            replace(
                state,
                suspected_app_issue=False,
                message="已保留為 Prompt 回饋。請確認方向後再次產生候選。",
            )
        )

    def _retry_failed_tests(self, command: RetryFailedRecipeTests) -> None:
        state = self._state
        previous = self._last_test_command
        if (
            state is None
            or state.stage not in {"candidate", "review"}
            or previous is None
        ):
            return
        failed_ids = {
            item.test_id for item in state.comparisons if item.error
        }
        if not failed_ids:
            return
        self._retry_order = tuple(item.test_id for item in state.comparisons)
        self._retry_preserved = tuple(
            item for item in state.comparisons if not item.error
        )
        retry = RunRecipeCandidateTests(
            tuple(
                feedback_id
                for feedback_id in previous.selected_feedback_ids
                if feedback_id in failed_ids
            ),
            tuple(
                case
                for case in previous.manual_cases
                if case.test_id in failed_ids
            ),
            command.operation_id,
            tuple(
                item
                for item in previous.saved_case_importance
                if item[0] in failed_ids
            ),
        )
        self._state = replace(state, stage="candidate")
        self._run_tests(retry)

    @staticmethod
    def _build_test_request(
        action: ResolvedAction,
        input_text: str,
        model: str,
    ) -> LLMRequest:
        return LLMRequest(
            (
                LLMMessage("system", action.system_prompt),
                LLMMessage("user", action.prompt.format(input=input_text)),
            ),
            model,
            action.temperature if action.temperature is not None else 0.2,
        )

    def _set(self, state: RecipeImprovementState) -> None:
        self._state = state
        if (
            state.action_id
            and state.stage not in {"overview", "history", "applied"}
            and self._action is not None
        ):
            self._drafts[(state.action_id, state.press_type)] = _RecipeDraft(
                state,
                self._action,
                self._binding,
            )
        self._presenter.set_recipe_improvement(state)

    def _candidate_identity_matches(
        self,
        parent_version: str,
        iteration: int,
    ) -> bool:
        state = self._state
        candidate = state.candidate if state is not None else None
        if candidate is None:
            return False
        return (
            candidate.parent_version == parent_version
            and candidate.iteration == iteration
        )

    def _finish_operation(
        self,
        outcome: Literal["succeed", "fail", "cancel"],
    ) -> None:
        handle = self._operation_handle
        self._operation_handle = None
        if handle is not None:
            getattr(handle, outcome)()
