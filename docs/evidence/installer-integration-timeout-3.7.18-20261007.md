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
