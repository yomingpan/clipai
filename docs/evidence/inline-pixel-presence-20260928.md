# Independent Inline window pixel presence, 2026-09-28

`scripts/probe_inline_pixel_presence.py` creates the production Inline Tk
surface in a controlled desktop position and samples only an 8×8 patch of its
known background color. A baseline patch is checked before showing the window;
if it already matches, the run is blocked as ambiguous. The observer never
saves pixels or screen content. It does not simulate `Ctrl+Alt+M`.

On this Windows desktop, the corrected probe observed the patch in all 40
runs (20 Minimal, 20 Choice). Report:
`artifacts/inline-pixel-presence-20260928-position-verified.json`. The probe
also requires the shown window's actual position to match the sampled patch.
Two earlier 40-run passes are retained at
`artifacts/inline-pixel-presence-20260928-final.json` and
`artifacts/inline-pixel-presence-20260928.json`.

| Metric | Minimal | Choice |
| --- | ---: | ---: |
| Observed / attempted | 20 / 20 | 20 / 20 |
| Detection upper-bound median | 60.1 ms | 80.2 ms |
| Detection upper-bound p95 | 90.2 ms | 94.9 ms |
| Detection upper-bound maximum | 95.3 ms | 95.5 ms |

The 47 screen grabs themselves took a median 43.7 ms and p95 64.5 ms. The
surface was found on the first sample in most runs and by the second sample in
all runs. These numbers are **sampling upper bounds**, not frame-rendering
latency; subtracting the median grab time would not recover true first-pixel
time. The separate [Tk-to-DWM measurement](inline-surface-presentation-20260928.md)
reports a different boundary and is not combined with these timings.

The first two single-run attempts sampled `(0, 0)` because `winfo_rootx/y`
returned zero for a withdrawn Tk window. They were observer-coordinate errors,
not product frame failures. The corrected probe computes the expected position
from the same placement function used by the UI and checks that coordinate
after show. A denied screen grab now produces a content-free `blocked` report;
the test suite deliberately injects this failure and checks the result. A real
restricted-sandbox run produced
`artifacts/inline-pixel-presence-sandbox-blocked-20260928.json` with that
reason. A separate negative oracle test confirms that a missing pixel is
`fail`, not `pass`.

This establishes only that controlled initial Inline windows appeared on the
desktop. It does not observe the first exact pixel time, state-label changes,
focus preservation, physical shortcut response, microphone, Provider, Paste,
or target insertion. Representative-device and end-to-end baselines remain
open.

A separate native Windows integration check ran with desktop foreground
permission:
`tests/ui/test_inline_dictation_window.py::test_minimal_status_preserves_the_native_foreground_window`
passed (1 case). It verified that a controlled Tk input target retained the
Windows foreground when Minimal status was shown. The pixel probe did not make
this claim, and the test does not cover third-party editors.
