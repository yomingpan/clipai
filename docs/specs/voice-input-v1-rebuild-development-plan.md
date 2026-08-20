# Voice Input V1 — Clean Rebuild Development Plan

> Superseded for Popup lifetime and permission behavior by
> `single-popup-voice-stability-adr.md`. Historical coexistence and
> collision-placement sections remain only as implementation history.

Status: Approved product and architecture plan  
Implementation baseline: `develop` at the implementation session's start  
Source of research evidence: the experimental `develop...HEAD` Voice Input branch  
Audience: the new session agent responsible for implementation

## 1. Handoff directive

Implement Voice Input from a clean branch created from `develop`. Do not repair,
revert in place, or cherry-pick the experimental Voice Input commits. The
experimental branch is research evidence only: use it to understand Browser
Speech/WebView2 behavior, microphone-release defects, process protocol hazards,
and missing test cases. Recreate any useful behavior only after the new
contracts and state ownership described here exist.

Before changing production code, the implementation agent must:

1. Read the repository agent contract, product philosophy, architecture
   boundaries, and testing strategy.
2. Confirm the worktree is clean and resolve the current `develop` commit.
3. Create a new `codex/`-prefixed branch from `develop`.
4. Preserve this approved plan while changing baselines and add it as the first
   documentation-only commit on the clean implementation branch. Do not
   cherry-pick the experimental feature commits to obtain it.
5. Confirm that none of the experimental Voice Input production modules are in
   the baseline.
6. Run the existing unit and architecture tests and record the baseline.
7. Follow the commit sequence in this document. Do not combine stages merely to
   reduce commit count.

The implementation is complete only when every Definition of Done item and the
manual Windows release matrix have evidence. Passing fake-engine unit tests is
not sufficient.

## 2. Answer-first product definition

Voice Input V1 is a Windows cross-application dictation input method. The user
holds `Ctrl+Alt+W`, speaks, releases the keys, reviews an editable transcript in
a ClipAI Popup, and explicitly sends the reviewed content back to the original
external application. Within the Voice Draft, `Ctrl+V` always sends the reviewed
content externally; `Ctrl+Enter` only switches Editing and Reading presentation.

Voice Input is not an automatic AI Action, not an implicit Follow-up mechanism,
and not a background recorder. Existing ClipAI Actions remain an explicit,
secondary operation that the user may apply to the reviewed Voice Draft.

The core product promises are:

- Immediate and truthful visible feedback for every intent.
- The microphone is used only during an explicitly active Push-to-Talk capture.
- Content is never pasted into a guessed or newly foregrounded target.
- Late setup, engine, UI, provider, and paste completions cannot affect a newer
  operation or Workflow.
- Draft content is ephemeral and is not persisted across application restarts.
- The only supported V1 engine path is controlled Edge WebView2 Browser Speech
  on Windows 10/11.
- The first supported languages are `zh-TW` and `en-US`.

## 3. Decision ledger

These decisions are approved. An implementation agent must not reopen them
without presenting new evidence that makes the plan unsafe or impossible.

### 3.1 Primary interaction

- Default shortcut: `Ctrl+Alt+W`.
- Gesture: Push-to-Talk only. Press starts; release requests stop and
  finalization.
- Release never auto-pastes. It enters Review.
- `Ctrl+V` in either Voice Draft presentation mode sends the reviewed content
  to the frozen external target. It never inserts clipboard content into the
  Popup draft.
- The Paste button explicitly sends the current semantic content to the frozen
  external target. A focused, non-editable completed result may continue to use
  `Ctrl+V` as the same external Paste intent.
- Voice Review enters Editing mode. `Ctrl+Enter` toggles between Editing and
  Reading presentation modes; Editing permits direct typing, while `Ctrl+V`
  always routes to the frozen external target.
- There is no mouse Start control in V1. Listening offers explicit Stop and
  Cancel controls as safety exits.

### 3.2 Target and focus

- A normal capture freezes the external Paste Target at the first PTT press,
  before showing or activating ClipAI UI.
- The target is validated again immediately before dispatch.
- Invalid or closed targets fail closed: preserve content, display the failure,
  and never substitute the current foreground window.
- A Voice Popup already in Review may start another capture in the same
  Workflow and reuse its valid frozen target.
- A PTT intent originating from a general result Popup, setup surface, Tray, or
  other ClipAI window is rejected. It does not use the last-seen external
  window.
- During Listening and Finalizing, the Voice Popup is visible without taking
  keyboard focus. It activates and focuses the editor only after entering
  Review.

### 3.3 Window and Workflow behavior

- Each new Voice Input from an external target creates an independent Workflow.
- There is at most one unpinned transient Popup at a time.
- Starting a new transient Workflow closes the previous unpinned Workflow and
  cancels its active provider invocation. Late completion cannot reopen it.
- Pinned Popups remain visible and retain their independent Workflows.
- A new transient Voice Popup must avoid covering existing pinned Popups where
  practical; use the established placement policy with a deterministic offset,
  not a new window manager.
- There may be multiple visible pinned Workflows, but there is exactly one
  container-wide active microphone capture.
- A new capture is rejected while another capture is Listening or Finalizing.
  It never preempts the active capture.

### 3.4 Draft, editing, and Actions

- The Workflow owns the canonical editable Voice Draft.
- Listening and Finalizing are read-only. Interim recognition appears as a
  visually distinct projection and is not canonical content.
- Review enables selection, Copy, Paste, pinning, and explicit Actions. It
  starts in Editing mode; `Ctrl+Enter` switches to Reading mode and can switch
  back to Editing without creating another draft or Workflow state owner.
- A new capture freezes the current selection/caret. It replaces a non-empty
  selection or inserts at the caret. Moving the caret during capture cannot
  retarget that capture.
- Final recognition segments retain engine order and use one deterministic text
  joining policy owned below the UI seam.
- An explicit Action uses the current Voice Draft selection when non-empty,
  otherwise the full canonical draft. The resolved text is immutable for that
  invocation.
- Action results remain in the same Voice Workflow. Back returns to the editable
  Voice origin. Running a new Action from an earlier position truncates later
  history according to existing linear Workflow rules.
- A Paste button request or `Ctrl+V` from either Voice Review mode sends the
  currently completed and visible semantic content. Loading, failed, cancelled,
  or interim content is not pasteable.
- The footer is the persistent source of truth for Editing versus Reading mode,
  the current `Ctrl+V` meaning, `Ctrl+Enter` transition, and Reading-mode target.

### 3.5 Paste settlement

- Voice Input does not create a paste registry, paste worker owner, clipboard
  transaction, or new terminal vocabulary.
