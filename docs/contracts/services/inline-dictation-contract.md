# Inline Dictation contract

[ADR-0022](../../adr/0022-right-alt-inline-pill-and-input-recovery.md) is authoritative
where it amends ADR-0019/0018. Inline Dictation is one
non-Workflow interaction from the first accepted solo `Right Alt` release through
capture, delivery decision, optional refinement, Paste settlement, and a
terminal notice or explicit discard. `VoiceInputController` owns that semantic
lifetime. Capture, provider invocation, Paste Operation, and view leases retain
separate identities. Runtime routes typed effects and matching acknowledgements;
it does not create another interaction registry.
The Windows adapter admits solo Right Alt only when no other key is held.
Another physical key cancels that press; injected keys do not participate and
mouse clicks do not cancel it. At 0.5 seconds a matching press may emit preview
only. Release emits Invoked before Ended; an unchorded release claims the menu
mask once, a chorded release never claims it. Right Alt never opens Entry Panel.
The default has no Ctrl+Alt+M alias or printable-M suppression. AltGr layouts
must choose another chord in `config/shortcuts.yaml`; guide and tray explain
that migration. See `tests/platform/test_right_alt_hotkey.py`, `test_hotkey.py`
and `tests/services/test_shortcut_guide.py`.
While the same interaction is active, exact physical Esc is consumed by the
hotkey adapter and still delivered to ClipAI's ordered interruption queue;
the foreground application must not receive it. An unpinned foreground Popup
also owns unmodified Esc when ClipAI lacks focus. The first Esc cancels the
latest interruptible operation; an idle second Esc closes that Popup. A pinned
Popup and modified Esc leave the physical key to the foreground application.
The modifier check includes Ctrl, Alt, Shift, and either Windows key; a
modified repeat is also passed through. A consumed key-up remains consumed
even if the owning window closes before physical release.
Capture ID and Inline Interaction ID have distinct generated values. The existing
diagnostics log records content-free, monotonic lifecycle stages keyed by these
IDs and the provider/Paste operation IDs. A requested UI presentation is not
evidence that its first frame was visible, and Paste Dispatch is not insertion.

## User journeys

| Mode and intent | Observable journey | Required outcome |
| --- | --- | --- |
| Either mode, idle short or long | Freeze the external target and begin capture on release. | No delivery intent from the start gesture or timer. |
| Either mode, short stop | Stop recognition with explicit raw delivery; request Paste once canonical text exists. | The same nonactivating Pill remains visible. |
| Either mode, long stop | Stop with explicit refinement delivery; refine then request Paste. | Threshold only previews; release creates the one intent. |
| Automatic stop, then explicit choice | Show complete text in the same Pill's review panel with no chosen delivery. Short/✓ selects raw; long/✦ selects refinement. | No Paste or provider before that choice. |
| Mode change during capture | Save the selected mode through a typed tray command. | A failed save changes nothing; a successful save affects only later interactions. |
| No speech or recognition failure | Stop or timeout without usable canonical text. | No Paste; show a truthful retryable failure. Preserved recognized text remains recoverable when available. |
| Refinement unavailable, failed, or empty | Preserve the original text and show complete text in recovery. | Offer explicit Paste raw, Copy, or Discard. Never silently Paste the original. |
| Frozen target invalid or focus refused | Reject the Paste attempt without selecting a new foreground target. | Keep complete text and Copy/manual-paste guidance visible. |
| Esc during capture, refinement, or Paste | Cancel only the matching operation. | After discard, no new Paste admission; wait for provider cancellation admission or Paste settlement before allowing a new capture. Dispatch cannot be undone. |
| Paste terminal acknowledgement | Route the matching Paste Operation outcome to the controller. | `dispatched_unconfirmed` says the shortcut was sent and asks the user to check the original field; `failed`, `cancelled`, and `cleanup_failed` show their distinct recovery and cleanup truth. Never claim insertion success. |

The shared Pill and review/recovery panel may only close under the current
interaction and view lease. A late provider result, Paste acknowledgement, or
terminal dwell callback from an older interaction cannot change or close a
newer one. A second shortcut during refinement or pending Paste is rejected
with visible feedback. A new capture is admitted only after the preceding
interaction reaches a settled, dismissible terminal phase.
New installs with no preferences file start in Minimal; existing preferences
and corrupt-file ordinary defaults retain their existing mode behavior. See
`tests/platform/test_json_guidance_preferences.py`.

