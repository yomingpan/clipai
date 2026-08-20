# Voice Input V1 manual release checklist

Run this checklist on both Windows 10 and Windows 11 with Edge WebView2 Runtime
installed. Record the OS build, WebView2 Runtime version, microphone device, and
whether browser permission was new or previously granted.

Before the hardware matrix, run the controlled WebView bridge integration on an
interactive Windows desktop. It covers fake-media protocol lifecycle, a missing
microphone failure, and a permitted physical microphone reaching Listening:

```powershell
$env:CLIPAI_RUN_VOICE_WEBVIEW_INTEGRATION = "1"
python -m pytest -m integration tests/platform/test_voice_webview_host_integration.py
```

## Short end-to-end smoke test

1. Start ClipAI and focus a writable external app such as Notepad.
2. Hold `Ctrl+Alt+W`. On first use, confirm the setup surface appears and no
   dictation starts. Select **Enable Microphone**, grant permission, and wait for
   the surface to close with Voice Input shown as ready in the tray.
3. Focus Notepad again, hold `Ctrl+Alt+W`, speak a short sentence, and release.
   Confirm the popup remains non-activating while listening, then changes to an
   editable Review draft after finalization. Confirm the Review draft receives
   initial keyboard focus. Click an external window and confirm the unpinned
   popup closes according to the normal Popup focus-out policy.
4. In Editing mode, press `Ctrl+V` and confirm clipboard content is inserted into
   the draft and nothing is sent to Notepad. Confirm the footer describes Editing
   mode. Press `Ctrl+Enter`, confirm the draft becomes read-only and the footer
   describes Reading mode plus the external target. Press `Ctrl+V` and confirm
   the reviewed text is sent only to the original Notepad window. Press
   `Ctrl+Enter` again and confirm Editing mode returns. The Paste button must
   continue to send the reviewed text explicitly from either mode.
   While editing, move the caret and let a finalized Voice insertion update the
   draft; confirm the caret does not jump to another position.
5. Repeat with the original window closed before Paste. Confirm the draft stays
   visible with a failure and no text is sent to the currently focused window.
6. In a clean run with no cached external target, keep ClipAI focused and hold
   `Ctrl+Alt+W`; confirm capture still starts in a targetless Voice Draft. Focus
   an external editor before pressing Paste and confirm that target is captured
   for that Paste operation.

## Release matrix

| Scenario | Expected result |
| --- | --- |
| First setup accepted | Permission is requested once; tracks are released before Ready is shown; pressing the setup shortcut does not become a capture. |
| Setup declined | Voice remains not ready and a later PTT opens setup again. |
| Permission blocked | Tray/setup reports blocked state and directs the tester to repair permission. Select **Manage Microphone Permission** and confirm Windows opens the microphone privacy settings; it does not repeatedly record. |
| PTT press/release | One capture only; release finalizes and never auto-pastes. |
| Missing release watchdog | Hold PTT without a terminal press observation for 120 seconds. The active capture cancels with a missing-release message; it never finalizes or auto-pastes. |
| Stop / Cancel / Esc during capture | Microphone stops; interim text is discarded; existing draft remains available. |
| Natural recognition end before release | It restarts only for the same held press; release still stops it. |
| No speech | Review remains available with a retry message and no invented text. |
| Host crash | Capture ends truthfully; later explicit PTT can rebuild the host; no background restart occurs. |
| Disable during capture | New captures are rejected immediately; capture and host settle; tray becomes Disabled only after preference save and cleanup settlement. |
| Pinned and unpinned popups | With a completed result Popup focused, `Ctrl+Alt+W` opens that Workflow's existing Follow-up field immediately, inserts finalized speech at its live caret, preserves typed text and PIN state, and never submits automatically or creates a fresh Voice Draft. Voice Review continues its Draft. An answering, Follow-up-unavailable, or unfocused visible Popup rejects with explicit feedback; only no visible Popup starts a fresh Voice Draft. |
| Frozen or targetless target | When capture starts over an external app, Paste keeps that frozen target. When capture starts without one, the Draft remains usable and Paste captures the latest observed external target at operation start. An unavailable target fails closed. |
| Languages | `zh-TW` and `en-US` apply to the next capture only and persist only after a successful explicit save. |
| App shutdown | The host exits and no microphone indicator remains active. |

Do not mark Voice Input V1 released until every matrix row has a dated result on
both operating systems.