- It uses the existing Paste Operation and Output Operation owners.
- Paste is never reported as confirmed success. The legal terminal truth remains
  the repository's existing Paste terminal model.
- An unpinned Voice Popup closes only after dispatch is reported
  `dispatched_unconfirmed` and clipboard cleanup has settled.
- A pinned Voice Popup remains open after dispatch and retains its content.
- Failed, cancelled, or cleanup-failed paste keeps the Popup and content visible
  with truthful feedback.
- UI copy must say the paste instruction was sent, not that the destination
  consumed the content.

### 3.6 Setup, consent, and Tray

- First PTT while Voice Input is not ready opens a retriable first-use setup
  surface. It
  does not create a Voice Workflow, retain a Paste Target, or start capture.
- Setup explains that the microphone is active only during PTT, audio is
  processed by the configured Browser Speech provider, ClipAI does not retain
  audio, and transcript evaluation/storage is not enabled.
- The user explicitly selects Enable Microphone and completes system/browser
  permission handling.
- Setup performs a readiness check, releases all media tracks, closes the setup
  surface, restores the originating external application when safe, and tells
  the user to press PTT again.
- Focus restoration uses an operation-scoped `SetupReturnTarget`, captured by
  the existing foreground/control-surface owner before ClipAI activates. It is
  not a Paste Target, is valid only for the matching setup identity, and is
  discarded at setup terminal settlement. A stale, closed, or replaced return
  target is not activated.
- It never turns the setup press into a late recording, even if the physical
  keys still appear held.
- Dismissing or declining setup leaves Voice Input not ready. The next shortcut
  returns to setup.
- A permanently blocked permission is distinct from a dismissed setup. The UI
  provides a repair path to Windows/browser settings instead of repeatedly
  issuing an ineffective request.
- Tray projects authoritative state; it never optimistically changes its check
  state.
- Tray provides Enable Voice Input, Disable Voice Input, and Manage Microphone
  Permission actions with state-appropriate labels.
- Enable Voice Input opens the same retriable setup surface used by the first
  shortcut. Manage Microphone Permission opens the external repair path; it does
  not change ClipAI enablement state.
- Disable means ClipAI will not start capture. It does not claim to revoke an
  OS/browser permission already stored outside ClipAI.
- Disable immediately rejects new capture, cancels setup/capture, waits for real
  terminal settlement, releases media, and then projects Disabled.
- Disable discards interim recognition but preserves already-finalized and
  manually edited Voice Draft content. The retained Popup can still Copy or
  Paste, but cannot start another capture until enabled.

### 3.7 Language, engine, and persistence

- Supported languages: `zh-TW` and `en-US` only.
- First default: `zh-TW`. Persist the last successfully saved explicit choice.
- Language cannot change during an active capture. A change applies to the next
  capture.
- Backend: controlled Edge WebView2 Browser Speech only.
- Configuration must not advertise unsupported `openai`, generic browser, or
  alternate webview backends. Unknown backend values fail configuration
  validation instead of silently falling back.
- The engine seam remains replaceable, but no second production engine is built
  in V1.
- The host process may remain warm while Voice Input is enabled. Idle means no
  MediaStreamTrack, recognition session, or microphone lease exists.
- Disable and application shutdown end the host process.
- Drafts are memory-only and disappear when their Workflow closes or ClipAI
  exits. Do not write them to preferences, logs, diagnostics, temporary files,
  or evaluation records.

### 3.8 Failure and cancellation

- Browser recognition may transparently recover from a natural end/no-speech
  condition only when the controller still accepts the same capture and press
  identities and has not received the typed release/abandon event from the
  Shortcut owner. The engine adapter never reads keyboard state or autonomously
  chooses to restart.
- Release, Stop, Cancel, Popup close, Disable, listener shutdown, and application
  shutdown create an irreversible stop gate. No subsequent event can restart
  microphone use for that capture.
- No-speech at release produces Review with a clear retry message and preserves
  pre-existing draft content.
- Host/engine crash ends the capture, discards interim, preserves finalized text,
  and displays a retryable error. The next explicit PTT may rebuild the host.
  Background restart is forbidden.
- Missing key release, repeated key events, modifier release order, listener
  shutdown, and late timer callbacks all require deterministic terminal
  behavior.
- The existing Shortcut subsystem remains the sole owner of physical key truth.
  It emits identified press-started, press-ended, press-abandoned, and
  listener-stopped observations. The Voice controller owns only the resulting
  capture restart/cancellation decision. A 120-second non-configurable V1 safety
  watchdog cancels a capture that never receives a terminal press observation;
  it never synthesizes a successful release.
- `Esc` is lifecycle-aware:
  - Setup: close setup and remain not ready.
  - Listening/Finalizing: cancel the active capture, discard its interim, retain
    the earlier canonical draft, and keep the Popup.
  - Review: close the Workflow and discard the unpersisted draft.
  - Paste pending: request cancellation and wait for the Paste owner to report
    terminal truth.
- Escape handling is scoped to an active Voice Popup through the existing UI
  command queue. ClipAI must not globally suppress or reinterpret Escape while
  the non-activating Listening Popup lacks focus; physical PTT release and the
  explicit Stop/Cancel controls remain available in that state.

### 3.9 Explicit exclusions

Do not build or retain any of the following in this plan:

- Voice Evaluation Mode, keyboard/voice trials, scoring, cohorts, CSV export, or
  evaluation persistence.
- OpenAI transcription, local transcription, generic Chrome/Edge tabs, or
  automatic engine fallback.
- Audio recording or storage.
- Transcript persistence or crash recovery across application restarts.
- Automatic language detection or unverified language lists.
- User-customizable Voice shortcut.
- Click-to-start or toggle recording.
- Automatic paste on release.
- Implicit Voice Follow-up based only on Popup visibility. The later single-
  Popup ADR permits explicit `Ctrl+Alt+W` Follow-up only when that result Popup
  has confirmed focus.
- Multiple simultaneous captures or multiple microphone leases.
- Tabs, workflow switchers, background task managers, or a new Popup window
  management system.
- A new clipboard transaction mechanism, paste coordinator, provider worker,
  event bus, or session-named domain concept.
- The unrelated pip certificate/build-isolation change from the experimental
  branch.

## 4. Architecture diagnosis

### 4.1 Executive judgment

Classification: **Red for promoting or repairing the experimental branch**.  
Recommendation: **core rebuild from clean `develop` with a hard migration
boundary**.  
Confidence: **high**.  
Main reason: the experiment proves transport feasibility but duplicates
canonical draft, Workflow routing, capture, and output-operation knowledge
across service, runtime, and UI paths, while some worker completions can project
UI without the typed command queue.

