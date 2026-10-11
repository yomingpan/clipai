# Experimental window placement

The Tray exposes `Popup Window Position` immediately below `Inline Dictation`.
Popup and Inline Dictation independently offer `Follow Cursor` (`cursor`) and
`Bottom Center` (`bottom_center`). Both default to Bottom Center. Inline input
mode remains independent of placement; Full Choice and Minimal Input share the
same Inline placement preference.

`UserPreferencesCoordinator` owns both saved choices and their shared save gate.
Tray callbacks only enqueue `SetPopupPlacement` / `SetInlineDictationPlacement`.
The existing preference runtime persists on an interactive worker and projects
pending and typed completion on the UI thread. Radio checks stay on the saved
choice during Saving; failed saves retain that choice and report the error.
Schema 8 persists both preferences. Missing or invalid placement values use
Bottom Center, while valid saved Inline choices from schema 7 remain intact.

The composition root injects the saved Popup placement reader into the existing
`PopupLayoutPolicy`. It calculates initial bounds in the pointer monitor's work
area, excluding the taskbar, with physical position and toolkit logical size.
Bottom Center centers the physical width and uses the existing scaled 16-unit
bottom margin. Follow Cursor retains the previous cursor-relative clamping.
The Entry Panel uses this same policy because it shares the primary shell.
`PrimarySurfaceHost` remains the only owner of bounds and dragging. An existing
Popup, Panel navigation, streaming update, and identity-matched Panel-to-Popup
replacement retain existing bounds. A saved choice affects the next new shell;
Inline freezes its choice at the next interaction start.
