# Microsoft WebView2 regression report draft

## Suggested title

`[Regression] SpeechRecognition cloud handshake returns HTTP 403 in WebView2 Runtime 153; Runtime 152 succeeds`

## Product and environment

- OS: Windows 11
- OS version: `10.0.26200.0`
- Architecture: x64
- WebView2 host: WinForms-based hidden WebView2, microphone permission explicitly
  allowed through `CoreWebView2.PermissionRequested`
- Host libraries: pywebview 5.3.2, pythonnet 3.1.0
- WebView2 SDK assembly version: `1.0.2045.28`
- Runtime channel: Stable Evergreen Runtime; retained M152 runtime used only for
  the controlled comparison
- Importance: Blocking; the application's voice-input feature produces no
  transcription
- Input language: `zh-TW`
- Working Runtime: `152.0.4191.66`
- Failing Runtime: `153.0.4234.32`
- Runtime selection was verified from the renderer user agent.
- The comparison used the same machine, physical microphone, application code,
  locale, OS account, and network.

## Problem description

The Web Speech `SpeechRecognition` API starts successfully and emits `onstart`
in WebView2 Runtime 153, but it emits `onerror` with `error === "network"`
about one second later and never returns an interim or final result.

The same host and page return interim and final recognition results when forced
to use the locally retained WebView2 Runtime 152.

This is not a `no-speech` result. A Chromium NetLog shows that the M153 cloud
speech WebSocket handshake reaches the service and receives HTTP 403.

## Minimal JavaScript path

The failure occurs both with and without an earlier `getUserMedia()` call. The
smallest failing recognition path is:

```html
<pre id="events"></pre>
<script>
const events = document.querySelector("#events");
const log = (message) => events.textContent += `${message}\n`;

window.startDiagnosticRecognition = () => {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition = new Recognition();
  recognition.lang = "zh-TW";
  recognition.interimResults = true;
  recognition.continuous = false;
  recognition.onstart = () => log("start");
  recognition.onresult = (event) => log(`result: ${event.results[0][0].transcript}`);
  recognition.onerror = (event) => log(`error: ${event.error}`);
  recognition.onend = () => log("end");
  recognition.start();
};
</script>
```

The production host also reproduces the failure when it first calls
`getUserMedia({audio: true})`, confirms non-zero microphone audio levels, stops
that stream, and then calls `SpeechRecognition.start()`.

## Steps to reproduce

1. Create a WebView2 environment with a fresh user-data directory.
2. Allow `CoreWebView2PermissionKind.Microphone` in the
   `CoreWebView2.PermissionRequested` handler.
3. Load the minimal page above from a local file.
4. In response to an explicit application Push-to-Talk command, invoke
   `startDiagnosticRecognition()` through the WebView host and speak a short
   phrase into the microphone.
5. Observe `start`, followed by `error: network` and `end`, with no result.
6. Capture a default-mode Chromium NetLog and inspect the WebSocket handshake.
7. Repeat with Runtime 152.0.4191.66 using the same host, page, microphone, and
   network.

## Actual result

| Runtime | Cloud speech route (sanitized) | Handshake | Web Speech result |
| --- | --- | --- | --- |
| 152.0.4191.66 | `speech.platform.bing.com/speech/recognition/edge/interactive/v1` | `101 Switching Protocols` | Interim and final text |
| 153.0.4234.32 | `api.msedgeservices.com/stt/speech/recognition/interactive/cognitiveservices/v1` | `403 Forbidden` | `network` error |

On M153, DNS resolution and the underlying connection complete before the HTTP
403. Chromium reports network error `-320` for the rejected WebSocket upgrade.

## Expected result

`SpeechRecognition` should upgrade the cloud speech connection and return
recognition results in Runtime 153 as it does in Runtime 152, or expose a
documented configuration requirement if the service migration requires one.

## Issue-template classification

- Repro in corresponding full Edge browser: Not yet determined. Microsoft's
  current official playground forces the on-device model and therefore does not
  exercise this cloud route.
- Regression: Yes.
- Last known working version: `152.0.4191.66`.
- First confirmed failing version: `153.0.4234.32`.

## Duplicate search

The MicrosoftEdge/WebView2Feedback issue tracker was searched on 2026-09-16 for
`SpeechRecognition`, `network`, `403`, `api.msedgeservices.com`, and Runtime
153. No issue describing this M152-to-M153 cloud-handshake regression was found.
The older issue #1613 concerns initial API availability and is not the same
failure.

## Controlled comparisons and exclusions

- Removing the preliminary `getUserMedia()` call does not change the M153
  result. Duplicate microphone permission requests are therefore not the
  primary cause.
- The microphone is active and produces non-zero audio levels.
- The same physical microphone produces a final transcript under M152.
- A fresh WebView2 profile produces the same version-dependent result.
- DNS and TLS/connectivity succeed; the service returns an HTTP response.
- Windows time synchronization is healthy (`time.windows.com`; measured offset
  approximately 73 ms during diagnosis).
- Chromium Web Speech core files compared between the two stable branches are
  unchanged; the observable difference is the Edge service route/handshake.

## Questions for the WebView2/Edge team

1. Did Runtime 153 intentionally migrate WebView2 cloud SpeechRecognition from
   the legacy Bing speech route to `api.msedgeservices.com`?
2. Is the new route expected to authorize WebView2 embedded clients, including
   hidden WebView2 controllers?
3. Can the team determine whether the 403 is caused by client credential/token
   construction, embedded-product identity, an allow-list, or service rollout
   skew?
4. Is there a supported way to obtain a non-secret correlation identifier for
   this failed handshake?
5. Is this fixed in a later M153 servicing build or M154?

## Diagnostic-data handling

The raw NetLogs include signed query values and authorization-related fields and
should not be attached to a public GitHub issue. They were deleted after the
sanitized comparison above was recorded.

We can reproduce the issue again and provide Microsoft with an exact UTC
timestamp and an unredacted NetLog through a private, security-appropriate
upload channel if requested. Public comments should contain only runtime
versions, endpoint families, status codes, timings, field presence/lengths, and
one-way hashes.

## Current impact

Applications that depend on Edge WebView2 cloud `SpeechRecognition` can enter
the listening state normally but receive no transcription after updating from
Runtime 152 to 153. If the application treats `network` like `no-speech`, this
can appear to users as repeated silence rather than a transport failure.