This classification does not mean the entire application needs a rewrite. It
means the experimental Voice slice should not become the production foundation.
Existing Workflow, Paste, output-operation, shortcut, preference, provider, and
Popup capabilities on `develop` remain the reusable platform.

### 4.2 Triggering evidence

Observed facts from `develop...HEAD`:

- The experiment adds roughly four thousand lines across core, services, app,
  platform, UI, configuration, scripts, documentation, and tests.
- A single Voice runtime module grew to more than five hundred lines and
  coordinated capture, preferences, UI feedback, Workflow routing, copy/paste,
  evaluation, CSV work, and shutdown.
- Canonical draft/composer data appeared in a Voice coordinator, Workflow
  projection, and runtime routing fields.
- The runtime retained Workflow/composer/commit identifiers that overlap
  existing Workflow and Paste owners.
- Some preference/evaluation worker paths could call feedback or Tray sinks
  directly instead of returning a typed command to the runtime queue.
- The public command union omitted at least one enqueued Voice command while a
  private runtime command collection compensated for it.
- Configuration advertised multiple Voice backends while composition selected
  one concrete Browser Speech engine.
- The test suite used synchronous fakes for important runtime callbacks. The
  relevant unit and architecture tests passed, yet the real subprocess/JS/media
  terminal handshake remained unproved.
- Evaluation features greatly expanded the product state and privacy surface
  beyond the original Voice Input objective.

Inference, not yet measured fact:

- Duplicate draft/routing ownership is the most likely source of stale edits
  and late-event integration defects.
- Process/JS/reader-thread/app-queue settlement without one terminal contract is
  the most likely source of microphone and shutdown instability.
- Patch-level fixes would continue to enlarge a runtime module that already
  changes for unrelated product reasons.

### 4.3 Current reusable capability and protected behavior

The clean `develop` baseline already owns behavior that Voice Input must reuse:

- Shortcut press identity and physical press/release lifecycle.
- Typed application command queue.
- Workflow execution, history, foreground identity, pin, visibility, and
  provider binding.
- Selection-first semantic input for explicit Actions.
- Popup rendering and explicit operation feedback.
- Paste target validation, clipboard transaction coordination, Paste Operation
  membership, cancellation, dispatch truth, cleanup, and terminal
  acknowledgement.
- User preference persistence and authoritative Tray projection.
- Provider task ownership and non-provider blocking TaskSupervisor capacity.

The rebuild must preserve those owners and extend them through typed contracts;
it must not create Voice-specific substitutes.

### 4.4 Four-part diagnosis

#### Single owners

- `VoiceInputController`: capability enablement, setup/permission lifecycle,
  engine readiness, the single microphone lease, active capture identity,
  mapping from accepted Shortcut press identity to capture, capture restart and
  cancellation decision, provisional recognition buffer, and domain capture
  settlement. It does not own raw physical-key truth.
- `WorkflowController`: canonical editable Voice origin, insertion application,
  Action input resolution, linear successful history, displayed position, Back,
  and semantic content currently available for output.
- `WorkflowRuntimeModule`: Workflow membership, foreground identity,
  visible/headless lifetime, pin behavior, and provider binding.
- Existing Paste and Output Operation owners: target dispatch, cancellation,
  clipboard mutation/restoration, and terminal acknowledgement.
- Browser Speech adapter: subprocess, WebView, media/recognition transport, JSON
  protocol, and transport shutdown only. It does not inspect keyboard state or
  make product-level restart decisions.
- Existing Shortcut subsystem: physical key identity, held/released/abandoned
  observation, modifier-release normalization, and listener-stop truth.
- App runtime: composition, command dispatch, and execution of typed effects. It
  owns no duplicate Voice domain state.

#### Reusable capability versus exception

Voice capture is a reusable input capability targeting a typed Workflow draft;
it is not a special-case Action or provider branch. Editing versus Reading is a
UI-local presentation mode owned by the visible Workflow view; it does not
represent capture, Workflow, or Voice Draft domain state. Browser Speech is one
adapter at the engine seam. The production adapter and deterministic test adapter
make the seam real; no additional production engine is required.

#### Knowledge that must not propagate

- Browser permission/error vocabulary must not reach Popup policy as raw
  strings.
- Keyboard/physical-held truth must not enter the Browser Speech adapter.
- Widget focus/selection objects must not enter services.
- Workflow visibility must not stand in for capture or paste identity.
- Engine callbacks must not know Tray, presenters, Workflow controllers, or
  Paste coordinators.
- Voice runtime must not retain canonical draft, current presentation mode, or
  Paste membership. The presenter resets its UI-local mode only when entering a
  new Voice Review projection and preserves it across later draft revisions.
- The UI must not read engine, clipboard, keyboard listener, or target adapters.

#### Enforceable safeguards

- Immutable typed intents, events, effects, identities, snapshots, and terminal
  outcomes.
- Exhaustive application command union tests.
- Architecture tests prohibiting UI/platform imports across the established
  layer rules.
- Architecture test prohibiting TaskSupervisor/engine worker closures from
  calling presenters, Tray projection, or Workflow mutation.
- Architecture test prohibiting the speech adapter from importing or querying
  keyboard/hotkey implementations.
- Owner tests ensuring the Voice runtime has no mirrored Workflow/capture/paste
  registries.
- Exactly-once terminal contract tests for setup and capture.
- Identity isolation tests for late engine, UI edit, permission, provider, and
  Paste completions.
- Strict configuration tests that reject unsupported backend names.

### 4.5 Debt multiplier

The experimental debt multiplier is duplicated ownership plus unmanaged
concurrency. Three similar future changes—adding another engine, adding another
recording gesture, and adding persistent drafts—would each require coordinated
changes in core commands, multiple runtime flags, Workflow projection, UI state,
adapter callbacks, configuration, and scattered tests. Every change would
multiply identity combinations and make a late completion capable of mutating
the wrong Workflow. The clean rebuild prevents that multiplication by making
capture and canonical draft two explicit owners joined by one typed seam.

### 4.6 Options considered

1. Patch the experimental runtime: lowest apparent initial cost, highest
   ownership and concurrency risk, poor reversibility after merge.
2. Incrementally reshape the experimental branch: preserves more code but makes
   it difficult to prove that compatibility fields and old paths are gone.
3. Rebuild the Voice slice from `develop`: higher deliberate implementation
   cost, lowest migration ambiguity, preserves all non-Voice platform owners,
   and is fully reversible by abandoning the new branch.

Approved option: **3**.

### 4.7 Smallest rebuild boundary

Build only the new Voice capability/capture controller, the Voice-origin
extension to existing Workflow behavior, one Browser Speech adapter, the
necessary app composition/dispatch, and Popup/Tray projections. Reuse all
existing Paste, output, clipboard, provider, shortcut, preference, and Workflow
lifecycle mechanisms.

