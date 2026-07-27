from __future__ import annotations

from collections.abc import Callable
import difflib
import tkinter as tk
from tkinter import messagebox
import uuid

import customtkinter as ctk

from ClipAI.core.commands import (
    ApplyRecipeCandidate,
    BeginRecipeImprovement,
    CancelRecipeImprovementOperation,
    GenerateRecipeCandidate,
    KeepPersonalRecipeVersion,
    OpenRecipeImprovement,
    OpenProviderSettings,
    OpenRecipeVersionHistory,
    RestoreRecipeVersion,
    RefineRecipeCandidate,
    ReturnToRecipeCandidate,
    RetryFailedRecipeTests,
    TreatRecipeIssueAsPrompt,
    RunRecipeCandidateTests,
    SetRecipeComparisonVerdict,
)
from ClipAI.core.models import (
    PresentationDocument,
    RecipeEvidenceItem,
    RecipeComparisonVerdict,
    RecipeImprovementState,
    RecipeManualTestCase,
)
from ClipAI.ui.window_icons import (
    CUSTOMTKINTER_ICON_DELAY_MS,
    destroy_windows_window_icons,
    install_clipai_window_icons,
)


_DIRECTIONS = ("更精簡", "更清楚", "更實用", "保留更多細節", "改善格式")


def default_test_ids(
    evidence: tuple[RecipeEvidenceItem, ...],
) -> tuple[str, ...]:
    saved = tuple(item for item in evidence if item.has_saved_case)
    negatives = tuple(item for item in saved if item.outcome == "needs_adjustment")
    helpful = tuple(item for item in saved if item.outcome == "helpful")
    selected = list(negatives[:2])
    if helpful:
        selected.append(helpful[0])
    else:
        selected = list(negatives[:3])
    return tuple(item.feedback_id for item in selected)


