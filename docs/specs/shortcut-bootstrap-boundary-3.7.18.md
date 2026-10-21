# Shortcut bootstrap boundary diagnosis

## Judgment

Yellow; local refactor inside the existing Windows adapter. Confidence is high
that module discovery causes the observed delay and the automation path fails
on Unicode targets in fresh English Windows runners; their internal causes
are not established. No installer workflow rebuild.

## Triggering evidence

Repeated compiled installations reached `integrating`, then failed with
`TimeoutExpired` after 30 seconds. Adding diagnostic cmdlets yielded one passed
cycle; removing them restored the failure. Fresh-runner probes showed the
stall after shell startup and before request parsing, before COM construction.
Module-path pinning still timed out. Explicit Utility import still took
28.266/17.578/17.656 seconds. Run 37550519499 measured the original path at
19.641/12.406/12.078 seconds; direct Windows .NET calls took
3.703/0.281/0.266 seconds on another fresh runner. These are CI measurements,
not Windows 11 user-device latency claims. The .NET replacement then failed
in runs 37551811207 and 37552002633 while assigning a Chinese TargetPath,
even after supplying a real executable target.

## Protected capability

Create and validate exact per-user shortcuts from the existing JSON request.
Preserve target, arguments, icon, working directory, UTF-8 paths, ownership
rejection, temporary request cleanup and the 30-second subprocess bound.

## Four-part diagnosis

1. `WindowsInstallationIntegration` owns native integration. Services retain
   installation policy and settlement; no second state owner is needed.
2. Deterministic bootstrap OS integration is reusable capability, not a special
   CI exception. The same adapter serves install and owned removal validation.
3. Ambient PowerShell module discovery leaks host configuration/initialization
   into the installer. Contain that dependency in this platform adapter.
4. A real Windows regression creates and validates a Unicode shortcut with
   an empty PATH, rejects changed arguments and preserves its bytes.
   Native execution uses IShellLinkW, including Unicode target and argument
   readback; it does not resolve or launch the shortcut target.
   The existing compiled installer cycle remains the end-to-end safeguard.

## Debt multiplier

Adding warm-up commands or larger timeouts to three future integration features
would multiply hidden initialization and make failures harder to attribute.
Keep native execution explicit rather than adding workaround state.

## Options

Longer timeouts retain discovery and latency. Direct .NET calls remove
cmdlet discovery but failed the fresh-runner Unicode regression. The selected
stdlib worker uses the documented IShellLinkW and IPersistFile interfaces.
Its native ABI cost is bounded within the Windows adapter and justified by
both observed failures; no alternate shell fallback remains.

## Intervention and completion

Replace the PowerShell child with the private Python executable in isolated
mode and an absolute stdlib worker path. Keep the same owned JSON intent,
30-second bound, bootstrap Job containment and finally cleanup. Balance COM
apartment initialization and both interface references within that child.
No new bundled dependency, parallel worker mechanism, user-data owner or
service contract. Complete only after the native regression,
source/architecture tests and original compiled installer cycle pass.

## Reversible sequence

Record the failing native regression before changing the adapter. Apply the
bounded replacement, repeat native creation/validation and compiled acceptance,
then remove the temporary diagnostic workflow and harness before tagging.
Git history preserves the original adapter without retaining a live dual path.

## ADR

Decision: first-install shortcut integration uses explicit Unicode Windows
Shell Link APIs and cannot depend on PowerShell module import or WScript
automation. Alternatives above failed the observed latency or Unicode gates. Review when a
second native operation needs this same shell boundary; extract a shared
platform capability only when it removes actual coupling.

## Uncertainty

Clean Windows 11, standard-user, reboot and independent first-user gates remain
outstanding. CI proves the bounded mechanism, not those device requirements.
Highest-value next evidence is the compiled installer using the final adapter.
