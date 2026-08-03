# ClipAI

ClipAI turns explicit user Actions into AI-assisted workflows while preserving the identity and lifecycle of each interaction.

## Language

**Workflow**:
An interaction lineage that begins with an Action and may continue through follow-ups. It may be visible or headless, and it keeps the provider and model choice captured at its start until the workflow ends.
_Avoid_: Session, popup

**Foreground Workflow**:
The visible Workflow currently targeted by user interaction. Window focus may report a candidate, but does not independently define this identity.
_Avoid_: Active popup, focused window

**Pinned Workflow**:
A visible Workflow explicitly preserved when another external Action starts. Pinning preserves the Workflow but does not make it the Foreground Workflow.
_Avoid_: Persistent popup

**Shortcut Press**:
One physical shortcut operation that begins when a complete registered binding
first matches and ends when its non-modifier function key is released or the
operation is cancelled. Every Shortcut Press has its own identity, even when
Ctrl, Alt, or Shift remain held between presses. Modifier Context is only the
currently held modifiers and is not an Action identity.
_Avoid_: Chord, gesture (when referring to one Action intent)

**Paste Operation**:
An explicit attempt to deliver canonical Workflow content to one captured
external target. Each Paste Operation has its own identity and preserves the
truth of whether delivery was not dispatched or dispatched without confirmation.
_Avoid_: Paste action, keyboard job

**Paste Dispatch**:
The irreversible point in a Paste Operation after which ClipAI can no longer
promise that cancellation prevented delivery.
_Avoid_: Paste completion, successful paste

**Clipboard Preservation**:
The promise that temporary clipboard use either restores every original format
or stops before Paste Dispatch. Partial restoration does not satisfy this promise.
_Avoid_: Best-effort restore
