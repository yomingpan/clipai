# WebView2 M153 SpeechRecognition HTTP 403: primary-source investigation

Date: 2026-09-16

## Question

Why does the same ClipAI Web Speech request succeed with Edge WebView2
152.0.4191.66 but fail during the WebSocket handshake with HTTP 403 on
153.0.4234.32?

This note uses Microsoft documentation, Microsoft-owned repositories, Chromium
source, and the sanitized local differential in
[`docs/testing/webview2-m153-speech-regression.md`](../testing/webview2-m153-speech-regression.md).
It intentionally does not record request secrets, query values, credentials,
connection identifiers, or audio payloads.

## Executive conclusion

The strongest supported conclusion is an **M153 Edge/WebView2 cloud-speech
authentication or service-routing integration regression**.

The evidence proves that M153 changed both the speech host and request path,
then reached the new service and was rejected at the WebSocket HTTP handshake.
Microsoft documents that Edge's cloud Web Speech implementation uses Azure
Cognitive Services, and Azure Speech documents HTTP 401/403 as results of
missing or invalid authorization. This puts endpoint selection, credential or
token construction, and server-side authorization/rollout ahead of microphone,
DNS, TLS, and audio-format theories.

It does **not** yet prove which authorization input is wrong. In particular,
Microsoft does not publicly document `Sec-MS-GEC`, `Sec-MS-GEC-Version`, or
their validation rules. Claims about how those values are generated or rotated
come from third-party reverse engineering and are deliberately not treated as
facts here.

## Proven facts

### 1. Edge Web Speech cloud recognition uses Azure Cognitive Services

Microsoft's `SpeechRecognitionEnabled` policy documentation states that the
Microsoft Edge Web Speech implementation uses Azure Cognitive Services and
that voice data leaves the machine. It also says that, when the policy is
enabled or unset, websites may use speech recognition.

Source: [Microsoft Edge policy: SpeechRecognitionEnabled](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/speechrecognitionenabled)

This supports treating the observed `/stt/.../cognitiveservices/v1` request as
an Edge-to-Azure speech-service request rather than an arbitrary web request.

### 2. The M153 request reached an HTTP-speaking service and was forbidden

The controlled local differential records:

| Runtime | Host/path family | Result |
| --- | --- | --- |
| M152 | `speech.platform.bing.com`, legacy Edge recognition path | WebSocket `101`, audio exchange, final result |
| M153 | `api.msedgeservices.com`, Azure-style `stt/.../cognitiveservices/v1` path | HTTP `403`, no upgrade |

The M153 connection completed DNS and transport setup before the HTTP response.
This rules out microphone acquisition as the direct cause of this particular
failure and makes generic DNS/TLS outage explanations inconsistent with the
observed transaction.

This is local primary evidence; see the sanitized incident note linked above.

### 3. The M153 path shape is consistent with Azure Speech STT routing

Microsoft documents Azure Speech endpoint construction with the `stt` service
prefix and paths under `speech/recognition/.../cognitiveservices/v1`. The
private/custom-domain example is not the Edge consumer endpoint, but it confirms
that this path family belongs to Azure Speech-to-text routing.

Source: [Microsoft: use private endpoints with Speech service](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-services-private-link)

### 4. Azure Speech rejects invalid or absent authorization with 401 or 403

Microsoft's Speech SDK troubleshooting guide says requests without a valid
`Ocp-Apim-Subscription-Key` or `Authorization` header are rejected with HTTP
403 or 401. The same documentation classifies invalid, expired, or
region-mismatched subscription keys/tokens as authentication failures.

Sources:

