# Inline Dictation measurement plan (`Ctrl+Alt+M`)

Status: measurement design with partial instrumentation. Content-free Inline lifecycle stages now enter the existing diagnostics log with monotonic timestamps and distinct interaction, capture, and operation IDs; Paste and clipboard owners already emit their own stages. Actual first UI frame, target insertion, and device latency still require an external desktop observer and have no verified baseline. This plan applies to Choice-based and Minimal input modes in [ADR-0019](../adr/0019-inline-dictation-interaction-lifetime.md). Voice Input V1 performance objectives in [the rebuild plan](voice-input-v1-rebuild-development-plan.md#9-performance-and-release-objectives) describe PTT/Review; they are reference points, not verified Inline Dictation thresholds.

The scenario runner and release-quality oracles are specified separately in the [autonomous validation plan](inline-dictation-autonomous-validation-plan.md). The two plans share scenario IDs and outcome vocabulary; simulation results never count as measured device latency.

## Decision to support

Optimize the time from explicit user intent to trustworthy, usable text while keeping the microphone, focus, clipboard, cancellation, and Paste outcome truthful. A faster median is not a win if tail latency, wrong-target delivery, lost text, or misleading success increases. Before changing a gesture, engine, prompt, or Paste path, establish a repeatable baseline on real supported Windows machines.

The product question is not one stopwatch reading. It has three parts:

1. **Response:** How quickly does the user see the real state after each press or choice? Does the UI remain responsive while work continues?
2. **Completion:** Which stage delays usable text, including the long tail, and how often does the journey fail or require recovery?
3. **Trust:** Does the visible state match actual microphone, provider, Paste Dispatch, and clipboard cleanup truth? Does the content preserve intended meaning?

## Measurement boundaries

Use one short-lived, opaque **Inline interaction ID** to join stages of one explicit `Ctrl+Alt+M` journey. Retain separate capture, provider invocation, Paste Operation, and view lifecycle IDs. An ID correlates observations; it does not grant ownership, change admission, or imply success. The typed provider and Paste completion paths now report their terminal stages. Missing UI-frame and target-insertion observations remain `not_observable`, not zero duration.

Record monotonic timestamps at the boundary that actually observes each event. Compute intervals only from timestamps in the same process/clock domain. For a WebView or external observer, record send and receive boundaries in the Python host and label transport/observer uncertainty; do not subtract unrelated wall clocks. Wall time is only for grouping runs. Each stage records an explicit outcome (`completed`, `failed`, `cancelled`, `timed_out`, `skipped`, or `not_observable`) and a typed reason where available. A late or duplicate event remains visible in diagnostics but cannot extend or settle a newer interaction.

| Boundary | Start → end | Why it matters |
| --- | --- | --- |
| Shortcut response | Physical hotkey accepted → first mode-appropriate status frame visible; separately accepted → `Preparing microphone` projected | Immediate reassurance; UI frame needs a real interactive observer, not only a render callback. Minimal input status must not activate or displace the target. |
| Microphone startup | Capture requested → engine `Listening` acknowledgement | Warm/cold host, permission, device, and transport delay. `Listening` cannot be inferred from window visibility. |
| Recording health | `Listening` → stop press; note first interim, first final, silence hint, restarts, 120-second limit | Recognition runs while speaking. This is not post-stop latency, but affects confidence and finalization cost. |
| Stop response | Short or long stop press accepted → `Finalizing` visibly projected | The user should know the second press and its raw/refine intent were accepted immediately. |
| Recognition settlement | Stop request → terminal engine event → canonical recognized text or typed failure | Distinguish engine tail from controller/UI scheduling. Preserve partial final segments as a separate outcome. |
| Delivery decision | Choice-based: recognized text ready → raw/refine/cancel choice → pending feedback; Minimal input: stop gesture classified → recognition ready → raw Paste or refine admission | Report user decision time for Choice-based mode and short/long classification latency for Minimal input separately. Mode changes mid-interaction cannot change its decision. |
| Refinement | Refine intent accepted → provider task admitted → first response/terminal response → result or explicit raw-text recovery | Split local queue, network/provider time, and post-response processing only where the boundary is observable. A provider failure must not become automatic raw Paste or a refined success. |
| Paste | Paste request → admission → worker start → target activation → dispatch attempt/receipt → clipboard cleanup → terminal acknowledgement visible | `dispatched_unconfirmed` means the shortcut was sent, not that the target consumed text. Measure restoration and failure recovery independently. |
| End-to-end | First press → truthful terminal presentation; stop press → terminal presentation; choice press → terminal presentation only in Choice-based mode | Report both modes and raw/refine journeys separately. Separate human choice time from machine time where it exists. |

The window now shows `準備潤飾` before provider task admission and `整理中` after admission. The trace records that gap separately. Provider settlement and Paste settlement have separate acknowledgements; the latter never asserts that a target consumed the text. The external observer must still measure when either visible state reaches the screen and whether the target actually changes.

## What counts as a good result

**Speed:** for each stage and end-to-end journey, report count, median, p90, p95, p99 when sample size supports them, maximum, and timeout rate. Include a histogram or distribution, never only an average. Publish sample count and uncertainty beside every tail percentile. A few runs cannot establish p99. Keep startup, stop settlement, refinement, and Paste distributions separate; a quick STT stage cannot hide slow or failed Paste.

**Reliability:** report admission rejection, recognition empty/partial, provider failure and explicit recovery, wrong/stale target, Paste not dispatched, `dispatched_unconfirmed`, clipboard cleanup failure, cancellation after each phase, late completion ignored, and interaction left without terminal feedback. Use denominators appropriate to each stage and split by frozen Inline Input Mode. A cancelled journey is not a latency success or a generic failure; inspect whether cancellation stopped later side effects.

**Content:** on a fixed, explicitly consented test corpus, compare recognized text and final text separately. Include filler removal, self-correction, names/terms, dates, negation, uncertainty, language mixing, and punctuation. Character/word error can describe recognition, but human review of intent preservation and edit effort is needed for the final result. Do not optimize transcription accuracy as a proxy for usable writing. Track whether raw delivery was the intended path or an explicit recovery choice after provider failure.

Report Choice-based raw/refine choice rate, Minimal input short/long stop rate,
provider-failure recovery choice rate, and corpus outcomes split
into `no_manual_change`, `cosmetic_manual_change`, `meaning_changed`, and
`unsafe_change`. Negation or uncertainty reversal, changed names/dates/numbers/
terms, retained withdrawn information, and new commitments/conclusions are
release-blocking unsafe changes. Each corpus result records the action version,
prompt hash, provider/model version, and evaluator rubric. CI uses frozen
provider responses; non-deterministic live-provider evaluation is a separate
monitoring run, never a flaky unit gate.

**Trust:** verify that `Preparing`, `Listening`, `Finalizing`, `Refining`, Paste pending, failure, and terminal messages appear only when their owner reports the corresponding state. Measure whether Minimal input status stays readable without stealing focus and whether failures expose a complete-text recovery path. In a controlled target, compare actual inserted text and caret/selection behavior with ClipAI's `dispatched_unconfirmed` receipt. Outside a controlled target, never claim insertion success. Pair timing with a short user observation: did the user know the shortcut worked, what ClipAI was doing, and whether they needed to recover text?

No universal numeric Inline Dictation SLO is set before device baselines. Retain the existing PTT objectives as hypotheses to test for equivalent stages. Define a release gate only after measuring representative devices and choosing an acceptable tail, failure, and trust budget; record the baseline, sample size, and rationale when a threshold changes. Zero wrong-target delivery, unintended Paste after accepted discard, and false confirmed-success claims are correctness requirements, not percentile targets.

Before the baseline exists, the exploratory release gate requires complete
traces, causal evidence for every pending state, no interaction held beyond its
phase deadline without a truthful visible state, and the zero-tolerance
correctness requirements above. Measure terminal-notice dwell time as well as
time to terminal state: a dispatch notice that appears and disappears before a
person can read it fails the trust objective even when its timing is fast.

## Reproducible device and scenario matrix

Use at least a lower-spec supported Windows PC and a typical PC, with OS build, CPU class, RAM, storage class, WebView2 version, audio device class, provider/model, network class, app version, and power mode recorded as bounded metadata. Avoid serial numbers, user names, executable paths, or raw window titles. Repeat both Inline Input Modes, warm and cold start, short and long speech, `zh-TW` and `en-US`, raw and refine choices or short/long stop gestures, idle and background load, stable and impaired network, and controlled targets representing plain text, browser input, and a rich editor. Separate setup/permission runs from steady-state capture. Use the same fixed phrases, target state, and run order; randomize or alternate order when comparing versions to reduce warm-cache and time-of-day bias.

Exercise negative paths: no speech, permission/device denial, engine timeout or self-end, provider unavailable/slow/cancelled, target closed or focus refused, modifier held, Paste overlap, clipboard external change, Esc at each phase, and a second hotkey while work is pending. Capture terminal state and cleanup evidence even when there is no final text. Automated fault injection establishes ordering and ownership; interactive Windows runs establish actual OS latency and target behavior. They are different evidence classes and must not be merged into one distribution.

2026-09-27 attended smoke contains one Choice raw, one Choice refine, one Minimal raw, one Minimal refine, and one Minimal cancellation run with controlled-target and App trace evidence. The [content-safe evidence summary](../evidence/inline-attended-20260927.json) records one observation per stratum; it supports stage-by-stage inspection, not representative percentiles or a device baseline. The full exploratory aggregation remains in the local `artifacts/inline-attended-exploratory-five-20260927.json`. First visible frame, independent audio/HID observation, and multiple-device cohorts remain unmeasured.

The [post-hotkey follow-up](../evidence/inline-followup-20260927.json) records the operator's successful LINE key-propagation check, the agent's blocked Tcl batch, and the local audio endpoint inventory. This PC exposed built-in speakers and a microphone array but no virtual or loopback input endpoint; a second Windows device is unavailable. The representative baseline therefore remains unestablished.

The first attended acoustic replay passed controlled-target readback but lacks speaker-playback start/end timestamps. A subsequent attended run at `artifacts/inline-controlled-audio-minimal-4/report.json` passed the controlled-target, clipboard-restoration, and same-interaction playback-timing checks. Its saved monotonic timestamps place the full WAV between Listening and Stop; the offline validation at `artifacts/inline-validation-audio-timed-user-20260927/manifest.json` reproduces the verdict. This establishes speaker-playback ordering on one PC, not independent microphone input, transcription accuracy, or a representative latency distribution.

Two attended fixed-WAV Minimal-refine attempts exposed a suppressed-M long-press regression: the listener produced `short` after a physical hold. After the platform adapter fix and app restart, `artifacts/inline-controlled-audio-refine-minimal-3/report.json` passed the same playback-timing, long-stop, provider-refinement, controlled-target Paste, and clipboard checks. Its single-run stage samples are recorded in the follow-up evidence; they do not establish p95 or a before/after performance comparison.

## Tooling sequence and status

1. **Trace and offline validation: partially implemented.** Content-free lifecycle stages use monotonic timestamps and distinct identities through the existing diagnostics logger. `scripts/report_inline_dictation_baseline.py` validates stage ordering, rejects incomplete or invalid traces including Paste after discard, and reports supported interval distributions by mode and path. Counts, median, p90, p95, p99 when sample size permits, cumulative latency buckets, terminal outcome rates, copy outcomes, recovery requests, and discards are separated; a recovery request is not proof that its first frame was visible. Deterministic fixtures cover malformed terminal traces. It produces no device performance claim. Owner-stage correlation and an external observation schema still need completion; do not add a second interaction registry, global event bus, or widget-owned timer.
2. **Local interactive Windows probe.** A controlled target app and external frame/target observer timestamp actual first frame, actual text insertion, caret/selection, focus, and clipboard restoration. Join its observations with content-free ClipAI traces by a run nonce, never by transcript or window title. Include a warm-up and repeated runs, then emit one local JSONL record per journey with stage durations, terminal truth, device cohort, and measurement uncertainty. The probe must not turn `dispatched_unconfirmed` into product success.
3. **Offline comparison: partially implemented.** `scripts/compare_inline_dictation_baselines.py` compares only matching controlled-desktop cohorts, retains sample counts and outcomes, and refuses simulation or incomplete traces. Device, target, language, load, and warm/cold strata require the external observer and a real baseline before a regression threshold can be set.
4. **Optional user diagnostic mode.** After local measurement is useful, offer an explicit, short-lived way to collect the same content-free timing and outcome metadata on other machines. Export remains an explicit user intent through the existing diagnostics boundary. No always-on transcript/audio capture or silent remote telemetry is implied.

## Privacy and measurement integrity

The trace contains no audio, interim/final transcript, prompt, provider response, clipboard payload, selected text, raw target title/path, or credential. Record only approved coarse metadata, typed outcomes, and durations. Trace files live in the app-owned diagnostics area, use a short-lived run nonce only inside one exported bundle, and are deleted on the documented diagnostics retention schedule. They are readable/exportable only through the existing explicit user diagnostics action and the SafeDiagnosticsExporter allowlist. Check both the trace artifact and the existing diagnostic export path for accidental content inclusion. A consented quality corpus is stored separately from ordinary diagnostics and is never sampled from real user dictation. Measure instrumentation overhead with and without tracing; if the probe changes the latency distribution materially, report it and reduce or relocate observation. Keep UI-thread observations constant-time and send reporting off the critical path.

## Next decision

The identity-scoped lifecycle, mode choice, fallback, cancellation deadline, typed Paste acknowledgement, and content-free stage trace are implemented and covered by deterministic and Tk tests. The next gate is the isolated Windows desktop observer and a baseline for both modes. The initial report should answer: **Which stage dominates p95 stop-to-terminal time on each device and mode, how often is the outcome unusable, and which visible state made the wait understandable or misleading?** Only then choose the smallest performance change and rerun the same matrix.
