# ADR-0020: First-install bootstrap and recovery

Status: accepted for local candidate implementation, 2026-10-01. The user
requested completion through manual acceptance, so B/C now proceed for an
isolated unsigned ClipAI Preview. Runtime archive, signing provider and
clean-VM feasibility remain unaccepted public-release choices.

## Context and diagnosis

Classification: Yellow; incremental migration. Ownership evidence is strong,
runtime/Setup feasibility needs device proof. Managed install already shares
verified bundle staging and payload materialization with managed update. Keep
immutable versions, external shared data, stable launcher, production key
admission, current-pointer commit and identity-bound launch health.

At the initial diagnosis, first-install UI/recovery coordination had no services owner. The
installer checks targets before acquiring its gate, cannot prove all interrupted
ownership, and builds both version and launcher venvs. `main.py` finds OpenSSH
via PATH and imports app/UI composition even for install dispatch. A bootstrap
must not assume that importing the normal app entry needs only installer deps.
gate used `Local\\`, so cross-logon-session contention was not covered.
The candidate now has the services owner, checks under admission, private
verifier resolution and a Global gate. Cross-session device proof and migration
from old deployed Local writers are still public-release requirements.

These are source observations, not newly reproduced production failures.
The existing test suite protects engine behavior; an A-stage synthetic fixture
is not evidence of full package readiness or clean-machine installation.

## Decision and four-part diagnosis

1. Single owner: `FirstInstallCoordinator` in services owns lifecycle,
   cancellation and recovery policy. Existing platform mechanisms execute
   admitted mutations; app composes; Windows integration owns OS effects.
2. Reusable capability: first installation/recovery is deployment admission,
   not an About or Inno-specific exception. Do not expand scope to silent
   install, enterprise deployment or automatic repair before demand exists.
3. Boundary leakage: Setup parsing manifests, invoking pip, managing pointers
   or keeping its own version list would duplicate the existing engine. A
   separate cleanup lock would duplicate gate ownership. PATH or Setup-temp
   dependency would leak the bootstrap lifetime into all normal launches.
4. Safeguards: typed operation results, shared stager/materializer, one admitted
   mutation context, cross-session gate evidence, persisted ownership,
   architecture/fault tests and separate clean-VM/first-use gates.

Use an embedded trusted bootstrap and complete compatible runtime, thin
per-user Setup, and fixed release assets. The exact runtime source stays open
until a pinned artifact passes license/security and actual environment gates.
The full CPython installer, NuGet and embeddable packages are not interchangeable;
app-local standalone builds are another candidate requiring admission.

Minimal maintenance is retained-data uninstall/reinstall via a trusted entry
that survives a broken app venv. Do not patch a live base runtime under old
venvs or create a new background updater. The concrete transition contracts
are in [first-install-contract](../contracts/first-install-contract.md).

## Options and tradeoffs

| Option | Benefit | Cost/risk and reversibility |
| --- | --- | --- |
| Incremental trusted Setup (selected) | Reuses verified policy; removes system-tool dependency | Larger artifact, runtime/signing maintenance; Setup release can be withheld independently |
| Keep source/BAT as user entry | Small change | Does not solve first-user bootstrap/trust; retain for development only |
| Online bootstrap | Smaller download | More transport/proxy/runtime-source failure paths; defer |
| Full app freezing | Potentially fewer visible Python files | Broad packaging/runtime change with unproven benefit; defer |

Debt multiplier is duplicated ownership plus hidden bootstrap dependencies.
Adding repair, channels and runtime upgrades to independent Setup policy would
multiply those rules three times. The smallest intervention is one coordinator
around the existing engine, with explicitly owned native integration and gate.

## Sequence and completion criteria

A1 fixes ownership/recovery and prerequisite/signing decisions; A2 runs bounded
runtime/packaging experiments on a genuinely clean VM; A3 checks the minimum
new-user journey. A local copied-runtime probe advances A2 preparation only.
Following the explicit 2026-10-01 user instruction, B adds core contracts/coordinator and shared admitted engine work, C adds
thin Setup/integration/first-use entry, D assembles signed candidate assets,
and E checks the actual downloaded candidate before public release.

A1 signing/admission, A2 clean VM and A3 observation remain public-release
gates. Local acceptance does not waive them. Preserve source launching and existing
managed release artifacts throughout; experimental probes do not become a
second production installer. Complete installation, startup health and first
successful user-triggered Action have independent observable completion states.

## Consequences, uncertainties and review trigger

The installer has more lifecycle work than a ZIP wrapper, but avoids manual
deletion/support loops and gives runtime security maintenance an exit. No
general repair, migration engine, telemetry platform or alternate update policy.

Highest-value missing evidence: a distributable pinned runtime, isolated full
dependency/bootstrap imports, clean VM/reboot/update/uninstall, non-admin
cross-session mutex access, publisher identity/signing eligibility and real
new-user observation. The current developer host cannot substitute for these.

Review on a second installer entry, repair, runtime/keyring rotation, new channel,
cross-architecture support or native integration becoming a second state owner.