Observable completion criteria:

- No experimental Voice module or evaluation path is copied wholesale.
- Every active setup/capture has one typed identity, one transport-terminal
  report, and exactly one controller-owned domain settlement.
- The app runtime holds no mirrored Voice domain flags or registries.
- Canonical draft exists only in the owning Workflow.
- No media track survives idle, Disable, cancel, host crash, or shutdown.
- All approved user journeys and failure matrices pass.

### 4.8 Concise ADR

Context: the Voice experiment proved Edge WebView2 Browser Speech but mixed
transport, capture, draft, Workflow, UI, paste, evaluation, and concurrency
ownership.  
Decision: rebuild from `develop` using a container-wide `VoiceInputController`,
Workflow-owned canonical Voice origins, typed command/effect round-trips, and
the existing Paste/Workflow owners.  
Alternatives: patch or incrementally reshape the experiment.  
Consequences: more up-front reconstruction, smaller and enforceable interfaces,
deterministic lifecycle tests, no evaluation features, and one supported engine.
  
Review trigger: revisit before adding a second recording gesture, concurrent
capture, audio persistence, transcript persistence, automatic language
detection, or an engine whose transport needs stored audio. A second streaming
engine that satisfies the existing contract is not by itself a redesign
trigger.

### 4.9 Remaining uncertainty

- Actual WebView2 warm-start and finalization distributions on supported Windows
  machines must be measured; the SLO shape is fixed but thresholds may be
  adjusted with recorded evidence.
- Exact Windows APIs required for non-activating display and safe focus restore
  must be confirmed against existing Popup adapters.
- Browser permission persistence and repair navigation can vary by WebView2
  runtime version; manual testing must document supported behavior.

The highest-value early spike is a narrow host lifecycle test proving setup,
release of media after readiness, PTT start, stop terminal acknowledgement,
cancel, and process shutdown without building product UI.

## 5. Target module design

Use the repository's definition of a deep module: small interface, substantial
behavior behind it, and tests through the same interface used by callers.

### 5.1 Core domain contracts

Add immutable domain concepts for:

- Voice setup identity.
- Voice capture identity.
- Supported Voice language.
- Capability/setup state.
- Capture phase and terminal outcome.
- Frozen Workflow draft target containing Workflow identity, expected origin
  revision, and insertion range—not a widget reference.
- Typed engine events for setup ready/blocked/failed, capture listening,
  interim, sequenced final segment, transport ended, and transport failed.
- Typed Shortcut origin context resolved at press time: valid external target,
  active editable Voice origin, or unsupported ClipAI surface. This context is
  frozen before any Popup change and carried with the press identity.
- A short-lived Setup return target distinct from the Paste Target.
- Voice disable operation identity and typed engine-shutdown/preference-save
  completions.
- Typed controller effects for preparing, starting, stopping, cancelling, and
  shutting down engine work, plus preference persistence when required.
- Immutable Voice capability/capture projection suitable for presentation.

Every operation-scoped command/event carries its operation identity. Each final
segment also carries a zero-based monotonic sequence number. UI edit and
output intents carry Workflow identity and the revision/content identity needed
to reject callbacks from dead or replaced Popups.

Do not represent permission, phase, terminal outcome, error category, or paste
settlement as free-form strings. Do not add a second Session concept.

### 5.2 VoiceInputController

The external interface accepts typed user intents and typed engine/runtime
events and returns an immutable transition result containing the authoritative
Voice projection plus zero or more typed effects. Callers do not mutate fields
or call presenter-specific methods.

It owns two related state machines:

Capability/setup:

- Disabled
- Setup required
- Requesting permission
- Ready/idle
- Permission blocked
- Unavailable

Capture:

- No active capture
- Starting
- Listening
- Stop requested
- Finalizing
- Cancel requested
- Terminal

The externally visible Review state belongs to the Workflow's Voice origin,
not to the active capture state machine. A successful capture terminal produces
one typed finalized insertion for the target Workflow. Interim text is only a
capture projection.

Transport settlement and domain settlement are deliberately different:

- The adapter reports exactly one transport terminal (`ended` or `failed`) for
  each accepted setup/capture transport operation, after its transport/media
  cleanup attempt.
- The controller alone produces exactly one domain setup/capture outcome. It may
  turn transport success into a domain warning/failure when identities,
  sequences, cancellation, or Workflow revision are invalid.
- Only the controller can emit a finalized Workflow insertion, and it emits at
  most one per capture.

Controller invariants:

- At most one active setup operation and one active capture; setup and capture
  cannot use the microphone concurrently.
- At most one microphone lease container-wide.
- Only the active identity may change state.
- A stop gate is monotonic.
- Every accepted setup/capture reaches exactly one domain settlement after zero
  or one matching transport-terminal report.
- Terminal or stale events are idempotently ignored.
- Permission ready does not imply Listening.
- Enabled does not imply microphone active.
- Disable becomes authoritative only after required cancellation/shutdown
  settlement, while new starts are rejected immediately.
- Provisional text cannot mutate a Workflow.
- Final segment sequence starts at zero. Identical duplicates are ignored;
  conflicting duplicates fail the transport. Future sequence numbers are held
  in a bounded reorder buffer. On transport end, a gap produces a warning and
  only the contiguous confirmed prefix is eligible for insertion; buffered text
  after the gap is not guessed into place.
- Cancel discards every interim and final segment collected by that capture,
  including contiguous segments not yet applied. It preserves only canonical
  Workflow content that existed before the capture.

The controller also owns an identified Disable join operation. New setup/capture
is rejected as soon as Disable is accepted. Engine shutdown/capture terminal and
preference-save completion may arrive in either order; the controller aggregates
them by Disable identity and is the only owner of the final Tray projection:

- Both succeed: `Disabled`.
- Media/host cleanup times out or fails: force-terminate the identified host,
  remain capture-blocked, and project `Disabled — cleanup unconfirmed`. Re-enable
  is rejected until the host is confirmed absent or a fresh process-level
  recovery check after application restart succeeds.
- Preference save fails after cleanup: remain disabled for the current process
  and project `Disabled — setting not saved` with a Retry Save action. Do not
  claim the choice will survive restart.
- Late completion for an older Disable operation is ignored.

Enable/setup is transactional in the opposite direction. Explicit Enable starts
setup but does not persist `enabled=true`. Permission/readiness must settle and
all setup media must be released first; the controller then requests preference
save. Only a successful save projects Ready. Dismiss, deny, blocked permission,
or preference-save failure leaves capture unavailable and the persisted disabled
choice unchanged. A retry reuses no old setup identity. A previously persisted
enabled choice may start the warm host on application startup without requesting
media; actual permission is revalidated on the next explicit PTT.

