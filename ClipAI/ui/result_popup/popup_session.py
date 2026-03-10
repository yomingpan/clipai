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
    session_id: str = field(default_factory=lambda: str(uuid4()))
    rounds: list[PopupRound] = field(default_factory=list)
    round_count: int = 0
    max_rounds: int = 5
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)

    def can_continue(self) -> bool:
        return self.round_count < self.max_rounds

    def push_result(self, *, kind: RoundKind, prompt_text: str, new_result: str, model: str) -> None:
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
        self.latest_result = new_result
        self.round_count += 1
        self.updated_at = _utc_now_iso()

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
                f"{item.result_text}"
            )
        return "\n\n".join(parts)