- [Microsoft: troubleshoot the Speech SDK](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/troubleshooting)
- [Microsoft Speech SDK cancellation error codes](https://learn.microsoft.com/en-us/cpp/cognitive-services/speech/microsoft-cognitiveservices-speech-namespace)

Therefore the observed 403 is strong evidence of a service-side authorization
decision. It is not sufficient to identify the exact credential field because
the consumer Edge service can have private authorization inputs beyond the
public Azure SDK contract.

### 5. Chromium projects transport failures as Web Speech `network`

Chromium's speech engine converts upstream/downstream transport errors to
`SpeechRecognitionErrorCode::kNetwork`, and the renderer maps that enum to the
Web Speech network error. This explains why a rejected WebSocket handshake is
seen by ClipAI as `SpeechRecognitionErrorEvent.error === "network"`.

Sources:

- [Chromium speech recognition engine](https://chromium.googlesource.com/chromium/src/+/5202d434ad7080be15f6d6d2cbb9d826f798ce9f/content/browser/speech/speech_recognition_engine.cc)
- [Chromium renderer speech dispatcher](https://chromium.googlesource.com/chromium/src/+/e75e328a026878f90373d4055f8a582da0f9e7e0/content/renderer/speech_recognition_dispatcher.cc)

### 6. M153 public release notes do not announce this migration

Microsoft's Edge 153 web-platform release notes do not mention a cloud Web
Speech endpoint or authentication migration. The security release page confirms
that 153.0.4234.32 is an official Stable build, but does not describe speech
service changes.

Sources:

- [Microsoft Edge 153 web-platform release notes](https://learn.microsoft.com/en-us/microsoft-edge/web-platform/release-notes/153)
- [Microsoft Edge security release notes](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-relnotes-security)

Absence from release notes is not evidence that no private Edge integration
changed. It means the public change log cannot identify the responsible commit.

## Root-cause candidates

### A. M153 emits an invalid or incomplete authorization value for the new route

**Confidence: medium-high.**

Why it fits:

- the request reaches the new service and receives an authorization-class HTTP
  response;
- M152 succeeds on the same machine, profile strategy, locale, microphone, and
  network;
- M153 changes both host and path, so credential scope or construction may also
  need to change;
- Azure documents endpoint/region mismatch and invalid or absent credentials as
  authentication failures.

What remains unproven:

- whether the rejected value is a subscription key, bearer token, private Edge
  service token, client identity, or another signed request field;
- whether the browser generated the wrong value or the service expected the
  wrong rollout version.

### B. Client/service rollout skew for the new `api.msedgeservices.com` route

**Confidence: medium-high.**

The runtime and service are independently deployable. A newly selected M153
route returning a fast, deterministic 403 is compatible with the client using
a credential/version contract that the contacted service deployment does not
accept, or with the service not authorizing WebView2 traffic on that route.

This is an inference from the version differential and 403. No public Microsoft
incident or M153 release note currently confirms such a rollout mismatch.

### C. `Sec-MS-GEC` or `Sec-MS-GEC-Version` mismatch

**Confidence: medium as a test target; low as a concluded root cause.**

These names are relevant because they occur in observed Edge speech traffic,
but Microsoft has no public primary-source contract describing their purpose,
generation, clock tolerance, version binding, or validation response. Chromium's
open-source Web Speech implementation does not establish the Edge-specific
contract either.

Consequently, the following popular claims must remain unverified here:

- that `Sec-MS-GEC` is a time-derived hash;
- that it uses a particular shared token;
- that `Sec-MS-GEC-Version` must exactly track the Edge build;
- that clock skew or a stale version necessarily produces 403.

Those claims may suggest experiments, but are not acceptable evidence for a
root-cause statement without confirmation from Microsoft or a controlled
request-field differential.

### D. WebView2 embedder identity is not authorized on the new route

**Confidence: medium.**

The failing executable is WebView2 rather than full Edge. Because the new host
appears only in M153, the service might distinguish product/channel/embedder
identity and fail to recognize or authorize the WebView2 request. This is
especially plausible if full Edge 153 succeeds while WebView2 153 fails under
the same OS account and network.

This candidate has not yet been tested. WebView2's public API does not expose a
supported way for ClipAI to supply Edge's private speech-service identity, so
this would be a Microsoft integration defect rather than a ClipAI configuration
omission.

### E. Service policy, quota, geography, or IP reputation rejects the new host

**Confidence: low-medium.**

Azure documents 403 both for invalid authorization and, in SDK error semantics,
for forbidden/quota cases. A regional or service-side policy could reject the
new endpoint while the legacy endpoint still works. However, the exact
M152-pass/M153-fail split on one machine favors route/client-version skew over a
general network or account block.

### F. Microphone permission, silence, audio encoding, DNS, or TLS

**Confidence: very low.**

The server returns 403 before a WebSocket upgrade and before the speech audio
exchange. M153 also fails when the preliminary `getUserMedia()` call is removed.
These mechanisms cannot explain the observed HTTP authorization response.

## Highest-value discriminating experiments

These experiments should retain only field presence, lengths, stable hashes,
status codes, and timing. Never publish raw credentials or signed query values.

1. **Full Edge 153 versus WebView2 153.** Run the same minimal Web Speech page,
   locale, profile freshness, OS account, and network in full Edge Stable 153.
   If Edge succeeds while WebView2 fails, embedder/product identity becomes the
   leading candidate. If both fail on the new route, client/service rollout or
   shared credential construction becomes more likely.
2. **M153 point releases/channels.** Compare 153 Stable with the next official
   153 patch and with 154 Beta/Stable, recording only runtime version, selected
   host/path family, and handshake status. Recovery without ClipAI changes would
   strongly implicate Microsoft client/service integration.
3. **Sanitized request-shape comparison.** For M152 and M153, record whether each
   authentication-related field is present, its byte length, and a one-way hash;
   record whether any version-shaped non-secret value matches the runtime
   version. Do not retain values. This can reveal missing, empty, or internally
   inconsistent fields without leaking secrets.
4. **Clock sanity check.** Record Windows time-service synchronization status and
   UTC offset, then retry after confirmed synchronization. A result change would
   support a time-bound signature theory; no change would weaken it. This does
   not establish the undocumented GEC algorithm.
5. **Response metadata under private disclosure.** Preserve the 403 response
   body and non-sensitive response-header names for Microsoft support only.
   Azure gateways often return diagnostic request identifiers or an error class
   that Microsoft can correlate. Public reports should redact values.
6. **Microsoft-side correlation.** File a WebView2 regression with exact runtime
   versions, UTC timestamps, sanitized endpoint families, HTTP statuses, and a
   privately supplied NetLog. Only Microsoft can conclusively distinguish bad
   client credential generation from server rollout/allow-list failure.

## Decision

The current evidence justifies reporting:

> Edge WebView2 153 migrated cloud Web Speech recognition from the legacy Bing
> speech route to an Azure-style Microsoft Edge services route. On the tested
> system the new route rejects the WebSocket handshake with HTTP 403, while
> WebView2 152 upgrades and returns recognition results. This is most consistent
> with an Edge/WebView2 speech-service authorization or rollout integration
> regression.

It does not justify reporting:

> `Sec-MS-GEC` is definitely wrong, the subscription key expired, or ClipAI must
> generate/replace a browser credential.

Those statements require evidence that is not available in Microsoft's public
sources and would invite an unsupported, security-sensitive workaround.
