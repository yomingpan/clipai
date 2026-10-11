# Inline surface presentation measurement, 2026-09-28

`scripts/inline_surface_presentation_benchmark.py` creates the production
`InlineDictationWindow` on the interactive Windows desktop. For each mode it
measures initial show, transition to `整理中`, and expansion to recovery. Choice
mode also measures its selection expansion. Each interval ends after Tk idle
layout/paint and `DwmFlush`, with the window confirmed viewable. Expanded
choice and recovery bounds are checked against the current monitor work area.

Run command:

```powershell
.\.venv\Scripts\python.exe scripts\inline_surface_presentation_benchmark.py --iterations 20 --output artifacts\inline-surface-presentation-20260928-final.json
```

A second 20-iteration run used `artifacts/inline-surface-presentation-20260928-repeat.json`.
Both reports have `status=pass`, 60/60 expanded work-area checks, and zero
bounds failures. Device metadata: Windows build 10.0.26200, eight logical
processors, 2560×1380 work area, 1.25 DPI scale, Tcl 8.6.12.

| Phase | Run 1 median / p95 / max ms | Run 2 median / p95 / max ms |
| --- | ---: | ---: |
| Minimal initial | 11.09 / 17.06 / 31.57 | 10.59 / 12.58 / 26.56 |
| Minimal refining | 7.89 / 9.13 / 16.27 | 8.18 / 8.73 / 8.76 |
| Minimal recovery | 17.35 / 34.63 / 59.33 | 17.27 / 26.00 / 26.58 |
| Choice initial | 10.71 / 15.50 / 20.60 | 10.43 / 11.63 / 11.69 |
| Choice selection | 17.07 / 34.14 / 141.20 | 16.78 / 24.40 / 25.43 |
| Choice refining | 16.47 / 24.61 / 51.33 | 16.46 / 17.00 / 17.03 |
| Choice recovery | 16.72 / 17.14 / 32.77 | 16.71 / 17.15 / 17.37 |

Each cell has 20 samples. Run 1's Choice selection maximum was a 141.20 ms
outlier; the repeat did not reproduce it. Neither run supports a stable tail
claim or a release threshold. The benchmark starts at toolkit calls, so it
does **not** measure physical hotkey acceptance, runtime queueing, WebView,
Provider, Paste, target insertion, or an independently observed pixel frame.
It does not establish that Minimal mode preserved external focus. These remain
separate desktop gates and the representative-device baseline remains open.
