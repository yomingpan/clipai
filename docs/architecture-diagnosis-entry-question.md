# Entry Panel question admission diagnosis

## Judgment
Green: a local interface extension, with high confidence. Keep the existing
owners and extend the launch contract to represent the existing question intent.

## Evidence and protected behavior
`EntryPanelOption` and `EntryPanelDecision` previously described only Action or
category references. `WorkflowRuntimeModule._open_contextual_question` already
creates the question Workflow. The Panel runtime already owns frozen input and
the identity-matched pre-projection handoff. Existing slots 1–7, selection
safety, provider admission and Workflow history must remain unchanged.

## Ownership, capability, propagation and enforcement
The coordinator owns navigation/projection; Panel runtime owns its lifetime and
frozen input; Workflow runtime owns admission/membership; WorkflowController
owns composer eligibility, source capture state and question state. Launching an
existing non-Action intent is a reusable launcher capability. Treating it as a
YAML Action would leak execution semantics into the Action catalog. A typed
option/decision command and a frozen `InputTarget` keep this boundary explicit.
Tests enforce no recapture, no early provider invocation, source lineage and
handoff before projection.

## Debt multiplier
Special-casing a fake Action would multiply catalog, execution and recent-history
exceptions for each future launcher command. A second capture path would also
multiply clipboard ownership and timing bugs across three similar additions.
The typed command has one current legal value; more values require their own
admission contract rather than speculative dispatch machinery.

## Options and decision
A fake Action is small initially but couples unrelated lifecycles. A new question
pipeline duplicates existing ownership. Extending the typed launcher boundary
has a bounded cost and is reversible; choose this local extension. No catalog
migration, new clipboard owner, new transport mechanism or general command
framework is included.

## Sequence and safeguards
Add typed projection/decision, admit frozen input through Workflow runtime,
render the fixed root entry, then verify lifecycle and native surface behavior.
Completion means slot 8 opens the composer with the frozen source and provider
work starts only after submission. Existing shortcut behavior remains covered.

## ADR
Context: a frequent question operation is missing from the root launcher.
Decision: fixed root slot 8, using the existing contextual-question Workflow.
Alternatives: category nesting, fake Action, separate workflow implementation.
Consequence: the launcher explicitly supports an intent as well as Actions.
Review trigger: another non-Action entry or changes to source-admission policy.

## Uncertainty
Native desktop focus behavior still requires the integration smoke; unit tests
alone cannot establish physical keyboard/foreground behavior.