### 5.3 Workflow Voice origin

Extend the existing Workflow module with a typed Voice origin instead of a
parallel Voice draft store. The origin contains canonical text, revision, and
the frozen Paste Target. It is not an Action result step.

The Workflow interface must support behavior equivalent to:

- Create Voice origin from a validated external target.
- Resolve and freeze an insertion range for a capture.
- Apply one finalized capture insertion only when Workflow/origin revision and
  target identity are still valid.
- Apply an explicit UI edit with identity/revision validation.
- Resolve selection-first Action input.
- Navigate from Action results back to the Voice origin.
- Truncate later results when starting again from the origin.
- Resolve current completed semantic content for Copy/Paste/Action. V1 adds no
  Voice-specific Archive control or Archive behavior.

The exact public method names are an implementation decision. Keep the interface
small and test through observable Workflow snapshots and semantic results.

### 5.4 Runtime dispatch

Add one focused app composition/dispatch module. It may:

- Translate shortcut press lifecycle into typed Voice intents.
- Resolve and freeze press-time origin context before any ClipAI surface changes.
- Ask the existing runtime for the current external target or active Voice
  Workflow context.
- Create/close Workflows through existing runtime ownership.
- Execute controller effects through injected adapters.
- Enqueue typed engine/preference completions.
- Apply finalized insertions to the owning Workflow.
- Forward immutable projections produced by the owning controller/Workflow.

It must not retain canonical draft, composer mode, current Workflow truth,
capture phase, permission truth, microphone truth, active Paste handle, or a
parallel operation registry.

It also must not construct, merge, or infer Voice phase/capability snapshots.
Presentation receives owner-produced projections; runtime may route them but
cannot derive Ready, Listening, Disabled, or terminal truth.

### 5.5 Engine seam and Browser Speech adapter

Define one engine port at the core seam and provide:

- A production Edge WebView2 Browser Speech adapter.
- A deterministic in-memory/fake adapter used by controller/runtime tests.

The production adapter owns:

- Host process start and liveness.
- Protocol serialization/decoding.
- WebView2 readiness and permission request transport.
- SpeechRecognition and MediaStream lifecycle.
- Transport-level stop/cancel/shutdown.
- Exactly-once terminal event emission per accepted operation.

The adapter sends transport events only to a queue sink supplied at composition.
It has no
reference to UI, Tray, Workflow, preferences, Paste, or provider objects.

The host protocol must include a protocol version and operation identity in
every operation-scoped message. Unknown message types, invalid payloads,
unexpected EOF, and host stderr/stdout encoding problems become typed transport
failures. Human-readable runtime noise must never be parsed as protocol data.

Host/media invariants:

- Permission readiness releases all test/setup media tracks before reporting
  Ready.
- Capture terminal stops recognition and all media tracks before emitting the
  terminal event.
- Stop/cancel arriving during asynchronous `getUserMedia` prevents any later
  recognition start and immediately stops any late-created track.
- A natural recognition end is reported to the controller. Only a subsequent
  identified controller effect may restart recognition for the same capture;
  the adapter never reads a physical-held gate or restarts autonomously.
- Process EOF settles the active operation once and moves capability to
  Unavailable.
- Shutdown is idempotent and settles/terminates boundedly.

The real-process integration seam is a bundled test-only host page/driver that
uses the real process and JS bridge while injecting fake `getUserMedia` and
`SpeechRecognition` implementations. It exposes deterministic protocol events
and observable fake track-stop counters. Production configuration cannot select
this page/driver. Automated integration proves bridge/process/cleanup calls;
only the manual hardware matrix claims that a real Windows microphone indicator
turns off.

### 5.6 Preferences and configuration

Persist only:

- Whether ClipAI Voice Input is enabled by explicit user choice.
- Last selected supported language.

Do not persist permission truth; it is externally owned and must be checked.
Do not persist active state, setup IDs, capture IDs, drafts, targets, or errors.

Configuration exposes only the supported Browser Speech backend and parameters
that composition actually consumes. Validate host/port/runtime parameters and
reject unsupported backend values. Secrets are not required for V1.

Preference writes use the established asynchronous preference workflow and
return typed completions through the command queue. Tray check state changes
only from the authoritative saved/controller projection.

### 5.7 Popup and Tray presentation

Derive controls from typed state rather than scattered booleans.

Setup surface:

- Explanation of microphone use, online recognition processing, audio
  non-retention, and ephemeral transcripts.
- Enable Microphone primary action.
- Cancel/close.
- Permission-blocked repair instructions and settings link/action.

Voice Popup:

- Stable title `Voice Input`.
- Privacy-safe target badge using application identity only, never a full window
  title.
- One stable status region for Preparing, Listening, Finalizing, Review,
  Pasting, and Error.
- Microphone icon plus text while Listening; do not rely on color or animation.
- Read-only canonical/interim presentation while Listening/Finalizing.
- Editable canonical draft in Review.
- Primary Paste, secondary Copy, pin, close, and language selection.
- Stop and Cancel while Listening; Cancel while Finalizing.
- Language controls disabled while capture is active.
- Clear keyboard hints for PTT and `Ctrl+V` without duplicating the Popup title
  as the first content heading.

Tray state is a projection of Disabled, Setup required, Setting up, Ready,
Listening, Permission blocked, and Unavailable. Menu actions are disabled while
their real operation cannot be accepted.

## 6. End-to-end lifecycle specifications

### 6.1 First use

1. External application is foreground.
2. User presses PTT.
3. Runtime immediately shows pending feedback within the response SLO.
4. Controller reports Setup required; no Workflow or capture is created.
5. Setup surface explains privacy and requests explicit Enable.
6. Browser/system permission completes or fails through a setup identity.
7. On transport success, setup media is released before preference save begins.
8. Successful preference save permits Ready; failure remains not ready with a
   retryable setting error.
9. Setup closes and the matching short-lived return target is restored when
   still valid.
10. User sees `Voice Input ready — hold Ctrl+Alt+W to speak`.
11. A later PTT re-resolves a real Paste Target. Target validation failure shows
    actionable feedback and starts neither Workflow nor capture.

### 6.2 Normal new dictation

1. Resolve and freeze the valid external Paste Target.
2. Validate the press-time origin context and ask the controller to reserve
   single-capture admission. A setup requirement, invalid target, unsupported
   ClipAI origin, or active capture rejects here without closing any existing
   Popup or creating a Workflow.
3. After admission succeeds, close/cancel the previous unpinned transient
   Workflow; retain pinned ones.
