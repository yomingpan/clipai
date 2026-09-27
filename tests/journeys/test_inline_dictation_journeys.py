"""Reproducible typed-command journeys for the current inline safety boundary.

These cases deliberately assert only observed side-effect admission. Paste
settlement and device insertion require separate evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import random
import uuid

import pytest

from ClipAI.app.runtime_voice_input import VoiceInputRuntimeModule
from ClipAI.core.commands import (
    CancelInlineDictation,
    ConfirmInlineDictation,
    InlineDictationRefineCancelAccepted,
    InlineDictationRefineCancelTimedOut,
    InlineDictationRefineSettled,
    PasteOperationCompleted,
    ToggleInlineDictation,
    VoiceEngineEventReceived,
)
from ClipAI.core.models import InlineOrigin, PasteOutcome, PasteRequest, PasteTarget
from ClipAI.core.voice import VoiceEngineEnded, VoiceEngineFinalSegment, VoiceEngineListening
from ClipAI.platform.keyboard import SystemKeyboardOutput
from ClipAI.services.clipboard_transaction import ClipboardTransactionCoordinator
from ClipAI.services.paste_operation import PasteOperationCoordinator
from ClipAI.services.voice_input import VoiceInputController


TARGET = PasteTarget("controlled:1", 41, "Controlled editor", "private", 1)


class Engine:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def start_capture(self, capture_id, language, *, sequence_start=0) -> None:
        self.calls.append(("start", capture_id, language, sequence_start))

    def stop_capture(self, capture_id) -> None:
        self.calls.append(("stop", capture_id))

    def cancel_capture(self, capture_id) -> None:
        self.calls.append(("cancel", capture_id))


class Workflows:
    def controller_for(self, _workflow_id):
        return None


class Presenter:
    def __init__(self) -> None:
        self.choices: list[str] = []
        self.closes: list[tuple[bool, str]] = []
        self.paste_outcomes: list[tuple[str, PasteOutcome, str]] = []
        self.interaction_ids: list[str] = []
        self.cancel_unconfirmed: list[tuple[str, str]] = []

    def open_inline_dictation(self, interaction_id="", _mode="choice") -> None:
        self.interaction_ids.append(interaction_id)

    def update_inline_dictation(self, _projection) -> None:
        pass

    def present_inline_choice(self, _interaction_id: str, text: str, allow_refine: bool = True, message: str = "") -> None:
        self.choices.append(text)

    def present_inline_paste_pending(self, _interaction_id: str) -> None:
        pass

    def present_inline_paste_cancelling(self, _interaction_id: str) -> None:
        pass

    def present_inline_paste_outcome(self, interaction_id: str, outcome: PasteOutcome, text: str) -> None:
        self.paste_outcomes.append((interaction_id, outcome, text))

    def present_inline_refining(self, _interaction_id: str) -> None:
        pass

    def present_inline_refinement_pending(self, _interaction_id: str) -> None:
        pass

    def present_inline_cancel_unconfirmed(self, _interaction_id: str, _text: str) -> None:
        self.cancel_unconfirmed.append((_interaction_id, _text))

    def present_inline_recovery(self, _interaction_id: str, _text: str, _message: str) -> None:
        pass

    def present_inline_copy_state(self, _interaction_id: str, _state: str) -> None:
        pass

    def close_inline_dictation(self, *, flash_failure=False, message="", interaction_id="") -> None:
        self.closes.append((flash_failure, message))


class VirtualTimer:
    def __init__(self, due: float, callback) -> None:
        self.due = due
        self.callback = callback
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class VirtualClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.timers: list[VirtualTimer] = []

    def schedule(self, delay: float, callback) -> VirtualTimer:
        timer = VirtualTimer(self.now + delay, callback)
        self.timers.append(timer)
        return timer

    def advance(self, seconds: float) -> None:
        target = self.now + seconds
        while pending := [timer for timer in self.timers if not timer.cancelled and timer.due <= target]:
            timer = min(pending, key=lambda item: item.due)
            timer.cancelled = True
            self.now = timer.due
            timer.callback()
        self.now = target


@dataclass(frozen=True)
class Step:
    stage: str
    action: str
    text: str = ""


class JourneyClipboard:
    def __init__(self) -> None:
        self.value = "prior clipboard"
        self.sequence = 1
        self.restore_fails = False

    def snapshot(self) -> str:
        return self.value

    def sequence_number(self) -> int:
        return self.sequence

    def write_transient_text(self, text: str) -> None:
        self.value = text
        self.sequence += 1

    def restore_if_unchanged(self, snapshot: str, expected_sequence: int) -> bool:
        if self.restore_fails:
            raise OSError("restore unavailable")
        if self.sequence != expected_sequence:
            return False
        self.value = snapshot
        self.sequence += 1
        return True


class Journey:
    def __init__(self, *, with_paste_owner: bool = False, mode: str = "choice") -> None:
        self.engine = Engine()
        self.presenter = Presenter()
        self.output_requests: list[tuple[str, PasteTarget, bool, str, str]] = []
        self.clock = VirtualClock()
        self.commands: list[object] = []
        self.foreground = TARGET
        self.mode = mode
        self.clipboard = JourneyClipboard()
        self.dispatches: list[tuple[PasteTarget, str]] = []
        self.target_valid = True
        self.target_focus_allowed = True
        self.activated_target: PasteTarget | None = None
        self.paste_completions: list[PasteOperationCompleted] = []
        self.paste_owner = (
            PasteOperationCoordinator(
                clipboard_transactions=ClipboardTransactionCoordinator(self.clipboard),
                dispatcher=SystemKeyboardOutput(
                    modifier_is_pressed=lambda _modifier: False,
                    target_is_valid=lambda _target: self.target_valid,
                    activate_target=self._activate_target,
                    target_is_foreground=lambda target: self.target_focus_allowed and self.activated_target == target,
                    target_activation_timeout_sec=0,
                    paste_shortcut=lambda: self.dispatches.append((self.activated_target, self.clipboard.value)),
                    paste_settle_sec=0,
                    wait=lambda _seconds: None,
                ),
                completion_sink=self._paste_completed,
            )
            if with_paste_owner else None
        )
        self.controller = VoiceInputController(enabled=True)
        self.runtime = VoiceInputRuntimeModule(
            controller=self.controller,
            engine=self.engine,
            workflows=Workflows(),
            paste_target_reader=lambda: self.foreground,
            inline_input_mode_reader=lambda: self.mode,
            inline_presenter=self.presenter,
            paste_inline=self._request_output,
            cancel_inline_paste=self._cancel_paste,
            cancel_inline_refinement=lambda _operation_id: True,
            dispatch=self.commands.append,
            watchdog_schedule=self.clock.schedule,
            monotonic_clock=lambda: self.clock.now,
        )
        self.capture_id = ""
        self.interaction_id = ""
        self.stage = "not_started"
        self.trace: list[dict[str, object]] = []

    def _activate_target(self, target: PasteTarget) -> bool:
        self.activated_target = target
        return self.target_focus_allowed

    def _request_output(self, text: str, target: PasteTarget, refine: bool, interaction_id: str, operation_id: str) -> None:
        self.output_requests.append((text, target, refine, interaction_id, operation_id))
        if not refine and self.paste_owner is not None:
            assert self.paste_owner.admit(PasteRequest(operation_id, "", text, target, InlineOrigin(interaction_id))), self._context()

    def _cancel_paste(self, operation_id: str) -> None:
        if self.paste_owner is not None:
            self.paste_owner.request_cancel(operation_id)

    def _paste_completed(self, completion: PasteOperationCompleted) -> None:
        self.paste_completions.append(completion)
        self.runtime.handle_inline_paste_completion(completion)

    def apply(self, step: Step) -> None:
        self.stage = step.stage
        if step.action == "start":
            assert self.runtime.handle(ToggleInlineDictation()), self._context()
            self.capture_id = str(self.engine.calls[-1][1])
            self.interaction_id = self.presenter.interaction_ids[-1]
        elif step.action == "listening":
            self.runtime.handle(VoiceEngineEventReceived(VoiceEngineListening(self.capture_id)))
        elif step.action == "final":
            self.runtime.handle(VoiceEngineEventReceived(VoiceEngineFinalSegment(self.capture_id, 0, step.text)))
        elif step.action in {"stop", "stop_short", "stop_long"}:
            assert self.runtime.handle(ToggleInlineDictation("long" if step.action == "stop_long" else "short")), self._context()
        elif step.action == "change_mode":
            self.mode = step.text
        elif step.action == "ended":
            self.runtime.handle(VoiceEngineEventReceived(VoiceEngineEnded(self.capture_id)))
        elif step.action == "choose_raw":
            assert self.runtime.handle(ConfirmInlineDictation(self.interaction_id, False)), self._context()
        elif step.action == "choose_refine":
            assert self.runtime.handle(ConfirmInlineDictation(self.interaction_id, True)), self._context()
        elif step.action == "refine_failed":
            assert self.runtime.handle(InlineDictationRefineSettled(self.interaction_id, error=True, operation_id=self.output_requests[0][4])), self._context()
        elif step.action == "refine_success":
            assert self.runtime.handle(InlineDictationRefineSettled(self.interaction_id, step.text, operation_id=self.output_requests[0][4])), self._context()
        elif step.action == "discard":
            assert self.runtime.handle(CancelInlineDictation(self.interaction_id)), self._context()
        elif step.action == "late_refine":
            self.runtime.handle(InlineDictationRefineSettled(self.interaction_id, step.text, operation_id=self.output_requests[0][4]))
        elif step.action == "foreground_change":
            self.foreground = PasteTarget("controlled:other", 42, "Other editor", "private", 2)
        elif step.action == "advance_120s":
            self.clock.advance(120.0)
            while self.commands:
                self.runtime.handle(self.commands.pop(0))
        else:
            raise AssertionError(f"unknown journey action: {step.action}")
        self.trace.append({
            "stage": self.stage,
            "action": step.action,
            "capture_id": self.capture_id,
            "interaction_id": self.interaction_id,
            "monotonic_ms": round(self.clock.now * 1000),
            "paste_requests": sum(not request[2] for request in self.output_requests),
        })

    def assert_paste_count(self, count: int) -> None:
        actual = sum(not refine for _text, _target, refine, _identity, _operation_id in self.output_requests)
        assert actual == count, self._context()

    def settle_paste(self, state: str, *, interaction_id: str | None = None, operation_id: str | None = None) -> bool:
        assert self.output_requests, self._context()
        requested = self.output_requests[-1]
        outcome = PasteOutcome(
            state,
            "dispatched_unconfirmed" if state == "dispatched_unconfirmed" else "not_dispatched",
            "restored" if state == "dispatched_unconfirmed" else "not_required",
        )
        return self.runtime.handle_inline_paste_completion(PasteOperationCompleted(
            operation_id or requested[4], "", outcome, InlineOrigin(interaction_id or requested[3]),
        ))

    def _context(self) -> str:
        operation_ids = [request[4] for request in self.output_requests]
        return f"stage={self.stage} capture_id={self.capture_id} interaction_id={self.interaction_id} operation_ids={operation_ids!r}"


@pytest.mark.parametrize(
    ("steps", "paste_count"),
    [
        ((Step("start", "start"), Step("listening", "listening"), Step("speech", "final", "spoken"),
          Step("stop", "stop"), Step("recognition", "ended"), Step("raw", "choose_raw")), 1),
        ((Step("start", "start"), Step("speech", "final", "spoken"), Step("stop", "stop"),
          Step("recognition", "ended"), Step("refine", "choose_refine"),
          Step("provider_failure", "refine_failed")), 0),
        ((Step("start", "start"), Step("speech", "final", "spoken"), Step("stop", "stop"),
          Step("recognition", "ended"), Step("refine", "choose_refine"),
          Step("discard", "discard"), Step("late_provider", "late_refine", "late")), 0),
        ((Step("start", "start"), Step("speech", "final", "spoken"), Step("stop", "stop"),
          Step("recognition", "ended"), Step("refine", "choose_refine"),
          Step("provider_success", "refine_success", "polished")), 1),
        ((Step("start", "start"), Step("stop", "stop"), Step("no_speech", "ended")), 0),
        ((Step("start", "start"), Step("listening", "listening"),
          Step("deadline", "advance_120s"), Step("speech", "final", "late words"),
          Step("recognition", "ended")), 0),
    ],
)
def test_replayable_inline_journey(steps: tuple[Step, ...], paste_count: int) -> None:
    journey = Journey()
    for step in steps:
        journey.apply(step)
    journey.assert_paste_count(paste_count)


def test_paste_oracle_detects_an_injected_discard_aftereffect() -> None:
    journey = Journey()
    for step in (Step("start", "start"), Step("speech", "final", "spoken"),
                 Step("stop", "stop"), Step("recognition", "ended"), Step("discard", "discard")):
        journey.apply(step)
    journey.assert_paste_count(0)

    # Mutation proof: a broken callback admitting Paste after discard fails the
    # same oracle and reports the current stage and capture identity.
    journey.stage = "mutated_late_provider"
    journey.output_requests.append(("spoken", TARGET, False, journey.interaction_id, "mutated-op"))
    with pytest.raises(AssertionError, match=r"stage=mutated_late_provider capture_id=inline-"):
        journey.assert_paste_count(0)


def test_replay_trace_contains_stages_and_ids_without_dictated_content() -> None:
    journey = Journey()
    for step in (Step("start", "start"), Step("speech", "final", "private dictated words"),
                 Step("stop", "stop"), Step("recognition", "ended"), Step("raw", "choose_raw")):
        journey.apply(step)
    trace = json.dumps(journey.trace, ensure_ascii=False)

    assert "private dictated words" not in trace
    assert "private dictated words" not in journey._context()
    assert journey.trace[-1]["interaction_id"] == journey.interaction_id
    assert journey.trace[-1]["paste_requests"] == 1


def test_frozen_target_is_used_after_foreground_changes() -> None:
    journey = Journey()
    for step in (Step("start", "start"), Step("target_switched", "foreground_change"),
                 Step("speech", "final", "spoken"), Step("stop", "stop"),
                 Step("recognition", "ended"), Step("raw", "choose_raw")):
        journey.apply(step)
    journey.assert_paste_count(1)
    assert journey.output_requests[0][1] == TARGET


@pytest.mark.parametrize("stop_action, expects_refinement", [("stop_short", False), ("stop_long", True)])
def test_minimal_mode_stop_gesture_uses_one_frozen_delivery_path(stop_action: str, expects_refinement: bool) -> None:
    journey = Journey(mode="minimal")
    for step in (Step("start", "start"), Step("mode_changed", "change_mode", "choice"),
                 Step("speech", "final", "spoken words"), Step("stop", stop_action),
                 Step("recognition", "ended")):
        journey.apply(step)

    assert journey.presenter.choices == []
    assert len(journey.output_requests) == 1
    assert journey.output_requests[0][2] is expects_refinement
    if expects_refinement:
        journey.apply(Step("provider_success", "refine_success", "polished words"))
        assert journey.output_requests[1][0] == "polished words"
        journey.assert_paste_count(1)
    else:
        journey.assert_paste_count(1)


def test_duplicate_and_stale_paste_acknowledgements_do_not_settle_a_new_interaction() -> None:
    journey = Journey()
    for step in (Step("start", "start"), Step("speech", "final", "first"),
                 Step("stop", "stop"), Step("recognition", "ended"), Step("raw", "choose_raw")):
        journey.apply(step)
    first_id, first_operation = journey.output_requests[-1][3:5]
    assert not journey.settle_paste("failed", operation_id="wrong-operation")
    assert not journey.settle_paste("failed", interaction_id="wrong-interaction")
    assert journey.presenter.paste_outcomes == []
    assert journey.settle_paste("dispatched_unconfirmed")
    assert not journey.settle_paste("dispatched_unconfirmed")
    assert len(journey.presenter.paste_outcomes) == 1
    assert journey.runtime.handle(ToggleInlineDictation())
    second_id = journey.controller.active_inline_capture_id()
    assert second_id is not None and journey.presenter.interaction_ids[-1] != first_id
    assert not journey.settle_paste("failed", interaction_id=first_id, operation_id=first_operation)
    assert len(journey.presenter.paste_outcomes) == 1


def _admit_raw_paste(journey: Journey) -> tuple[str, str]:
    for step in (Step("start", "start"), Step("speech", "final", "spoken words"),
                 Step("stop", "stop"), Step("recognition", "ended"), Step("raw", "choose_raw")):
        journey.apply(step)
    assert journey.paste_owner is not None and journey.output_requests, journey._context()
    return journey.output_requests[-1][3:5]


def test_journey_through_real_paste_and_clipboard_owners_restores_prior_content() -> None:
    journey = Journey(with_paste_owner=True)
    interaction_id, operation_id = _admit_raw_paste(journey)
    journey.stage = "paste_execution"
    journey.paste_owner.execute(operation_id)

    assert journey.dispatches == [(TARGET, "spoken words")], journey._context()
    assert journey.clipboard.value == "prior clipboard", journey._context()
    assert len(journey.paste_completions) == 1
    assert journey.paste_completions[0].outcome.state == "dispatched_unconfirmed"
    assert journey.presenter.paste_outcomes == [
        (interaction_id, journey.paste_completions[0].outcome, "spoken words")
    ]


def test_journey_real_paste_owner_dispatches_only_to_start_frozen_target() -> None:
    journey = Journey(with_paste_owner=True)
    for step in (Step("start", "start"), Step("target_switched", "foreground_change"),
                 Step("speech", "final", "spoken words"), Step("stop", "stop"),
                 Step("recognition", "ended"), Step("raw", "choose_raw")):
        journey.apply(step)
    journey.stage = "paste_after_foreground_change"
    journey.paste_owner.execute(journey.output_requests[-1][4])

    assert journey.dispatches == [(TARGET, "spoken words")], journey._context()
    assert journey.activated_target == TARGET


@pytest.mark.parametrize("failure", ["target_gone", "focus_refused"])
def test_journey_target_failure_keeps_recovery_and_never_dispatches(failure: str) -> None:
    journey = Journey(with_paste_owner=True)
    _interaction_id, operation_id = _admit_raw_paste(journey)
    if failure == "target_gone":
        journey.target_valid = False
    else:
        journey.target_focus_allowed = False
    journey.stage = failure
    journey.paste_owner.execute(operation_id)

    assert journey.dispatches == [], journey._context()
    assert journey.clipboard.value == "prior clipboard", journey._context()
    assert journey.paste_completions[0].outcome.state == "failed"
    assert journey.presenter.paste_outcomes[0][2] == "spoken words"


def test_journey_discard_before_dispatch_cancels_without_clipboard_mutation() -> None:
    journey = Journey(with_paste_owner=True)
    _interaction_id, operation_id = _admit_raw_paste(journey)
    journey.stage = "discard_before_dispatch"
    assert journey.runtime.cancel_inline_dictation(), journey._context()

    assert not journey.paste_owner.request_cancel(operation_id)
    assert journey.paste_completions[0].operation_id == operation_id
    assert journey.paste_completions[0].outcome.state == "cancelled"
    assert journey.dispatches == []
    assert journey.clipboard.value == "prior clipboard"


def test_journey_clipboard_cleanup_failure_preserves_dispatch_uncertainty() -> None:
    journey = Journey(with_paste_owner=True)
    _interaction_id, operation_id = _admit_raw_paste(journey)
    journey.clipboard.restore_fails = True
    journey.stage = "clipboard_cleanup"
    journey.paste_owner.execute(operation_id)

    assert journey.dispatches == [(TARGET, "spoken words")]
    assert journey.paste_completions[0].outcome.state == "cleanup_failed"
    assert journey.paste_completions[0].outcome.delivery == "dispatched_unconfirmed"
    assert journey.presenter.paste_outcomes[0][1].state == "cleanup_failed"


@pytest.mark.parametrize("seed", range(20))
def test_seeded_discard_races_quarantine_all_late_provider_events(seed: int, monkeypatch) -> None:
    rng = random.Random(seed)
    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID(int=rng.getrandbits(128)))
    journey = Journey()
    for step in (Step("start", "start"), Step("speech", "final", "spoken words"),
                 Step("stop", "stop"), Step("recognition", "ended"),
                 Step("refine", "choose_refine"), Step("discard", "discard")):
        journey.apply(step)
    operation_id = journey.output_requests[0][4]
    admission = next(command for command in journey.commands if isinstance(command, InlineDictationRefineCancelAccepted))
    callbacks = [
        admission,
        InlineDictationRefineSettled(journey.interaction_id, "late polished words", operation_id=operation_id),
        InlineDictationRefineSettled(journey.interaction_id, error=True, operation_id=operation_id),
    ]
    rng.shuffle(callbacks)
    journey.stage = "late_provider_interleaving"
    for callback in callbacks:
        journey.runtime.handle(callback)

    journey.assert_paste_count(0)
    assert journey.runtime.handle(ToggleInlineDictation()), f"seed={seed} {journey._context()}"
    assert journey.presenter.interaction_ids[-1] != journey.interaction_id, f"seed={seed} {journey._context()}"


def test_virtual_deadline_exposes_unconfirmed_provider_cancel_without_paste() -> None:
    journey = Journey()
    for step in (Step("start", "start"), Step("speech", "final", "complete original"),
                 Step("stop", "stop"), Step("recognition", "ended"),
                 Step("refine", "choose_refine"), Step("discard", "discard")):
        journey.apply(step)
    admission = next(command for command in journey.commands if isinstance(command, InlineDictationRefineCancelAccepted))
    journey.commands.remove(admission)
    journey.clock.advance(6.1)
    deadline = next(command for command in journey.commands if isinstance(command, InlineDictationRefineCancelTimedOut))
    assert journey.runtime.handle(deadline)

    assert journey.presenter.cancel_unconfirmed == [(journey.interaction_id, "complete original")]
    journey.assert_paste_count(0)
    assert not journey.runtime.handle(ToggleInlineDictation())
    assert journey.runtime.handle(admission)
    assert journey.runtime.handle(ToggleInlineDictation())
