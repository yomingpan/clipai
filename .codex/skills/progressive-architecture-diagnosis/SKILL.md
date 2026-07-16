---
name: progressive-architecture-diagnosis
description: Diagnose architectural debt before extending, refactoring, or repairing a software system. Use when ownership is unclear, modules repeatedly change for unrelated features, mechanisms are duplicated, boundaries leak, similar bugs recur, or the user asks whether to refactor, rewrite, migrate, or retain the current design. Gather evidence first; do not perform a major refactor or rewrite unless explicitly requested.
---

# Progressive Architecture Diagnosis

Diagnose the mechanism that makes technical debt compound, then recommend the
smallest evidence-backed intervention. Preserve verified behavior and separate
observed evidence from inference.

## Workflow

1. Read repository instructions and the affected use case. Inspect only the
   relevant structure, imports, tests, configuration/runtime ownership, git
   history, and co-changing files; expand only when evidence crosses a boundary.
2. State the current capability and the verified behavior that must remain.
3. Answer all four diagnostic questions:
   - Who is the single owner of the state, decision, rule, or workflow?
   - Is the request a reusable capability or a special exception?
   - Which knowledge crosses boundaries that should contain it?
   - Which contract, test, type rule, lint, or CI check prevents recurrence?
4. Identify the debt multiplier: duplicated ownership/mechanism, special-case
   growth, boundary leakage, unstable contract, hidden state, unmanaged
   concurrency, configuration drift, dependency inversion violation, or missing
   tests.
5. Classify the result: **Green** (continue with a bounded compromise),
   **Yellow** (stop before another workaround and propose a bounded
   intervention), or **Red** (create product-backlog architecture work with a
   migration boundary).
6. Recommend exactly one primary option: accept temporarily, local refactor,
   incremental migration, or core rebuild. Do not recommend a rewrite for
   untidiness alone.

## Required report

Use this structure:

1. Executive judgment: classification, recommendation, confidence, main reason.
2. Triggering evidence: facts vs. inference, with files/commits/tests.
3. Current capability and protected behavior.
4. Four-part diagnosis: ownership, capability vs. exception, propagation,
   enforcement.
5. Debt multiplier and the cost of three similar future changes.
6. Realistic options with benefit, cost, risk, and reversibility.
7. Recommended intervention: smallest boundary, exclusions, safeguards, and
   observable completion criteria.
8. Reversible migration sequence, if a change is recommended.
9. Concise ADR: context, decision, alternatives, consequences, review trigger.
10. Uncertainty: missing evidence and the highest-value next inspection.

## Guardrails

- Treat frequent edits as a signal, not proof; assess distinct change reasons,
  coupling, defects, cognitive load, and delivery impact.
- Do not modify production code during diagnosis unless explicitly asked.
- Prefer the smallest intervention that removes the debt-producing mechanism.
- Do not leave old and new ownership paths active indefinitely.
- Make the correct path easier and the incorrect path detectable through
  contracts and automated checks.
- State uncertainty rather than treating a style preference as a defect.
