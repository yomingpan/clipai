from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
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


@dataclass(frozen=True)
class PopupSessionSnapshot:
    session_id: str
    action_id: str
    action_name: str
    original_input: str
    latest_result: str
    action_press_type: str
    variant_applied: bool
    resolved_action_def: dict[str, object]
    input_loading: bool
    result_loading: bool
    current_provider: str
    current_model: str
    rounds: tuple[PopupRound, ...]
    round_count: int
    max_rounds: int
    created_at: str
    updated_at: str

    def can_continue(self) -> bool:
        return self.round_count < self.max_rounds


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
    current_provider: str = ""
    current_model: str = ""
    session_id: str = field(default_factory=lambda: str(uuid4()))
    rounds: list[PopupRound] = field(default_factory=list)
    round_count: int = 0
    max_rounds: int = 5
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False, compare=False)

    def can_continue(self) -> bool:
        with self._lock:
            return self.round_count < self.max_rounds

    def is_ready_for_chaining(self) -> bool:
        with self._lock:
            return (
                not self.input_loading
                and not self.result_loading
                and bool(self.latest_result.strip())
            )

    def snapshot(self) -> PopupSessionSnapshot:
        with self._lock:
            return PopupSessionSnapshot(
                session_id=self.session_id,
                action_id=self.action_id,
                action_name=self.action_name,
                original_input=self.original_input,
                latest_result=self.latest_result,
                action_press_type=self.action_press_type,
                variant_applied=self.variant_applied,
                resolved_action_def=dict(self.resolved_action_def),
                input_loading=self.input_loading,
                result_loading=self.result_loading,
                current_provider=self.current_provider,
                current_model=self.current_model,
                rounds=tuple(self.rounds),
                round_count=self.round_count,
                max_rounds=self.max_rounds,
                created_at=self.created_at,
                updated_at=self.updated_at,
            )

    def mark_input_ready(self, original_input: str) -> None:
        with self._lock:
            self.original_input = original_input
            self.input_loading = False
            self.updated_at = _utc_now_iso()

    def mark_result_ready(self, content: str) -> None:
        with self._lock:
            self.latest_result = content
            self.result_loading = False
            self.updated_at = _utc_now_iso()

    def append_result_chunk(self, chunk: str) -> None:
        with self._lock:
            if self.result_loading:
                self.result_loading = False
                self.latest_result = ""
            self.latest_result += chunk
            self.updated_at = _utc_now_iso()

    def update_result_metadata(self, *, provider: str, model: str) -> None:
        with self._lock:
            self.current_provider = provider
            self.current_model = model
            self.updated_at = _utc_now_iso()

    def update_action_metadata(
        self,
        *,
        action_id: str,
        action_name: str,
        action_press_type: str,
        variant_applied: bool,
        resolved_action_def: dict[str, object],
    ) -> None:
        with self._lock:
            self.action_id = action_id
            self.action_name = action_name
            self.action_press_type = action_press_type
            self.variant_applied = variant_applied
            self.resolved_action_def = dict(resolved_action_def)
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
        with self._lock:
            self.action_id = action_id
            self.action_name = action_name
            self.original_input = original_input
            self.action_press_type = action_press_type
            self.variant_applied = variant_applied
            self.resolved_action_def = dict(resolved_action_def)
            self.input_loading = False
            self.latest_result = placeholder
            self.result_loading = True
            self.current_provider = ""
            self.current_model = ""
            self.updated_at = _utc_now_iso()

    def start_round(self, *, kind: RoundKind, prompt_text: str, model: str, placeholder: str = "Connecting...") -> None:
        with self._lock:
            if self.round_count >= self.max_rounds:
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
        state = self.snapshot()
        parts = [f"[Original Input]\n{state.original_input}", f"[Latest Result]\n{state.latest_result}"]
        for item in state.rounds:
            parts.append(
                f"[Round {item.round_index} - {item.kind}]\n"
                f"Prompt: {item.prompt_text}\n"
                f"Result: {item.result_text}"
            )
        return "\n\n".join(parts)

    def render_full_text(self) -> str:
        state = self.snapshot()
        parts = [state.latest_result]
        for item in state.rounds:
            parts.append(
                f"--- round {item.round_index} ---\n"
                f"{item.kind}: {item.prompt_text}\n"
                f"{item.result_text}"
            )
        return "\n\n".join(parts)
