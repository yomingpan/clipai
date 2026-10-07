# 3.7.18 installer integration diagnosis

Public release remains pending. Windows Setup is explicitly unsigned; this
failure is unrelated to purchasing or configuring a publisher certificate.

Validation run [37547134117](https://github.com/yomingpan/clipai/actions/runs/37547134117)
at `09aa8205ce21169c13b2d7a927bbeed26d664944` passed 2,023 unit tests,
the complete managed transaction, packaging, offline imports and compiled
payload extraction. The Python 3.10–3.13 Windows source matrix also passed.

The actual Setup cycle failed after 98.09 seconds. Its retained native log
reported `checking`, `preparing`, `committing`, `integrating`, then
`installed_integration_incomplete:TimeoutExpired`. Files were committed; this
is not a successful installation or retained-data recovery receipt.

`WindowsInstallationIntegration._shortcut` is the only 30-second subprocess
at this integration boundary. A workspace-only probe of the same adapter,
filtered environment, empty PATH, open input pipe, bootstrap Job containment
and null input handle completed locally in under three seconds. It did not
modify user shortcuts or registry and cannot substitute for the failing CI.

Temporary `[DEBUG-shortcut-3718]` markers distinguish shell startup, intent
reading, COM construction, link opening and saving. Setup must preserve these
content-free markers explicitly; its normal log filter retains only lifecycle
lines. Remove all temporary markers before the official tag and re-run the
original compiled installer cycle. No timeout extension or success waiver has
been applied.

Diagnostic run [37548240330](https://github.com/yomingpan/clipai/actions/runs/37548240330)
at `48f1f802432af6c72dbcae357626c7d230df97a3` passed the full compiled
installer cycle. First installation took 73.31 seconds and retained-data
reinstallation 66.97 seconds. Both actual desktop startup probes passed;
duplicate installation and active-process removal were rejected; broken-venv
removal and final removal passed. Installed logical bytes were 292,165,309.

This successful sample does not establish the timeout's cause. The temporary
markers are removed for the next original-path run. Publication and tagging
remain pending that run's result; no claim of a resolved root cause is made.

The original-path run 37549396684 failed again after 85.42 seconds at the same
integration timeout. Fresh-runner diagnosis 37550295604 isolated the stall
before request parsing, before COM. Original/Utility-first calls took roughly
17–29 seconds; pinning the native module path still timed out. Comparative run
37550519499 measured original calls at 19.641/12.406/12.078 seconds and direct
.NET calls without cmdlet discovery at 3.703/0.281/0.266 seconds. See the bounded
architecture diagnosis in `docs/specs/shortcut-bootstrap-boundary-3.7.18.md`.

A real Windows regression with module autoload disabled failed on the original
adapter (1.91s), then passed after the bounded replacement (2.21s). It creates
and validates a Unicode shortcut, rejects different arguments without changing
the file, and confirms temporary intent cleanup. The temporary workflow and
harness have been removed; the release workflow retains this actual regression.
The complete compiled installer cycle on the fixed adapter is still pending.

Fresh-runner runs 37551811207 and 37552002633 failed the .NET automation
replacement at Chinese TargetPath assignment with a range error. Supplying
a real pythonw.exe and icon did not resolve it. This is a separate failure
from the original 30-second timeout; no internal ANSI/codepage cause is claimed.

The final adapter replaces its PowerShell child with a private isolated Python
stdlib worker using IShellLinkW and IPersistFile. It keeps the same JSON intent,
30-second bound, ownership readback and cleanup. Local Unicode creation,
validation, changed-argument rejection and unchanged-file checks passed in
1.58 seconds. The fresh-runner regression and final compiled cycle remain
pending. A temporary fast diagnostic workflow is retained only until that
regression passes and must be removed before the official tag.
