# Windows external editable-target detection — research note

Status: research finding (no implementation decision)
Date: 2026-08-23
Scope: whether ClipAI can reliably tell that the foreground *external* application
has an editable text target before routing `Ctrl+Alt+W`.

## Answer first

**No Windows API provides a reliable, cross-application boolean for “the user can
safely dictate here.”** Windows exposes useful *evidence*, not that product
guarantee. A normal Win32 edit control can be identified with good confidence;
UI Automation (UIA) can provide stronger evidence when the focused provider
correctly exposes an editable `Edit`/`Document` control. But custom controls,
web/Electron surfaces, virtualized editors, higher-integrity windows, and
accessibility-provider failures make a universal affirmative answer unsafe.

Therefore an external-editability observation must be advisory. It may improve
the Voice Draft’s wording or default, but must not be an admission requirement
or a license to paste into a guessed target. This matches the existing product
contract: a targetless Voice Draft is valid, while external paste is an explicit,
separately validated operation.

## What Windows can tell us

### 1. Win32 GUI-thread caret: a useful hint, not an editability contract

`GetGUIThreadInfo` can inspect the foreground thread (or the thread identified
by `GetWindowThreadProcessId`) and returns `hwndFocus`, `hwndCaret`, and
`rcCaret`. It succeeds even when the active window is owned by another process.
[Microsoft: GetGUIThreadInfo](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getguithreadinfo)
and [GUITHREADINFO](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-guithreadinfo).

However, this says that a window is displaying the *system GUI caret*; it does
not say that the control is editable, accepts text, is not a password/secure
field, or will still be focused at paste time. Microsoft explicitly warns that
the function can return invalid window handles while the foreground window is
losing activation, and documents special edit-control caret geometry. Thus an
`hwndCaret` result can be a positive heuristic for traditional controls; its
absence must never be interpreted as “not editable.”

### 2. UI Automation: the best general evidence when an app participates

UIA can return the focused element through `IUIAutomation::GetFocusedElement`.
[Microsoft: Obtaining UI Automation Elements](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-obtainingelements).
The focused element (and, where needed, an ancestor reached by a tree walker)
can be queried for:

- `Edit` or `Document` control type;
- `TextPattern2::GetCaretRange`, whose `isActive` value states whether the
  caret-owning text control has keyboard focus (or `TextPattern` selection as a
  lower-version alternative); and
- `ValuePattern` with `IsReadOnly == false` where the provider exposes one.