4. Create a Voice Workflow origin with an empty canonical draft and bind the
   reserved capture to it.
5. Start the engine with the new capture identity.
6. Show non-activating Preparing, then Listening only after engine acknowledgement.
7. Project interim text read-only.
8. Physical release requests stop exactly once and immediately projects
   Finalizing.
9. Engine stops recognition/media, then reports transport terminal.
10. Controller emits one domain settlement and finalized insertion; Workflow
    applies it if identity and revision remain valid.
11. Popup activates in Review with the editor focused.

### 6.3 Continue dictation in an existing Voice Draft

1. Active Voice Popup must currently display its editable Voice origin in Review
   and supply its Workflow identity and valid frozen target. It continues the
   Voice Draft unless the user has explicitly opened the Popup Follow-up with
   `Ctrl+/`; that explicit visible Follow-up intent routes the next PTT capture
   to the Follow-up field instead. A displayed Action result is not eligible
   and PTT is rejected rather than interpreted as Voice Follow-up.
2. Workflow freezes selection/caret and origin revision.
3. Single-capture admission succeeds or produces visible rejection.
4. Capture follows the normal lifecycle.
5. Finalized text replaces the frozen selection or inserts at the frozen caret.
6. A stale UI edit/capture completion after close or revision change is rejected.

### 6.4 Apply an Action

1. User explicitly triggers an existing Action shortcut while Voice Review is
   active.
2. Workflow resolves immutable selection-first input.
3. Existing provider and Workflow execution lifecycle runs unchanged.
4. Voice origin remains available through Back.
5. Failure retains the last valid visible content.
6. A new Action from the origin truncates downstream history.

### 6.5 Paste

1. User selects Paste or presses `Ctrl+V` from either Voice Review mode.
2. Workflow resolves the completed visible semantic content.
3. Existing Paste owner validates the frozen target and runs dispatch/cleanup.
4. UI projects pending from the real Paste operation identity.
5. Terminal acknowledgement drives close/retain/error behavior according to
   pin state and terminal truth.
6. Late Paste acknowledgement cannot affect another Workflow or newer Paste.

### 6.6 Disable and shutdown

1. Create a Disable operation identity and reject new setup/capture admission
   immediately.
2. Issue typed cancel/shutdown and preference-save effects. Their completions may
   arrive in either order and are joined only by the controller.
3. Cancel discards all provisional interim/final segments from the active
   capture; preserve canonical finalized/editable Workflow text from before it.
4. On cleanup and save success, project Disabled.
5. On host cleanup timeout/failure, force-terminate the identified host, remain
   capture-blocked, and project `Disabled — cleanup unconfirmed`; prohibit
   re-enable until absence/recovery is proven.
6. On save failure after cleanup, remain disabled for the current process and
   project `Disabled — setting not saved` with Retry Save.
7. Ignore completions for older Disable identities.
8. Application shutdown remains bounded even if host is unresponsive; report
   cleanup failure without leaving UI or worker threads alive.

## 7. Concurrency and identity matrix

Tests and implementation must explicitly cover these interleavings:

- Start then physical release before engine Listening acknowledgement.
- Stop/cancel while `getUserMedia` is pending.
- Natural recognition end racing with physical release.
- Natural end deciding to restart while Stop acquires the stop gate.
- Duplicate Listening, final segment, terminal, and process-EOF events.
- Final segments duplicated consistently/conflictingly, arriving out of order,
  leaving a terminal sequence gap, or arriving after transport terminal.
- Old capture event after a new capture begins.
- Setup completion after setup surface closes.
- Permission completion after Disable.
- Setup return target closed/replaced, or completion from an older setup trying
  to restore focus.
- Host crash during setup, starting, listening, stopping, and idle.
- Voice Popup close during Listening, Finalizing, provider Action, and Paste.
- UI edit callback after Workflow close/replacement.
- New transient Workflow while old unpinned provider invocation is active.
- Pinned old Workflow plus new Voice Workflow.
- New PTT while another capture is active.
- New PTT failing setup, target validation, origin-context validation, or capture
  admission; existing transient Workflow must remain untouched.
- Language change during capture.
- Paste target closes or changes identity before dispatch.
- Old Paste terminal after a new output operation starts.
- Listener shutdown or missing release while capture is active.
- Safety watchdog expiry without a terminal press observation.
- Disable cleanup and preference-save success/failure/timeout in both completion
  orders, including stale completion and Retry Save.
- Application shutdown during setup/capture/paste/preference save.

For every row, assert authoritative state, emitted effects, UI projection,
microphone/media truth, Workflow content, and whether the event is ignored or
settled. Avoid asserting private fields.

## 8. Testing decisions

### 8.1 What makes a good test

- Test observable behavior through the owning module's interface.
- Use identities and deterministic schedulers/events, not wall-clock sleeps.
- Assert operation truth, not optimistic UI state.
- Keep engine transport fakes below the engine seam and UI fakes above the
  presentation seam.
- Replace obsolete shallow-module tests when a deep-module interface test covers
  the behavior; do not layer tests around private implementation.
- Unit tests must not instantiate Tkinter, real clipboard, keyboard listeners,
  real providers, WebView2, or microphones.
- Integration markers are required when real OS/UI/process behavior is used.

### 8.2 Controller tests

Cover:

- All capability/setup transitions and rejected intents.
- All capture transitions and exactly-once controller domain settlement.
- Separation of adapter transport terminal from controller domain settlement.
- Monotonic stop gate and stale identity rejection.
- Single capture admission.
- Disable during every state.
- No-speech, crash, blocked permission, unavailable host, and timeout.
- Segment sequencing, bounded reorder, duplicate conflict, and terminal gaps.
- Language selection and active-capture lockout.
- Warm host without microphone lease.
- Enable permission/readiness/save transaction and Disable cleanup/save join.

### 8.3 Workflow tests

Cover:

- Voice origin creation and immutable target.
- Frozen selection replacement and caret insertion.
- Ordered segment joining and deterministic spacing.
- Edit revision validation.
- Selection-first Action input.
- Action result, Back to origin, failure preservation, and history truncation.
- Current semantic output content for Voice origin versus Action result.
- Close and late mutation isolation.

### 8.4 Runtime scenario tests

Use the real controller, Workflow, runtime dispatch, fake queue, fake engine,
fake presenter, and fake Paste/target adapters. Cover complete scenarios rather
than testing private runtime methods:

- First setup, Ready, second PTT, Review, and Paste.
- Normal PTT press/release with queued engine events.
- Continue dictation at selection/caret.
- Explicit Action and Back.
- Old unpinned cancellation and pinned coexistence.
- Rejection from a non-Voice ClipAI window.
- Late engine/UI/provider/Paste/preference completions.
- Disable and shutdown settlement.