class RecipeImprovementDialog:
    """Toolkit adapter for the typed Recipe-improvement state machine."""

    def __init__(self, master, command_sink: Callable[[object], None]) -> None:
        self._command_sink = command_sink
        self._state: RecipeImprovementState | None = None
        self._visible = True
        self._intro_shown = False
        self._window = ctk.CTkToplevel(master)
        self._window.title("ClipAI — 改善 Recipe")
        self._window.geometry("760x700")
        self._window.minsize(640, 560)
        self._window.protocol("WM_DELETE_WINDOW", self.close)
        self._window.bind("<Escape>", lambda _event: self.close())
        self._window_icon_handles: tuple[int, ...] = ()
        self._window.after(
            CUSTOMTKINTER_ICON_DELAY_MS,
            self._apply_windows_window_icons,
        )
        self._content = ctk.CTkScrollableFrame(self._window)
        self._content.pack(fill="both", expand=True, padx=16, pady=16)
        self._content.grid_columnconfigure(0, weight=1)
        self._evidence_vars: dict[str, tk.BooleanVar] = {}
        self._direction_vars: dict[str, tk.BooleanVar] = {}
        self._privacy_var = tk.BooleanVar(value=False)
        self._test_vars: dict[str, tk.BooleanVar] = {}
        self._saved_importance: dict[str, ctk.CTkEntry] = {}
        self._direction_entry: ctk.CTkTextbox | None = None
        self._manual_inputs: list[ctk.CTkTextbox] = []
        self._manual_importance: list[ctk.CTkEntry] = []
        self._comparison_reason_vars: dict[
            str,
            dict[str, tk.BooleanVar],
        ] = {}
        self._comparison_notes: dict[str, ctk.CTkEntry] = {}

    def show(self, state: RecipeImprovementState) -> None:
        self._visible = True
        self.apply(state)

    def apply(self, state: RecipeImprovementState) -> None:
        self._state = state
        for child in self._content.winfo_children():
            child.destroy()
        if state.stage == "overview":
            self._render_overview(state)
        elif state.stage in {"evidence", "generating", "error"}:
            self._render_evidence(state)
        elif state.stage == "candidate":
            self._render_candidate(state)
        elif state.stage == "testing":
            self._render_testing(state)
        elif state.stage == "review":
            self._render_review(state)
        elif state.stage == "applying":
            self._render_applying(state)
        elif state.stage == "history":
            self._render_history(state)
        elif state.stage == "applied":
            self._render_applied(state)
        if self._visible:
            self._window.deiconify()
            self._window.lift()
            self._window.focus_force()

    def _heading(self, text: str, subtitle: str = "") -> int:
        ctk.CTkLabel(
            self._content,
            text=text,
            anchor="w",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 2))
        if subtitle:
            ctk.CTkLabel(
                self._content,
                text=subtitle,
                anchor="w",
                justify="left",
                wraplength=680,
                text_color="#A9BACB",
            ).grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 12))
            return 2
        return 1

    def _render_overview(self, state: RecipeImprovementState) -> None:
        subtitle = (
            "選擇一個 Recipe，ClipAI 會根據你保存的回饋提出改善版本。"
            if not self._intro_shown
            else ""
        )
        self._intro_shown = True
        row = self._heading("改善 Recipe", subtitle)
        if state.message:
            ctk.CTkLabel(
                self._content,
                text=state.message,
                anchor="w",
                justify="left",
                wraplength=680,
                text_color="#FFB347",
            ).grid(row=row, column=0, sticky="ew", padx=8, pady=8)
            row += 1
        for variant in state.overview.variants:
            frame = ctk.CTkFrame(self._content)
            frame.grid(row=row, column=0, sticky="ew", padx=8, pady=6)
            frame.grid_columnconfigure(0, weight=1)
            press = "短按" if variant.press_type == "short" else "長按"
            ctk.CTkLabel(
                frame,
                text=f"{variant.name} · {press}",
                anchor="w",
                font=ctk.CTkFont(weight="bold"),
            ).grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 2))
            status = (
                f"{variant.negative_feedback_count} 則需調整 · "
                f"{variant.saved_case_count} 個已保存案例"
            )
            if variant.reminder_recommended:
                status += " · 建議現在改善"
            elif (
                variant.feedback_count
                and variant.negative_feedback_count == 0
            ):
                status = "目前回饋顯示運作良好"
            ctk.CTkLabel(frame, text=status, anchor="w").grid(
                row=1, column=0, sticky="ew", padx=14, pady=(0, 12)
            )
            ctk.CTkButton(
                frame,
                text=(
                    "開始改善"
                    if variant.improvement_supported
                    else variant.unavailable_reason
                ),
                width=130,
                state="normal" if variant.improvement_supported else "disabled",
                command=lambda action_id=variant.action_id, press_type=variant.press_type: self._command_sink(
                    BeginRecipeImprovement(action_id, press_type)
                ),
            ).grid(row=0, column=1, padx=14, pady=(10, 4))
            ctk.CTkButton(
                frame,
                text="版本記錄",
                width=130,
                fg_color="#4A4A4A",
                command=lambda action_id=variant.action_id, press_type=variant.press_type: self._command_sink(
                    OpenRecipeVersionHistory(action_id, press_type)
                ),
            ).grid(row=1, column=1, padx=14, pady=(4, 10))
            row += 1

    def _render_evidence(self, state: RecipeImprovementState) -> None:
        row = self._heading(
            f"{state.action_name} · {'短按' if state.press_type == 'short' else '長按'}",
            f"本次改善固定使用 {state.provider or '未設定 Provider'} / {state.model or '未設定模型'} · 產生建議會送出 1 次 AI 請求",
        )
        if state.message:
            ctk.CTkLabel(
                self._content,
                text=state.message,
                anchor="w",
                justify="left",
                wraplength=680,
                text_color="#FFB347",
            ).grid(row=row, column=0, sticky="ew", padx=8, pady=(0, 10))
            row += 1
        if state.suspected_app_issue:
            issue_actions = ctk.CTkFrame(
                self._content,
                fg_color="transparent",
            )
            issue_actions.grid(row=row, column=0, sticky="ew", padx=8, pady=4)
            ctk.CTkButton(
                issue_actions,
                text="返回 Recipe 清單",
                fg_color="#4A4A4A",
                command=lambda: self._command_sink(OpenRecipeImprovement()),
            ).pack(side="left")
            ctk.CTkButton(
                issue_actions,
                text="仍視為 Prompt 問題",
                command=lambda: self._command_sink(
                    TreatRecipeIssueAsPrompt(state.current_version)
                ),
            ).pack(side="right")
            row += 1
        ctk.CTkLabel(
            self._content,
            text="選擇要參考的回饋",
            anchor="w",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=row, column=0, sticky="ew", padx=8)
        row += 1
        self._evidence_vars = {}
        for item in state.evidence:
            evidence_frame = ctk.CTkFrame(
                self._content,
                fg_color="transparent",
            )
            evidence_frame.grid(
                row=row,
                column=0,
                sticky="ew",
                padx=10,
                pady=4,
            )
            evidence_frame.grid_columnconfigure(0, weight=1)
            selected = item.feedback_id in state.selected_feedback_ids
            variable = tk.BooleanVar(value=selected)
            self._evidence_vars[item.feedback_id] = variable
            outcome = "有幫助" if item.outcome == "helpful" else "需要調整"
            note = item.note or item.reason or "沒有補充說明"
            saved = " · 含保存案例" if item.has_saved_case else ""
            ctk.CTkCheckBox(
                evidence_frame,
                text=f"{outcome}{saved}\n{note}",
                variable=variable,
            ).grid(row=0, column=0, sticky="w", padx=4, pady=5)
            if item.has_saved_case:
                preview = " ".join(
                    (item.input_text or "").split()
                )[:90]
                ctk.CTkLabel(
                    evidence_frame,
                    text=f"輸入預覽：{preview}",
                    anchor="w",
                    text_color="#A9BACB",
                ).grid(row=1, column=0, sticky="ew", padx=30, pady=(0, 4))
                ctk.CTkButton(
                    evidence_frame,
                    text="展開",
                    width=70,
                    fg_color="#4A4A4A",
                    command=lambda frame=evidence_frame, selected_item=item: self._toggle_evidence_detail(
                        frame,
                        selected_item,
                    ),
                ).grid(row=0, column=1, rowspan=2, padx=4)
            row += 1
        if not state.evidence:
            ctk.CTkLabel(
                self._content,
                text="目前沒有回饋。你仍可描述想改善的方向，之後需加入手動測試案例。",
                anchor="w",
                justify="left",
                wraplength=680,
            ).grid(row=row, column=0, sticky="ew", padx=14, pady=8)
            row += 1
        if not state.can_generate:
            ctk.CTkButton(
                self._content,
                text="開啟 Settings and Models",
                command=lambda: self._command_sink(OpenProviderSettings()),
            ).grid(row=row, column=0, sticky="w", padx=8, pady=8)
            row += 1
        ctk.CTkLabel(
            self._content,
            text="你希望怎麼改善？",
            anchor="w",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=row, column=0, sticky="ew", padx=8, pady=(14, 4))
        row += 1
        direction_frame = ctk.CTkFrame(self._content, fg_color="transparent")
        direction_frame.grid(row=row, column=0, sticky="ew", padx=8)
        self._direction_vars = {}
        for index, label in enumerate(_DIRECTIONS):
            variable = tk.BooleanVar(value=label in state.directions)
            self._direction_vars[label] = variable
            ctk.CTkCheckBox(
                direction_frame,
                text=label,
                variable=variable,
                width=120,
            ).grid(row=index // 3, column=index % 3, sticky="w", padx=4, pady=4)
        row += 1
        self._direction_entry = ctk.CTkTextbox(self._content, height=90)
        self._direction_entry.grid(row=row, column=0, sticky="ew", padx=8, pady=8)
        self._direction_entry.insert("1.0", state.user_direction)
        row += 1
        privacy = (
            "我同意將目前 Prompt、所選回饋與其中已保存的案例傳送給"
            f" {state.provider or '目前的 AI Provider'}；資料不會同步到其他裝置。"
        )
        self._privacy_var = tk.BooleanVar(
            value=not state.privacy_confirmation_required
        )
        privacy_frame = ctk.CTkFrame(
            self._content,
            fg_color="transparent",
        )
        privacy_frame.grid(row=row, column=0, sticky="ew", padx=8, pady=10)
        ctk.CTkCheckBox(
            privacy_frame,
            text="我同意傳送上述資料",
            variable=self._privacy_var,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            privacy_frame,
            text=privacy,
            anchor="w",
            justify="left",
            wraplength=650,
        ).grid(row=1, column=0, sticky="ew", pady=(6, 0))
        row += 1
        buttons = ctk.CTkFrame(self._content, fg_color="transparent")
        buttons.grid(row=row, column=0, sticky="ew", padx=8, pady=8)
        ctk.CTkButton(
            buttons,
            text="返回",
            width=100,
            fg_color="#4A4A4A",
            command=lambda: self._command_sink(OpenRecipeImprovement()),
        ).pack(side="left")
        pending = state.stage == "generating"
        ctk.CTkButton(
            buttons,
            text="正在產生…" if pending else "產生改善建議",
            state="disabled" if pending or not state.can_generate else "normal",
            command=self._generate,
        ).pack(side="right")
        if pending:
            ctk.CTkButton(
                buttons,
                text="取消",
                width=90,
                fg_color="#7A3030",
                command=lambda: self._command_sink(
                    CancelRecipeImprovementOperation(state.operation_id)
                ),
            ).pack(side="right", padx=8)

    def _generate(self) -> None:
        state = self._state
        if state is None or self._direction_entry is None:
            return
        self._command_sink(
            GenerateRecipeCandidate(
                tuple(
                    feedback_id
                    for feedback_id, variable in self._evidence_vars.items()
                    if variable.get()
                ),
                tuple(
                    label
                    for label, variable in self._direction_vars.items()
                    if variable.get()
                ),
                self._direction_entry.get("1.0", "end").strip(),
                bool(self._privacy_var.get()),
                uuid.uuid4().hex,
            )
        )

    def _toggle_evidence_detail(
        self,
        frame,
        item: RecipeEvidenceItem,
    ) -> None:
        existing = getattr(frame, "_recipe_detail", None)
        if existing is not None:
            existing.destroy()
            frame._recipe_detail = None
            return
        detail = ctk.CTkTextbox(frame, height=150)
        detail.grid(row=2, column=0, columnspan=2, sticky="ew", padx=28, pady=6)
        detail.insert(
            "1.0",
            f"完整輸入\n{item.input_text or ''}\n\n完整結果\n{item.result_text or ''}",
        )
        detail.configure(state="disabled")
        frame._recipe_detail = detail

    def _render_candidate(self, state: RecipeImprovementState) -> None:
        assert state.candidate is not None
        row = self._heading(
            f"改善建議 {state.iteration}",
            f"{state.provider} / {state.model} · 下一步先用實際案例比較，再決定是否套用。",
        )
        ctk.CTkLabel(
            self._content,
            text=state.message,
            anchor="w",
            justify="left",
            wraplength=680,
        ).grid(row=row, column=0, sticky="ew", padx=8, pady=8)
        row += 1
        summary = ctk.CTkFrame(self._content)
        summary.grid(row=row, column=0, sticky="ew", padx=8, pady=8)
        summary.grid_columnconfigure(1, weight=1)
        for summary_row, (label, value) in enumerate(
            (
                (
                    "觀察到的問題",
                    state.candidate.problem_summary or state.candidate.explanation,
                ),
                (
                    "建議修改",
                    state.candidate.proposed_change or state.candidate.explanation,
                ),
                (
                    "必須保留",
                    state.candidate.preserve_behavior or "維持原 Recipe 的用途與輸出契約。",
                ),
            )
        ):
            ctk.CTkLabel(
                summary,
                text=label,
                font=ctk.CTkFont(weight="bold"),
                anchor="nw",
            ).grid(
                row=summary_row,
                column=0,
                sticky="nw",
                padx=10,
                pady=6,
            )
            ctk.CTkLabel(
                summary,
                text=value,
                anchor="w",
                justify="left",
                wraplength=530,
            ).grid(
                row=summary_row,
                column=1,
                sticky="ew",
                padx=10,
                pady=6,
            )
        row += 1
        details = ctk.CTkTextbox(self._content, height=180)
        details.grid(row=row, column=0, sticky="ew", padx=8, pady=8)
        details.insert(
            "1.0",
            "System prompt diff\n"
            + "\n".join(
                difflib.unified_diff(
                    state.current_system_prompt.splitlines(),
                    state.candidate.system_prompt.splitlines(),
                    fromfile="目前版本 / system_prompt",
                    tofile="候選版本 / system_prompt",
                    lineterm="",
                )
            )
            + "\n\nUser prompt diff\n"
            + "\n".join(
                difflib.unified_diff(
                    state.current_prompt.splitlines(),
                    state.candidate.prompt.splitlines(),
                    fromfile="目前版本 / prompt",
                    tofile="候選版本 / prompt",
                    lineterm="",
                )
            )
            + "\n\n候選 raw prompt\n"
            + state.candidate.system_prompt
            + "\n\n"
            + state.candidate.prompt,
        )
        details.configure(state="disabled")
        row += 1
        ctk.CTkLabel(
            self._content,
            text="選擇測試案例（1–5 個）",
            anchor="w",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=row, column=0, sticky="ew", padx=8, pady=(12, 4))
        row += 1
        defaults = set(default_test_ids(state.evidence))
        self._test_vars = {}
        self._saved_importance = {}
        for item in state.evidence:
            if not item.has_saved_case:
                continue
            variable = tk.BooleanVar(value=item.feedback_id in defaults)
            self._test_vars[item.feedback_id] = variable
            saved_frame = ctk.CTkFrame(self._content, fg_color="transparent")
            saved_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=4)
            saved_frame.grid_columnconfigure(0, weight=1)
            ctk.CTkCheckBox(
                saved_frame,
                text=f"{'需要調整' if item.outcome == 'needs_adjustment' else '有幫助'} · {item.note or item.reason}",
                variable=variable,
            ).grid(row=0, column=0, sticky="w", padx=4, pady=3)
            importance = ctk.CTkEntry(
                saved_frame,
                placeholder_text="這個例子最重要的是什麼？（選填）",
            )
            importance.grid(row=1, column=0, sticky="ew", padx=30, pady=3)
            self._saved_importance[item.feedback_id] = importance
            row += 1
        self._manual_inputs = []
        self._manual_importance = []
        for manual_index in range(5):
            manual_frame = ctk.CTkFrame(
                self._content,
                fg_color="transparent",
            )
            manual_frame.grid(row=row, column=0, sticky="ew", padx=8, pady=5)
            manual_frame.grid_columnconfigure(0, weight=1)
            manual_input = ctk.CTkTextbox(manual_frame, height=70)
            manual_input.grid(row=0, column=0, sticky="ew")
            importance = ctk.CTkEntry(
                manual_frame,
                placeholder_text=f"手動案例 {manual_index + 1}：最重要的是什麼？（選填）",
            )
            importance.grid(row=1, column=0, sticky="ew", pady=(4, 0))
            self._manual_inputs.append(manual_input)
            self._manual_importance.append(importance)
            row += 1
        ctk.CTkLabel(
            self._content,
            text="若要加入手動案例，請在上方貼上輸入內容。",
            anchor="w",
            text_color="#A9BACB",
        ).grid(row=row, column=0, sticky="ew", padx=8)
        row += 1
        buttons = ctk.CTkFrame(self._content, fg_color="transparent")
        buttons.grid(row=row, column=0, sticky="ew", padx=8, pady=14)
        ctk.CTkButton(
            buttons,
            text="這個建議不好",
            fg_color="#4A4A4A",
            command=lambda: self._command_sink(
                RefineRecipeCandidate(
                    state.candidate.parent_version,
                    state.candidate.iteration,
                )
            ),
        ).pack(side="left")
        ctk.CTkButton(
            buttons,
            text="開始比較",
            command=self._run_tests,
        ).pack(side="right")
        if any(item.error for item in state.comparisons):
            ctk.CTkButton(
                buttons,
                text="重試失敗案例",
                fg_color="#7A5A20",
                command=lambda: self._command_sink(
                    RetryFailedRecipeTests(uuid.uuid4().hex)
                ),
            ).pack(side="right", padx=8)

    def _run_tests(self) -> None:
        state = self._state
        if state is None:
            return
        manual_cases = tuple(
            RecipeManualTestCase(
                uuid.uuid4().hex,
                manual_input.get("1.0", "end").strip(),
                importance.get().strip(),
            )
            for manual_input, importance in zip(
                self._manual_inputs,
                self._manual_importance,
            )
            if manual_input.get("1.0", "end").strip()
        )
        self._command_sink(
            RunRecipeCandidateTests(
                tuple(
                    feedback_id
                    for feedback_id, variable in self._test_vars.items()
                    if variable.get()
                ),
                manual_cases,
                uuid.uuid4().hex,
                tuple(
                    (feedback_id, entry.get().strip())
                    for feedback_id, entry in self._saved_importance.items()
                    if entry.get().strip()
                ),
            )
        )

    def _render_testing(self, state: RecipeImprovementState) -> None:
        row = self._heading(
            "正在比較",
            f"{state.provider} / {state.model} · 共 {state.request_count} 次 AI 請求",
        )
        ctk.CTkLabel(
            self._content,
            text=state.test_progress,
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=row, column=0, padx=8, pady=30)
        ctk.CTkButton(
            self._content,
            text="取消測試",
            fg_color="#7A3030",
            command=lambda: self._command_sink(
                CancelRecipeImprovementOperation(state.operation_id)
            ),
        ).grid(row=row + 1, column=0, padx=8, pady=8)

    def _render_review(self, state: RecipeImprovementState) -> None:
        row = self._heading(
            "比較結果",
            "A 是目前版本，B 是改善候選。"
            f" 已完成 {sum(not item.error for item in state.comparisons)}／{len(state.comparisons)} 個比較。"
            " 請逐一選擇，不會只靠顏色表示。",
        )
        self._comparison_reason_vars = {}
        self._comparison_notes = {}
        for comparison in state.comparisons:
            frame = ctk.CTkFrame(self._content)
            frame.grid(row=row, column=0, sticky="ew", padx=8, pady=8)
            frame.grid_columnconfigure((0, 1), weight=1)
            ctk.CTkLabel(
                frame,
                text=comparison.importance or comparison.input_text[:100],
                anchor="w",
                justify="left",
                wraplength=620,
            ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=8)
            if comparison.error:
                ctk.CTkLabel(
                    frame,
                    text=f"測試失敗：{comparison.error}",
                    text_color="#E81123",
                ).grid(row=1, column=0, columnspan=2, padx=12, pady=8)
            else:
                for column, label, value, document in (
                    (
                        0,
                        f"A · {comparison.baseline_label}",
                        comparison.current_result,
                        comparison.current_presentation,
                    ),
                    (
                        1,
                        f"B · {comparison.candidate_label}",
                        comparison.candidate_result,
                        comparison.candidate_presentation,
                    ),
                ):
                    self._render_comparison_output(
                        frame,
                        column,
                        label,
                        value,
                        document,
                    )
                choices = ctk.CTkFrame(frame, fg_color="transparent")
                choices.grid(row=5, column=0, columnspan=2, pady=8)
                for label, verdict in (
                    ("A 比較好", "current_better"),
                    ("B 比較好", "candidate_better"),
                    ("都需要改善", "both_need_work"),
                ):
                    ctk.CTkButton(
                        choices,
                        text=label,
                        width=110,
                        fg_color=(
                            "#0052B8"
                            if comparison.verdict == verdict
                            else "#4A4A4A"
                        ),
                        command=lambda test_id=comparison.test_id, selected=verdict: self._command_sink(
                            self._comparison_verdict_command(
                                state,
                                test_id,
                                selected,
                            )
                        ),
                    ).pack(side="left", padx=4)
                improvement = ctk.CTkFrame(frame, fg_color="transparent")
                improvement.grid(
                    row=6,
                    column=0,
                    columnspan=2,
                    sticky="ew",
                    padx=8,
                    pady=(0, 8),
                )
                reason_vars: dict[str, tk.BooleanVar] = {}
                for reason_column, reason in enumerate(
                    ("不夠清楚", "遺漏重點", "語氣或格式不合")
                ):
                    variable = tk.BooleanVar(
                        value=reason in comparison.improvement_reasons
                    )
                    reason_vars[reason] = variable
                    ctk.CTkCheckBox(
                        improvement,
                        text=reason,
                        variable=variable,
                    ).grid(
                        row=0,
                        column=reason_column,
                        sticky="w",
                        padx=4,
                        pady=3,
                    )
                note = ctk.CTkEntry(
                    improvement,
                    placeholder_text="都需要改善時，請補充原因（選填）",
                )
                note.grid(
                    row=1,
                    column=0,
                    columnspan=3,
                    sticky="ew",
                    padx=4,
                    pady=4,
                )
                if comparison.improvement_note:
                    note.insert(0, comparison.improvement_note)
                improvement.grid_columnconfigure((0, 1, 2), weight=1)
                self._comparison_reason_vars[comparison.test_id] = reason_vars
                self._comparison_notes[comparison.test_id] = note
            row += 1
        ctk.CTkLabel(
            self._content,
            text=state.apply_gate.message,
            anchor="w",
            wraplength=680,
        ).grid(row=row, column=0, sticky="ew", padx=8, pady=8)
        row += 1
        review_actions = ctk.CTkFrame(self._content, fg_color="transparent")
        review_actions.grid(row=row, column=0, sticky="ew", padx=8, pady=12)
        ctk.CTkButton(
            review_actions,
            text=(
                "繼續改善"
                if any(
                    item.verdict == "both_need_work"
                    for item in state.comparisons
                )
                else "重新選擇測試案例"
            ),
            fg_color="#4A4A4A",
            command=lambda: self._command_sink(
                RefineRecipeCandidate(
                    state.candidate.parent_version
                    if state.candidate is not None
                    else "",
                    state.candidate.iteration
                    if state.candidate is not None
                    else 0,
                )
                if any(
                    item.verdict == "both_need_work"
                    for item in state.comparisons
                )
                else ReturnToRecipeCandidate(
                    state.candidate.parent_version
                    if state.candidate is not None
                    else "",
                    state.candidate.iteration
                    if state.candidate is not None
                    else 0,
                )
            ),
        ).pack(side="left")
        if any(item.error for item in state.comparisons):
            ctk.CTkButton(
                review_actions,
                text="重試失敗案例",
                fg_color="#7A5A20",
                command=lambda: self._command_sink(
                    RetryFailedRecipeTests(uuid.uuid4().hex)
                ),
            ).pack(side="left", padx=8)
        ctk.CTkButton(
            review_actions,
            text="套用這個版本",
            state="disabled" if state.apply_gate.mode == "blocked" else "normal",
            command=self._apply_candidate,
        ).pack(side="right")

    def _comparison_verdict_command(
        self,
        state: RecipeImprovementState,
        test_id: str,
        verdict: RecipeComparisonVerdict,
    ) -> SetRecipeComparisonVerdict:
        candidate = state.candidate
        reason_vars = self._comparison_reason_vars.get(test_id, {})
        note = self._comparison_notes.get(test_id)
        return SetRecipeComparisonVerdict(
            test_id,
            verdict,
            candidate.parent_version if candidate is not None else "",
            candidate.iteration if candidate is not None else 0,
            tuple(
                reason
                for reason, variable in reason_vars.items()
                if variable.get()
            ),
            note.get().strip() if note is not None else "",
        )

    def _render_comparison_output(
        self,
        frame,
        column: int,
        label: str,
        raw_text: str,
        document: PresentationDocument | None,
    ) -> None:
        ctk.CTkLabel(frame, text=label).grid(
            row=1,
            column=column,
            sticky="w",
            padx=12,
        )
        preview = ctk.CTkScrollableFrame(frame, height=150)
        preview.grid(row=2, column=column, sticky="nsew", padx=8, pady=6)
        preview.grid_columnconfigure(0, weight=1)
        if document is None:
            ctk.CTkLabel(
                preview,
                text=raw_text,
                anchor="nw",
                justify="left",
                wraplength=285,
            ).grid(row=0, column=0, sticky="ew", padx=6, pady=4)
        else:
            for row_index, block in enumerate(document.blocks):
                text = "".join(span.text for span in block.spans)
                if block.kind == "unordered_item":
                    text = f"• {text}"
                elif block.kind == "ordered_item":
                    text = f"{block.ordinal or 1}. {text}"
                ctk.CTkLabel(
                    preview,
                    text=text,
                    anchor="w",
                    justify="left",
                    wraplength=285,
                    font=ctk.CTkFont(
                        weight=(
                            "bold"
                            if block.kind == "heading"
                            else "normal"
                        )
                    ),
                ).grid(
                    row=row_index,
                    column=0,
                    sticky="ew",
                    padx=6,
                    pady=(5 if block.kind == "heading" else 2),
                )
        ctk.CTkButton(
            frame,
            text="查看 raw",
            width=80,
            fg_color="#4A4A4A",
            command=lambda parent=frame, selected_column=column, value=raw_text: self._toggle_raw_output(
                parent,
                selected_column,
                value,
            ),
        ).grid(row=3, column=column, sticky="w", padx=8, pady=(0, 6))

    def _toggle_raw_output(self, frame, column: int, raw_text: str) -> None:
        attribute = f"_raw_output_{column}"
        existing = getattr(frame, attribute, None)
        if existing is not None:
            existing.destroy()
            setattr(frame, attribute, None)
            return
        raw = ctk.CTkTextbox(frame, height=100)
        raw.grid(row=4, column=column, sticky="ew", padx=8, pady=6)
        raw.insert("1.0", raw_text)
        raw.configure(state="disabled")
        setattr(frame, attribute, raw)

    def _apply_candidate(self) -> None:
        state = self._state
        if state is None:
            return
        confirmed = False
        if state.apply_gate.mode == "confirm":
            confirmed = messagebox.askyesno(
                "確認套用",
                "比較結果不一致。仍要套用這個版本嗎？",
                parent=self._window,
            )
            if not confirmed:
                return
        candidate = state.candidate
        self._command_sink(
            ApplyRecipeCandidate(
                confirmed,
                uuid.uuid4().hex,
                candidate.parent_version if candidate is not None else "",
                candidate.iteration if candidate is not None else 0,
            )
        )

    def _render_applied(self, state: RecipeImprovementState) -> None:
        row = self._heading("已套用", state.message)
        ctk.CTkLabel(
            self._content,
            text="目前執行中的結果不會改變；下一次執行會使用新版本。",
            anchor="w",
        ).grid(row=row, column=0, sticky="ew", padx=8, pady=12)

    def _render_applying(self, state: RecipeImprovementState) -> None:
        row = self._heading("處理中", state.message)
        progress = ctk.CTkProgressBar(self._content, mode="indeterminate")
        progress.grid(row=row, column=0, sticky="ew", padx=8, pady=18)
        progress.start()

    def _render_history(self, state: RecipeImprovementState) -> None:
        row = self._heading(
            f"{state.action_name} · 版本記錄",
            "內建版本與所有已套用的個人版本都會保留在本機。",
        )
        if state.message:
            ctk.CTkLabel(
                self._content,
                text=state.message,
                anchor="w",
                justify="left",
                wraplength=680,
                text_color="#FFB347",
            ).grid(row=row, column=0, sticky="ew", padx=8, pady=8)
            row += 1
        if state.builtin_update_available:
            update = ctk.CTkFrame(self._content, border_width=1)
            update.grid(row=row, column=0, sticky="ew", padx=8, pady=8)
            update.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                update,
                text="ClipAI 的內建 Recipe 已更新，你的個人版本不會被覆蓋。",
                anchor="w",
                justify="left",
                wraplength=500,
            ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=10)
            ctk.CTkButton(
                update,
                text="保留個人版本",
                width=120,
                command=lambda: self._command_sink(
                    KeepPersonalRecipeVersion(
                        state.action_id,
                        state.press_type,
                        uuid.uuid4().hex,
                    )
                ),
            ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))
            ctk.CTkButton(
                update,
                text="檢視內建更新",
                width=150,
                fg_color="#4A4A4A",
                command=lambda frame=update: self._toggle_builtin_update_diff(
                    frame,
                    state,
                ),
            ).grid(row=1, column=1, sticky="e", padx=12, pady=(0, 10))
            row += 1
        for revision in state.revision_history:
            frame = ctk.CTkFrame(self._content)
            frame.grid(row=row, column=0, sticky="ew", padx=8, pady=6)
            frame.grid_columnconfigure(0, weight=1)
            title = (
                "ClipAI 內建版本"
                if revision.source == "builtin"
                else f"個人版本 · {revision.created_at[:19]}"
            )
            if revision.revision_id == state.active_revision_id:
                title += " · 目前使用中"
            ctk.CTkLabel(
                frame,
                text=title,
                anchor="w",
                font=ctk.CTkFont(weight="bold"),
            ).grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 2))
            ctk.CTkLabel(
                frame,
                text=revision.validation_summary,
                anchor="w",
            ).grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
            ctk.CTkButton(
                frame,
                text="還原",
                width=90,
                state=(
                    "disabled"
                    if revision.revision_id == state.active_revision_id
                    else "normal"
                ),
                command=lambda selected=revision: self._confirm_restore(selected),
            ).grid(row=0, column=1, rowspan=2, padx=14, pady=10)
            row += 1
        ctk.CTkButton(
            self._content,
            text="返回 Recipe 清單",
            fg_color="#4A4A4A",
            command=lambda: self._command_sink(OpenRecipeImprovement()),
        ).grid(row=row, column=0, sticky="w", padx=8, pady=12)

    def _confirm_restore(self, revision) -> None:
        if not messagebox.askyesno(
            "確認還原",
            "還原後，新的執行會立即使用這個版本。要繼續嗎？",
            parent=self._window,
        ):
            return
        self._command_sink(
            RestoreRecipeVersion(
                revision.action_id,
                revision.press_type,
                revision.revision_id,
                True,
                uuid.uuid4().hex,
            )
        )

    def _toggle_builtin_update_diff(
        self,
        frame,
        state: RecipeImprovementState,
    ) -> None:
        existing = getattr(frame, "_builtin_diff", None)
        if existing is not None:
            existing.destroy()
            frame._builtin_diff = None
            return
        builtin = next(
            (
                revision
                for revision in state.revision_history
                if revision.source == "builtin"
            ),
            None,
        )
        if builtin is None:
            return
        diff = ctk.CTkTextbox(frame, height=220)
        diff.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))
        diff.insert(
            "1.0",
            "System prompt\n"
            + "\n".join(
                difflib.unified_diff(
                    state.current_system_prompt.splitlines(),
                    builtin.system_prompt.splitlines(),
                    fromfile="目前個人版本",
                    tofile="新版內建 Recipe",
                    lineterm="",
                )
            )
            + "\n\nUser prompt\n"
            + "\n".join(
                difflib.unified_diff(
                    state.current_prompt.splitlines(),
                    builtin.prompt.splitlines(),
                    fromfile="目前個人版本",
                    tofile="新版內建 Recipe",
                    lineterm="",
                )
            ),
        )
        diff.configure(state="disabled")
        frame._builtin_diff = diff

    def close(self) -> None:
        state = self._state
        if state is not None and state.stage in {"generating", "testing"}:
            choice = messagebox.askyesnocancel(
                "作業仍在進行",
                "要取消目前作業嗎？\n選「否」會讓作業在背景繼續。",
                parent=self._window,
                default=messagebox.YES,
            )
            if choice is None:
                return
            if choice:
                self._command_sink(
                    CancelRecipeImprovementOperation(state.operation_id)
                )
        self._visible = False
        self._window.withdraw()

    def _apply_windows_window_icons(self) -> None:
        try:
            self._window_icon_handles = install_clipai_window_icons(self._window)
        except (OSError, tk.TclError):
            pass

    def destroy(self) -> None:
        try:
            self._window.destroy()
        except tk.TclError:
            pass
        destroy_windows_window_icons(self._window_icon_handles)
        self._window_icon_handles = ()