Microsoft’s UIA specification says `Edit` and `Document` controls must support
`TextPattern`; if a text control supports selection or caret placement, its
provider must support selection APIs. `TextPattern` itself is read-only,
whereas `ValuePattern` explicitly exposes whether a string value is read-only.
[Microsoft: Text and TextRange patterns](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-about-text-and-textrange-patterns),
[provider requirements](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-implementingtextandtextrange), and
[ValuePattern](https://learn.microsoft.com/en-us/windows/win32/api/uiautomationclient/nn-uiautomationclient-iuiautomationvaluepattern).

This provides a strong **capability signal** only when the application’s focused
provider is accurate. It is not proof that simulated keyboard input or a later
clipboard transaction will be accepted. UIA calls are cross-process and
Microsoft notes that `TextPattern` has no caching mechanism; broad tree walking
is resource-intensive. Keep the query bounded and time-limited.
[Microsoft: TextPattern performance](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-about-text-and-textrange-patterns) and
[Microsoft: UIA tree-walking guidance](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-obtainingelements).

`TextPattern2::GetCaretRange` is the strongest UIA caret observation available
to a client, but it still does not establish mutability by itself:
`TextPattern` applies to controls that permit text entry **or** read-only text
selection. Pair an active caret range with a non-read-only `ValuePattern` when
present; do not reject a multiline editor merely because it lacks
`ValuePattern`.
[Microsoft: GetCaretRange](https://learn.microsoft.com/en-us/windows/win32/api/uiautomationclient/nf-uiautomationclient-iuiautomationtextpattern2-getcaretrange),
[Microsoft: Edit control type](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-supporteditcontroltype), and
[Microsoft: TextPattern / editable and selectable text](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-implementingtextandtextrange).

### 3. TSF is an integration protocol, not a universal observer

The Text Services Framework (TSF) maintains document managers and the
relationship between documents and input focus, but a text store is created and
exposed by the participating application/control. Reading or modifying it is
governed by that text store’s document locks and its `ITextStoreACP` sink.
[Microsoft: TSF Thread Manager](https://learn.microsoft.com/en-us/windows/win32/tsf/thread-manager) and
[Microsoft: Text Stores](https://learn.microsoft.com/en-us/windows/win32/tsf/text-stores).

Consequently, TSF is the right architecture for a text service that integrates
with TSF-aware controls; it is not an out-of-process, universal “does the
foreground app accept dictation?” probe that ClipAI can rely on. Treat TSF
availability as application-dependent rather than as a fallback to UIA.

### 4. Browsers, Electron, and custom accessibility trees are provider-dependent

Windows UIA intentionally abstracts frameworks, but it only sees the element
tree that an application/provider exposes. Microsoft supplies providers for
standard Win32, Windows Forms, and WPF controls; custom or third-party controls
need their own provider or proxy. Without one, a control is largely opaque to
UIA beyond basic HWND information. This covers browser-rendered editors,
Electron renderers, canvas editors, and any other custom surface: their actual
result must be queried at runtime and cannot be assumed from the process name.
[Microsoft: UIA Providers Overview](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-providersoverview) and
[Microsoft: client-side providers](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-clientsideprovider).
For web content, Windows maps ARIA `readonly` to UIA `IsReadOnly`, but that is
only useful when the browser and web application expose correct accessibility
semantics. [Microsoft: ARIA mapping to UIA](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-ariaspecification).

Microsoft Active Accessibility (MSAA) can add compatibility coverage—standard
edit and rich-edit controls expose a value. A legacy focused `ROLE_SYSTEM_TEXT`
object that is neither read-only, unavailable, nor protected is a reasonable
lower-confidence hint. MSAA does not turn unexposed custom controls into
reliable editable targets or provide a modern text-selection contract. Use it
only as compatibility evidence, not as a different truth owner.
[Microsoft: Custom UI elements / MSAA](https://learn.microsoft.com/en-us/windows/win32/winauto/custom-user-interface-elements).
[Microsoft: MSAA–UIA bridge](https://learn.microsoft.com/en-us/windows/win32/winauto/appendix-g--active-accessibility-bridge-to-ui-automation),
[Microsoft: MSAA edit control](https://learn.microsoft.com/en-us/windows/win32/winauto/edit-control), and
[Microsoft: object state constants](https://learn.microsoft.com/en-us/windows/win32/winauto/object-state-constants).

### 5. Security and privilege are hard boundaries

UIA does not communicate with processes started by different users. Higher
integrity and protected system UI are deliberately isolated. Microsoft describes
`uiAccess` as an assistive-technology mechanism requiring signing, secure
installation, and an appropriate manifest; it remains unable to access system
integrity UI. ClipAI should not adopt this privilege model merely to improve
routing.
[Microsoft: UI Automation overview](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-uiautomationoverview) and
[Microsoft: UI Automation security](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-securityoverview).

## Confidence matrix

The confidence is about recognising **an editable text-capable focused target**,
not about successful dictation or paste delivery. “No” never proves the inverse.

| Foreground surface | Evidence available | Positive confidence | Safe product interpretation |
| --- | --- | --- | --- |
| Standard Win32/Edit/RichEdit, same user and integrity | Focused UIA `Edit`/`Document`; active `TextPattern2` caret; non-read-only `ValuePattern` if available; GUI caret as corroboration | High | “Text input appears available”; retain normal explicit paste validation. |
| WPF / WinForms standard editable control, same user and integrity | Same UIA contract; Microsoft supplies standard-control providers | High | Same as above. |
| Office or another rich native editor | UIA evidence and/or GUI caret; exact provider shape is app/version-specific | Medium–high | Use as a hint only; integration-test named apps before promising behaviour. |
| Browser contenteditable / web app / Electron editor | Runtime UIA provider evidence only; may be nested or custom; browser ARIA semantics must be exposed correctly | Medium when affirmative; low when absent | Do not identify from process name. Absence means “unknown,” not “not editable.” |
| Canvas, terminal, game, bespoke or inaccessible editor | Possibly GUI caret; often no meaningful UIA text provider | Low | Keep targetless Voice Draft available; ask user to paste explicitly. |
| Password / secure field | UIA can report a password element; value retrieval may fail | High for *rejecting automatic content inspection* | Never expose or infer its contents; do not promise paste/dictation compatibility. |
| Elevated app, protected/system desktop, or another user session | UIA access may be denied/limited by integrity or user boundary | Low / unavailable | Fail closed for external target operations; do not elevate ClipAI for this feature. |
| Foreground is changing / transient menu | `GetGUIThreadInfo` can return invalid handles during activation change | Low | Recheck only at explicit output dispatch; do not route based on a stale observation. |

## Design recommendation

Do **not** make editable-target detection the mechanism that decides whether
`Ctrl+Alt+W` is “dictation” versus “ask a question.” It would be an unreliable
technical fact overloaded with product intent, especially in the browser and
Electron cases users care about.

If the product later wants a polish signal, introduce a platform-owned,
best-effort typed observation such as `ExternalTextTargetEvidence` with values
`confirmed_editable`, `text_caret_present`, `unknown`, `protected`, and
`unavailable`. `confirmed_editable` requires focused, active-caret UIA evidence
plus explicit writable evidence where the provider offers it; `text_caret_present`
does not claim writability.
It should be captured only at explicit user intent and reported to services via
a typed command. It must not become a second target owner, an input-routing
authority, or a replacement for the existing Clipboard Transaction Coordinator
and Paste Operation Coordinator. A false negative leaves normal Voice Draft
available; a false positive still requires the existing target validation at
paste time.

## Evidence limits and next step

This research establishes Windows API guarantees, not an empirical compatibility
claim for specific browser/Electron applications. Before product use, build a
manual Windows matrix for the foreground applications ClipAI actually targets
(for example, a standard editor, Word, browser `<input>`, browser
`contenteditable`, Electron editor, terminal, password field, and elevated
application). Record UIA patterns, GUI caret result, and the existing explicit
paste outcome—without retaining user text.