Run at least one scenario with real TaskSupervisor scheduling to prove worker
threads only enqueue commands and never touch UI.

### 8.5 Adapter and protocol tests

Cover:

- Protocol version and identity round trips.
- Malformed/unknown messages and encoding replacement.
- Ready only after setup media release.
- Terminal only after capture media release.
- Stop/cancel during pending media acquisition.
- Natural end restart only while held and active.
- Process EOF for every active phase.
- Bounded idempotent shutdown.
- Host stdin/stdout closure and write failure.

### 8.6 UI and accessibility tests

Cover projections rather than engine behavior:

- Every state has visible text and correct enabled/disabled controls.
- Listening/Finalizing editor is read-only; Review is editable.
- Interim visual distinction does not change canonical content.
- Voice Review starts in Editing mode; `Ctrl+Enter` toggles a read-only Reading
  mode and can return to Editing without changing canonical ownership.
- `Ctrl+V` emits the identified external Paste intent from either Voice Review
  mode and never performs native popup paste; the Voice Draft widget intercepts
  it before Tk's native Text paste handler can modify the draft.
- The footer always states the mode, external `Ctrl+V` meaning, `Ctrl+Enter`
  transition, and target without relying on animation.
- General editable fields other than Voice Draft retain native `Ctrl+V`;
  non-editable completed result surfaces may emit the identified external Paste
  intent.
- Stop/Cancel/Paste feedback changes only after authoritative state.
- Non-activating Listening and activating Review.
- Pin coexistence and collision-aware placement.
- Target badge excludes window title/sensitive text.
- UI remains understandable without animation and supports keyboard navigation,
  focus visibility, tooltips, and accessible labels.

### 8.7 Architecture tests

Add enforceable checks for:

- Existing layer import rules.
- Core remains standard-library-only.
- UI never imports engine, clipboard, keyboard, Paste, or provider
  implementations.
- Platform adapter never imports app/UI/services policy.
- Engine/TaskSupervisor callbacks can only enqueue typed commands.
- Browser Speech adapter cannot import or query keyboard/hotkey implementations;
  only the Shortcut owner emits physical press observations.
- Application command union includes every dispatched Voice command.
- Runtime has no duplicate capture/Workflow/Paste registries or canonical draft.
- Runtime cannot construct Voice capability/capture phase snapshots; it forwards
  projections produced by owners.
- No unsupported backend or evaluation symbols remain.
- No transcript/audio fields enter preferences, logs, or diagnostics contracts.

### 8.8 Windows integration and manual release gate

Automated Windows integration starts the real WebView2 host with controlled test
events/media substitutes. It verifies process lifecycle, protocol, readiness,
stop/cancel, crash, and terminal handshakes without depending on a physical
microphone or interactive permission prompt.

Manual release testing covers Windows 10 and Windows 11 with the supported
WebView2 runtime:

- First-use Allow.
- Dismiss/deny and next-shortcut retry.
- Permanently blocked permission and repair instructions.
- Enable/Disable from Tray.
- Microphone indicator off after setup, release, cancel, Disable, crash, and
  shutdown.
- Fast tap, normal PTT, long dictation, no speech, and repeated captures.
- `zh-TW` and `en-US` fixed phrase corpus.
- External target closed, moved, or changed before Paste.
- Pinned result plus new Voice Popup on limited screen space.
- Host crash and recovery on next explicit PTT.
- Missing WebView2 runtime and repair path.

Record pass/fail, runtime version, OS version, timing measurements, and observed
error category. Do not record audio or transcript content in the artifact.

## 9. Performance and release objectives

- PTT intent produces pending visible feedback within 100 ms under normal local
  load.
- Display Listening only after engine acknowledgement.
- Warm-start target: Listening within 1 second. At 3 seconds show an explicit
  still-preparing state. At 10 seconds settle as timeout/unavailable.
- Release immediately displays Finalizing.
- Normal target: Review within 2 seconds of release. At 10 seconds settle as a
  retryable timeout while preserving finalized content.
- Cancel/Disable/Shutdown target: transport-terminal acknowledgement and
  microphone release within 2 seconds. A bounded timeout becomes the defined
  capture-blocked cleanup-unconfirmed state; it does not become fake success.
- Do not promise one universal recognition accuracy percentage. Track median
  latency and character/word error evidence for a fixed `zh-TW`/`en-US` manual
  corpus. Threshold changes require recorded spike data.

CI tests may use virtual time and deterministic timeout advancement; they must
not wait these wall-clock durations.

## 10. Tiny-commit implementation sequence

Each commit must leave the repository compiling and its relevant tests passing.
Prefer test-first behavior commits. Do not introduce compatibility aliases for
the experimental branch because the implementation baseline has no Voice
feature to preserve.

1. **docs: add the approved clean-rebuild plan**  
   Add this document unchanged to the clean implementation branch so every later
   commit and review has the same decision source.

2. **test: characterize develop shortcut, Workflow, Popup, and Paste behavior**  
   Add only the missing baseline characterization needed to protect existing
   semantics that Voice will reuse, especially physical press identity,
   selection-first Action input, transient/pinned lifetime, native `Ctrl+V` in
   ordinary editors, and Paste terminal truth.

3. **docs: record the approved Voice Input ADR and privacy contract**  
   Extract the concise decision and user-visible privacy claims from this plan
   into the repository's normal decision-document location if maintainers want
   a shorter durable ADR. No production behavior.

4. **feat: add typed Voice identities, languages, phases, and outcomes**  
   Introduce immutable core value types with equality/validation tests. Do not
   add runtime or UI behavior.

5. **feat: add exhaustive Voice intents, engine events, and controller effects**  
   Extend the application command contract and add an exhaustiveness test. Keep
   permission and terminal categories typed.

6. **feat: add Voice preference values and validation**  
   Add enabled choice and supported language to the existing preference model,
   persistence adapter, and coordinator tests. No capture behavior.

7. **feat: add VoiceInputController setup state machine**  
   Implement Disabled, Setup required, Requesting, Ready, Blocked, and
   Unavailable transitions through a small interface with deterministic tests.

8. **feat: add single-flight capture admission and Shortcut press mapping**  
   Keep physical truth in the Shortcut owner; map identified started,
   ended/abandoned, listener-stopped, and safety-watchdog observations to capture
   identity, rejection, and a monotonic stop gate. No real engine.

9. **feat: complete capture provisional-text and terminal policy**  
   Add interim, sequenced final segments, bounded reordering, duplicate/gap
   policy, no-speech, error, stop, cancel, stale event, transport terminal, and
   exactly-once domain settlement.

