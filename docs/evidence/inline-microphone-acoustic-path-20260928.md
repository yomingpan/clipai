# Default microphone acoustic path check — 2026-09-28

`scripts/probe_inline_microphone_path.py` played the SHA-matched fixed
`zh-TW-fixed.wav` through the default speaker while Windows WaveIn recorded the
default `Microphone Array` in memory. It wrote only signal statistics, never
microphone samples or recognized text.

| Run | Energy-envelope correlation | Baseline RMS | Peak RMS | Offset |
| --- | ---: | ---: | ---: | ---: |
| `artifacts/inline-microphone-path-20260928.json` | 0.891 | 1.3 | 792.2 | 0.61 s |
| `artifacts/inline-microphone-path-repeat-2-20260928.json` | 0.881 | 1.9 | 817.2 | 0.59 s |

Both runs captured about 6.6 seconds and matched the fixture's changing energy
envelope. The observed offset is consistent with the probe's 0.5-second delay
before playback. This confirms an acoustic path from this PC's speaker to its
default microphone under these conditions. It does not prove that WebView2
selected that device, that Web Speech transcribed the signal, or that a physical
`Ctrl+Alt+M` interaction succeeded. The separate direct WebView probe still
reports a typed `network` recognition failure. Two measurements are not a
representative device or reliability baseline.

To repeat the check from a normal desktop session:

```powershell
.\.venv\Scripts\python.exe scripts\probe_inline_microphone_path.py --audio-file artifacts\inline-audio-fixtures-20260927\zh-TW-fixed.wav --output artifacts\inline-microphone-path-new.json
```

The fixed WAV must match its manifest SHA-256. A microphone permission failure
is a blocked environment result, not evidence that the acoustic path failed.
