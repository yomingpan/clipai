# Minimal Inline refinement stall: 2026-09-28 follow-up

## Judgment and evidence

**Green: retain the existing owners and the bounded deadline. Confidence: medium.**
The 2026-09-27 desktop trace confirms the reported symptom, while a current
production-path Provider probe settles. The trace cannot identify which
network or task step stalled.

At 23:30:22 local time, interaction
`inline-interaction-c947ed10730445efb3b6e8d6c999264b` recorded
`stop_requested outcome=long`, `recognition_settled outcome=content_available`,
`refine_requested`, and `refine_admitted`. No `refine_settled` followed. The
user requested discard at 23:31:07, about 45 seconds later; cancellation was
accepted and the late completion ignored. Similar admitted operations at
23:01:25, 23:06:35, 23:07:15, and 23:08:51 remained pending until explicit
discard. These are content-free events in `logs/clipai.log`.

The then-current `InlineDictationCoordinator` passed no deadline to
`ProviderExecutionModule` (confirmed with `git show 5e374ca^:ClipAI/app/inline_dictation.py`).
Commits `5e374ca`, `24423b5`, and `0ce0a30` subsequently added a 75-second
deadline, settlement even when work suppresses cancellation, and an explicit
timeout recovery message and trace outcome. These changes were not loaded by
the desktop process that produced the 2026-09-27 events.

On 2026-09-28, `scripts/probe_inline_provider_refinement.py` sent the
SHA-matched fixed fixture through the current selected Action, prompt builder,
Gemini binding, transport, result processor, and Inline coordinator. With
network permission, it settled in 3.76 seconds with nonempty output, no Paste,
and no saved response text. Report:
`artifacts/inline-live-provider-refine-20260928-escalated.json`. The first run
inside the restricted sandbox reported `ProviderUnavailableError` after 1.3
seconds; it does not establish a product failure. The probe bypasses WebView
recognition, physical keys, Tk rendering, and target insertion. A nonempty
response that happens to match the fixture establishes settlement, not the
quality of editing.

Focused regression command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\app\test_inline_dictation.py tests\app\test_provider_execution.py tests\app\test_runtime_voice_input.py -k 'refine or provider_operation_deadline or provider_deadline'
```

Result: 13 passed, 53 deselected. This includes a short synthetic Provider
stall that must leave refining through the timeout callback, plus controller
recovery and identity matching. Architecture tests: 53 passed.

## Ownership and intervention

- `VoiceInputController` owns the Inline interaction phase and the decision to
  leave refining. `ProviderExecutionModule` owns the async request and its
  deadline; `InlineDictationCoordinator` connects the Action to a typed
  settlement. The UI only renders the accepted transition.
- Bounded settlement is a reusable Provider capability, not a special UI
  timer. No separate Provider queue, Inline state flag, or UI timeout owner is
  warranted.
- The failure boundary is between accepted Provider work and its terminal
  callback. The older missing deadline allowed an indefinitely pending
  interaction. The current contract prevents that state and preserves the raw
  text for an explicit recovery choice.
- The safeguard is the existing timeout and cancellation-resistant regression
  tests, plus content-free `refine_admitted` / `refine_settled` trace correlation.

The debt multiplier would be another owner or timer for the same refinement
state. Three more special-case fixes would produce conflicting cancellation,
late-result, and UI-close rules. The lowest-risk option is to keep the existing
deadline and typed settlement; a new state machine or Provider rewrite would
add cost without evidence of a surviving ownership defect. This choice is
reversible if a current desktop trace shows `refine_settled` without the
matching UI transition.

**ADR note.** Context: admitted Inline refinement lacked a terminal bound.
Decision: preserve Provider task ownership and controller phase ownership;
enforce a deadline and terminal recovery. Alternative: UI timer or parallel
runtime registry, rejected for duplicated ownership. Consequence: timeout
does not prove whether the external Provider request or local task stalled.
Review trigger: a post-`0ce0a30` desktop interaction remains on `整理中` for
more than 75 seconds, or records `refine_settled` while the matching view stays
there. That trace is the highest-value next evidence.
