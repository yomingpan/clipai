from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

RoundKind = Literal["follow_up", "deep_think"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PopupRound:
    round_index: int
    kind: RoundKind
    prompt_text: str
    result_text: str
    model: str
    created_at: str = field(default_factory=_utc_now_iso)


@dataclass
class PopupSession:
    action_id: str
    action_name: str
    original_input: str
    latest_result: str
    action_press_type: str = "short"
    variant_applied: bool = False
    resolved_action_def: dict[str, object] = field(default_factory=dict)
    input_loading: bool = False
    result_loading: bool = False
    session_id: str = field(default_factory=lambda: str(uuid4()))
    rounds: list[PopupRound] = field(default_factory=list)
    round_count: int = 0
    max_rounds: int = 5
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)

    def can_continue(self) -> bool:
        return self.round_count < self.max_rounds

    def mark_input_ready(self, original_input: str) -> None:
        self.original_input = original_input
        self.input_loading = False
        self.updated_at = _utc_now_iso()

    def mark_result_ready(self, content: str) -> None:
        self.latest_result = content
        self.result_loading = False
        self.updated_at = _utc_now_iso()

    def begin_chained_action(
        self,
        *,
        action_id: str,
        action_name: str,
        original_input: str,
        action_press_type: str,
        variant_applied: bool,
        resolved_action_def: dict[str, object],
        placeholder: str = "Connecting...",
    ) -> None:
        self.action_id = action_id
        self.action_name = action_name
        self.original_input = original_input
        self.action_press_type = action_press_type
        self.variant_applied = variant_applied
        self.resolved_action_def = dict(resolved_action_def)
        self.input_loading = False
        self.latest_result = placeholder
        self.result_loading = True
        self.updated_at = _utc_now_iso()

    def start_round(self, *, kind: RoundKind, prompt_text: str, model: str, placeholder: str = "Connecting...") -> None:
        if not self.can_continue():
            raise ValueError("Popup follow-up limit reached.")
        self.rounds.append(
            PopupRound(
                round_index=self.round_count + 1,
                kind=kind,
                prompt_text=prompt_text,
                result_text=self.latest_result,
                model=model,
            )
        )
        self.latest_result = placeholder
        self.result_loading = True
        self.round_count += 1
        self.updated_at = _utc_now_iso()

    def push_result(self, *, kind: RoundKind, prompt_text: str, new_result: str, model: str) -> None:
        self.start_round(kind=kind, prompt_text=prompt_text, model=model, placeholder=new_result)
        self.mark_result_ready(new_result)

    def as_context_text(self) -> str:
        parts = [f"[Original Input]\n{self.original_input}", f"[Latest Result]\n{self.latest_result}"]
        for item in self.rounds:
            parts.append(
                f"[Round {item.round_index} - {item.kind}]\n"
                f"Prompt: {item.prompt_text}\n"
                f"Result: {item.result_text}"
            )
        return "\n\n".join(parts)

    def render_full_text(self) -> str:
        parts = [self.latest_result]
        for item in self.rounds:
            parts.append(
                f"--- round {item.round_index} ---\n"
                f"{item.kind}: {item.prompt_text}\n"
                f"{item.result_text}"
            )
        return "\n\n".join(parts)
