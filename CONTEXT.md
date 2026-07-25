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
