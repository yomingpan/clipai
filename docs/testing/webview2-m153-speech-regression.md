# WebView2 M153 SpeechRecognition regression

Date: 2026-09-16  
Environment: Windows 11, Edge WebView2 Runtime x64, physical microphone  
Affected ClipAI seam: `ClipAI/platform/voice_webview_host.html`

## Symptom

Voice capture reaches `SpeechRecognition.onstart`, but no interim or final text
is produced. ClipAI presents this like silence because the production page
currently ignores both `no-speech` and `network` errors before `onend`.

## Differential result

The same ClipAI page, helper process, microphone, language (`zh-TW`), fresh
profile, and user phrase were exercised against two locally installed WebView2
runtimes. Runtime selection was verified from the renderer user agent.

| Runtime | Capture path | Result |
| --- | --- | --- |
| 152.0.4191.66 | `getUserMedia()` then `SpeechRecognition.start()` | Audio levels, interim text, and non-empty final text |
| 153.0.4234.32 | `getUserMedia()` then `SpeechRecognition.start()` | `network` error in about one second |
| 153.0.4234.32 | Direct `SpeechRecognition.start()` | Same `network` error |

Removing the capture-time `getUserMedia()` request does not change the M153
failure. This falsifies duplicate microphone permission requests as the primary
cause on this machine.

## Sanitized network evidence

Default-mode Chromium NetLog was captured separately for each runtime using a
fresh Voice WebView profile. Raw logs were deleted immediately after extracting
the following non-secret facts; query strings, request headers, service keys,
connection identifiers, and audio payloads are intentionally not retained.

| Runtime | Speech host | Path | WebSocket result |
| --- | --- | --- | --- |
| M152 | `speech.platform.bing.com` | `/speech/recognition/edge/interactive/v1` | `HTTP/1.1 101 Switching Protocols`; bidirectional frames followed |
| M153 | `api.msedgeservices.com` | `/stt/speech/recognition/interactive/cognitiveservices/v1` | `HTTP 403`; Chromium `net_error -320` |

M153 resolves DNS and establishes the underlying connection before the service
rejects the WebSocket handshake. The browser then projects that rejection as
`SpeechRecognitionErrorEvent.error === "network"`.

## Conclusion

The regression is in the Edge/WebView2 speech-service route or its handshake,
not microphone acquisition and not ClipAI's `getUserMedia()` sequencing. The
M152-to-M153 runtime change selects a different speech host and request shape;
the M153 service rejects that request with HTTP 403.

Identical Chromium Web Speech source blobs across M152 and M153 do not rule out
this failure because the observed change is in Edge runtime service integration.

## Additional local evidence

The M153 `msedge.dll` contains additional nearby strings for a Microsoft
Genuine Edge token path, including `NO_SUBSCRIPTION` and a
`microsoft_genuine_edge_token` source path. The M152 binary does not contain
those two strings. Both versions contain `Sec-MS-GEC`,
`Sec-MS-GEC-Version`, and `Ocp-Apim-Subscription-Key` strings.

This is a useful clue that M153 added or changed an Edge-specific identity or
subscription decision near the speech request path. It is not proof that a
particular token is malformed: Microsoft does not publish the contract or
validation rules for these private fields.

Windows time synchronization was healthy during the reproduction
(`time.windows.com`, measured offset about 73 ms). Gross clock skew is therefore
not a credible explanation for the 403 on this machine.

## Reproduction method

The differential was run with a temporary diagnostic page that surfaced the
real `SpeechRecognition.onerror` value and renderer user agent. Each run used a
fresh WebView2 profile. The helper process was pointed at the retained runtime
with `WEBVIEW2_BROWSER_EXECUTABLE_FOLDER`, and the selected version was verified
from the emitted user agent. The temporary page and raw NetLogs were deleted
after extracting the sanitized facts above. Do not ship an obsolete fixed
runtime as a permanent workaround.

The checked-in integration test still verifies host transport, microphone
availability projection, and entry into the listening state. It does not
currently automate the attended physical-microphone/runtime differential.

## Remaining discriminator

The highest-value remaining comparison is cloud recognition in full Edge 153
versus WebView2 153 on the same machine and network. Microsoft's current
official SpeechRecognition playground cannot answer that question: it opts in
to `processLocally = true`, targets the on-device model, and is documented for
Edge Canary or Dev. A passing or failing local-model run would bypass the cloud
route that returned this 403.

## Follow-up

1. Report the sanitized M152/M153 matrix and WebSocket status differential to
   Microsoft Edge WebView2, without attaching an unredacted NetLog publicly.
2. Project `network` separately from `no-speech` so ClipAI reports the real
   failure and does not restart a rejected transport as though the user were
   silent.
3. Evaluate a supported fallback STT adapter independently of the hidden
   WebView2 infrastructure. Any fallback must preserve the existing typed Voice
   operation lifecycle and cancellation ownership.