The Inline window freezes its placement at interaction start. `cursor` uses
the starting pointer position; `bottom_center` uses the work area's bottom
center and is the default for both Full Choice and Minimal Input. A reserved
transparent area holds panel expansion away from the nearer work-area edge;
content and Copy updates never move or resize the window. Placement is saved
atomically through the shared preference gate; invalid
or unchanged values do not write. The Tray offers the two modes and both
placement choices with pending state. Each new Pill samples starting display
metrics/DPI before placing and rendering; later updates keep that layout.
`InlineDictationInterfaceOwner` alone owns its window and interaction ID;
`OwnedModalRegistry` alone owns the five root-owned dialogs.
View Confirm, Copy, and Esc callbacks carry the interaction ID captured when
their window was created. The controller rejects a callback from an older
window even if a newer Inline interaction is now in a compatible phase.
`VoiceInputController` alone projects frozen `InlineDictationView` on each
transition: phase, chosen, preview_refine, allow_refine, audio/silence/countdown,
canonical text, message, Paste outcome and Copy lifecycle. Runtime forwards that
view unchanged through open/present/close; it does not infer presentation from
effects. Refinement settlement preserves chosen=refine. The owner compares the
identity before changing or closing the view. See
`tests/services/test_inline_dictation_view.py` and `tests/app/test_runtime_voice_input.py`.
During capture cancellation, the status remains visible as cancelling until
the matching engine terminal event or six-second watchdog settles it. A normal
cancel closes without a failure flash; a watchdog timeout reports the missing
acknowledgement before closing.

The Pill is 160×36 logical pixels on a 300-wide reserved canvas, with an
18-pixel status strip and an 8-pixel scaled work-area margin. The same window
holds a 300×136 notification card, padding-12 and radius-10, with a short
localized title and explanation. It has no transcript, text editor, scrollbar
or dropdown. A 72×24 Copy Content button appears only when content is available;
the existing typed copy intent consumes the complete owner-held content.
UI does not bind Enter or Ctrl+P here. A first explicit
delivery click locks until phase changes; stale view/callback identities are
ignored. Terminal Dismiss is scheduled once per interaction, at 600 ms for
dispatched_unconfirmed or 1200 ms for cancelled. See `tests/ui/test_inline_pill.py`
and `tests/ui/test_inline_dictation_owner.py`.

`voice_visuals` is the sole palette/status/raster source for Pill and Popup
voice controls. Rounded edges blend with the one pre-show memory-only backdrop;
fully transparent pixels use #010203. Waveforms follow real level, become a flat
muted line at silence/zero, and show 無聲 where required. Static phases schedule
no frames; active animation uses 80 ms. Golden colors, copy/status strings,
chosen/spinner mapping and border states are in `tests/ui/test_voice_visuals.py`;
`tests/architecture/test_voice_visuals_contract.py` prevents duplicated visuals.
Buttons are circular, 24×24 with six logical pixels of shell clearance; the two delivery
buttons have an eight-pixel gap. Hover brightens an enabled button without
moving its geometry. The charcoal shell uses one continuous light-gray outline;
there is no separate top highlight stroke. Cancel and refine use gray circular fills; the enabled confirm uses
a white circular fill. The enabled sparkle has a subtle, stationary white halo.
During refinement, the fixed sparkle is surrounded by a 1.5-pixel fading,
slightly violet quarter-circle light, moving clockwise once per 1600 ms. It stops when the
real refinement phase ends; paste status continues to reflect its own lifecycle.
This visual revision supersedes the original 132×26 dimensions; historical
latency and focus evidence in ADR-0022 describes that original geometry.
Typed `capture_notice` facts originate in `VoiceInputController` and distinguish
permission, service, initialization, interruption, timeout, no speech, time limit,
and incomplete recognition. UI never interprets English diagnostic strings.
See `docs/design/inline-pill-feedback.md` for the full presentation matrix.

Native display order is anchor/DPI → place → capture → draw → deiconify →
show_without_activation → prevent_click_activation → animation. Mapping must
settle before applying native policy because Tk can replace its native wrapper.
The root owns only a hidden fixed-pixel Tk raster resource; no background or
dictated text enters that resource or the bounded static geometry cache.
The native style survives a subsequent full event turn in the Pill integration
test. Six external-app cases and zero-black-fringe evidence are linked by ADR-0022.
Capture failures without recoverable text show a three-second terminal notice
with inactive status before the view closes; the previous listening or
finalizing label must not remain active during that notice. Starting a newer
interaction retires that older notice immediately so it cannot cover the new
status view; any late close request remains scoped to the older view lease.

The engine promotes its last interim segment once on stop and discards it on
cancel. The 120-second listening limit begins only on the matching Listening
event. The six-second stop/cancel watchdog produces a retryable timeout, never
a fabricated success. No provider call or Paste follows from opening,
rendering, focusing, or closing a view.

`ProviderExecutionModule` owns the provider task and cancellation admission;
`PasteOperationCoordinator` owns dispatch, cancellation, and terminal truth;
`ClipboardTransactionCoordinator` owns temporary clipboard preservation.
Esc before Paste Dispatch requests cancellation and restoration through these
owners. After dispatch, report only `dispatched_unconfirmed` or the actual
cleanup failure; do not retry automatically.
If provider cancellation has not settled after six seconds, the matching
interaction shows an unconfirmed cancellation state with complete original
text and Copy. Esc may retry the same provider operation cancellation. A new
capture remains blocked until a matching cancellation admission or provider
settlement; the timeout alone does not count as acknowledgement or permit Paste.