10. **test: add deterministic capture race matrix**  
   Cover stop-before-listening, natural-end/release, duplicate events, Disable,
   late events, and shutdown using virtual scheduling. Keep it at the controller
   interface.

11. **feat: add Workflow-owned Voice origin**  
    Extend Workflow contracts and snapshots with canonical Voice origin and
    frozen target; add creation, close, and semantic content tests.

12. **feat: add Voice insertion and edit revision behavior**  
    Add frozen selection/caret resolution, finalized insertion, deterministic
    joining, and stale UI edit rejection.

13. **feat: integrate explicit Actions and Back with Voice origin**  
    Add selection-first Action resolution, result history, Back, failure
    preservation, and downstream truncation tests without adding Voice logic to
    provider workers.

14. **feat: add focused Voice runtime dispatch using the typed queue**  
    Compose controller effects, shortcut press/release, Workflow targets, and
    typed engine event commands with a fake engine. Runtime owns no domain
    mirrors.

15. **test: enforce Voice ownership and worker-thread architecture rules**  
    Add architecture checks for imports, command union, queue-only callbacks,
    absent mirrored registries, and absence of transcript persistence.

16. **feat: define and test the versioned Browser Speech host protocol**  
    Build protocol encoding/decoding and a controlled host test harness before
    real WebView/media behavior.

17. **feat: implement WebView2 setup and permission transport**  
   Add explicit permission request, Ready-after-media-release, blocked/failure
   categories, process EOF settlement, and the test-only controlled host page.

18. **feat: implement WebView2 capture transport**  
    Add start, interim/final events, stop, cancel, natural-end policy, late media
    cleanup, and terminal-after-release behavior.

19. **test: add real-process Browser Speech integration harness**  
    Exercise the actual host process and protocol with controlled media/events;
    cover malformed messages, crash, write failure, and bounded shutdown.

20. **feat: compose the supported Voice backend and strict configuration**  
    Wire one production adapter, reject unsupported backend values, and keep
    host warm without media while enabled.

21. **feat: add Voice setup and privacy presentation**  
    Add first-use setup, truthful consent copy, permission repair, pending/error
    states, and focus restoration. It must not create a Workflow or target.

22. **feat: add authoritative Voice Tray controls**  
    Add Enable, Disable, status, permission management, pending projection, and
    shutdown behavior driven only by controller/preference truth.

23. **feat: add Voice Popup Listening and Review projections**  
    Add non-activating read-only capture projection, activating editable Review,
    stable status/control placement, language lockout, Stop/Cancel, target badge,
    and accessibility tests.

24. **feat: integrate transient/pinned Voice Workflow presentation**  
    Implement one transient Popup, pinned exceptions, collision-aware placement,
    cancellation of replaced unpinned Workflows, and late completion isolation.

25. **feat: route Voice Copy and explicit Paste through existing output owners**
    Route `Ctrl+V` from either Voice Review mode and the Paste button through
    the frozen target and semantic content, and project terminal truth/pin
    behavior.

26. **test: add full app-level Voice lifecycle scenarios**  
    Cover first setup, normal dictation, repeat insertion, Action/Back, Paste,
    pinned coexistence, rejection contexts, Disable, crash, and shutdown with
    real TaskSupervisor scheduling and deterministic adapters.

27. **test: add supported-language and privacy regression checks**  
    Verify only `zh-TW`/`en-US`, last-choice persistence, no draft/audio in
    persistence/log/diagnostics, and no evaluation functionality.

28. **docs: add Windows Voice Input release checklist and troubleshooting**  
    Document the manual matrix, privacy truth, permission repair, WebView2
    requirement, timing evidence, and known platform constraints.

29. **test: run and stabilize the complete release gate**  
    Run targeted tests, architecture tests, full unit suite, automated Windows
    integration, packaging/compile checks, and manual smoke. Fix only failures
    attributable to this feature in cohesive follow-up commits; do not weaken
    assertions or add sleeps.

Before every commit, inspect the intended diff. Before the final commit, inspect
the full branch diff against `develop` and search for unsupported backend,
evaluation, transcript persistence, direct UI callback, parallel paste owner,
and duplicate canonical draft symbols.

## 11. Definition of Done

### Product

- All approved lifecycle decisions in section 3 are implemented.
- A new user can understand setup, grant or decline permission, and retry later.
- PTT, Review, repeat capture, explicit Action, Back, Copy, and Paste operate on
  the correct Workflow and target.
- Transient versus pinned behavior remains understandable with multiple visible
  Workflows.
- Every control shows real pending, active, failure, or terminal truth.

### Safety and privacy

- No capture can begin without explicit enablement and a current PTT intent.
- No media track exists during enabled idle.
- Release, Stop, Cancel, Disable, crash, listener shutdown, and app shutdown all
  prove microphone release.
- Paste never uses a guessed target.
- Draft/audio are absent from persistent storage, logs, and diagnostics.
- Permission and processing disclosures are accurate for Browser Speech.

### Architecture

- Every state category has the single owner defined in this plan.
- Runtime composition contains no mirrored Voice domain state.
- All async completions use typed command round-trips.
- Canonical draft is Workflow-owned; provisional recognition is capture-owned.
- Existing Workflow, Paste, clipboard, provider, preference, and TaskSupervisor
  boundaries are preserved.
- Architecture enforcement fails if a future change violates these rules.

### Reliability

- Exactly-once setup/capture terminal settlement is proven.
- The concurrency matrix passes deterministically without arbitrary sleeps.
- Host crash and permission failure are recoverable on the next explicit intent.
- Late events from every operation category are isolated by identity.
- Performance targets have Windows evidence or an explicitly approved,
  evidence-backed threshold adjustment.

### Verification

- Targeted controller, Workflow, runtime, adapter, UI, and Tray tests pass.
- Architecture tests pass.
- Full unit suite passes.
- Automated Windows/WebView2 integration passes.
- Compile/packaging smoke passes on the supported environment.
- Manual Windows 10/11 matrix is completed and recorded without audio/transcript
  data.
- Final `develop...implementation-branch` diff contains no Evaluation feature,
  unsupported engine configuration, unrelated certificate fix, or experimental
  compatibility path.

## 12. Implementation-agent reporting contract

At the end of each logical stage, report:

- Current commit and completed behavior.
- Tests executed and exact result.
- Any observed divergence from this plan, separated into product, architecture,
  platform, or test evidence.
- Whether microphone/media release was proven or merely inferred.
- The next smallest safe commit.

Stop and ask for a product decision only if new evidence would change an
approved behavior or materially expand scope. For ordinary implementation
details, preserve the ownership and invariants here and continue autonomously.

Do not declare completion because unit tests pass. Completion requires the full
Definition of Done and Windows release evidence.
