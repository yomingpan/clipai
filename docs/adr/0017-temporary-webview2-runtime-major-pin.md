# ADR-0017: Temporary WebView2 runtime major pin

## Status

Superseded. The shipped configuration no longer pins WebView2 152. Evergreen
WebView2 153+ is used with the Ceto speech-service feature disabled so browser
speech falls back to the working Bing speech endpoint.

The optional runtime-major setting and resolver remain available only as a
rollback mechanism; they are not the current production workaround.

## Context

WebView2 Runtime 153.0.4234.32 reaches the cloud speech service but receives
HTTP 403 during the WebSocket upgrade. On the same machine, Runtime
152.0.4191.66 upgrades successfully and returns recognition results. Different
machines can retain different 152 patch versions, so an exact-version path is
not portable.

## Decision

`voice_input.webview2_runtime_major` is an optional positive integer. When set,
the app composition root supplies the platform Voice engine with the requested
major and the process environment. The platform resolver searches standard
system and per-user WebView2 `Application` directories, accepts only installed
runtime directories whose parsed major matches and which contain
`msedgewebview2.exe`, and selects the highest matching full version.

Only the Voice WebView2 helper receives
`WEBVIEW2_BROWSER_EXECUTABLE_FOLDER`. The parent process and unrelated WebView2
consumers are unchanged. If no matching runtime exists, Voice initialization
fails explicitly; it must not silently fall back to another major. Omitting the
setting preserves normal Evergreen selection.

## Ownership and boundary

- App config owns the requested major.
- `app/container.py` owns environment reading and dependency composition.
- `platform/browser_speech.py` owns installed-runtime matching and Voice helper
  process launch.
- Voice services and UI do not know runtime paths or versions.

This is a special exception for a verified external runtime regression, not a
second speech backend or a general browser-version manager.

## Alternatives rejected

- Exact absolute path: not portable across patch versions and machines.
- Global/system environment variable: changes unrelated WebView2 consumers and
  leaves hidden machine state.
- Silent fallback to Evergreen: would reproduce the failure while making the
  configured safety constraint untrue.
- Bundling M152: creates security and servicing obligations and is not part of
  this workaround.

## Consequences and safeguards

The target machine must already have a matching 152 runtime. Runtime discovery,
highest-patch selection, strict config parsing, helper-only environment
injection, and fail-closed absence are covered by automated tests. Diagnostics
record the configured major but not machine paths.

## Removal trigger

Re-test cloud recognition on a Microsoft-fixed M153 servicing build or a later
supported Evergreen runtime. After the fixed runtime passes the same physical
microphone and WebSocket handshake comparison, remove
`webview2_runtime_major: 152` from the shipped config. Remove the resolver and
schema field once no supported deployment relies on the pin.

## Superseding decision

At composition time, ClipAI preserves any existing
`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` value and idempotently appends
`--disable-features=msSpeechRecognitionServiceUseCetoService`. The Voice helper
therefore uses the installed Evergreen runtime without depending on an older
major remaining installed. The platform module declares the environment name
and fallback flag; it does not mutate process environment on import.
