# Fixed bottom-center window placement

Popup, Unified Entry Panel, and Inline Dictation open at the bottom center of
the monitor work area sampled when the new surface is shown. Display metrics
come from the existing injected platform reader, using the pointer's monitor
and excluding the taskbar. Pointer movement after opening does not reposition
an existing surface. There is no Follow Cursor option or placement preference.

`PopupLayoutPolicy` calculates initial Popup/Panel bounds with a scaled
16-unit bottom margin. `PrimarySurfaceHost` alone owns bounds and dragging.
Users may drag the header; navigation, streaming, regeneration, and the
identity-matched Panel-to-Popup replacement retain the existing bounds.
Closing the shell and opening a new shell uses bottom center again; dragging
does not save a preferred position.

`InlinePill` samples its display metrics/DPI once before showing, using its
existing scaled 8-unit margin. Its reserved notification space is above the
Pill. Status, Copy updates, and notification expansion never move or resize
the window, and showing or clicking the Pill never activates it. Its lifecycle
port carries interaction identity and input mode, not positioning policy.

`UserPreferencesCoordinator` retains its existing ownership and save gate for
other preferences. Placement commands, projections, presenters, and composition
readers are removed. `JsonUserPreferencesStore` accepts legacy schema versions
1–9; obsolete `popup_placement` and `inline_dictation_placement` fields are
ignored regardless of their values. Loading never writes a migration file.
The next ordinary atomic save uses schema 10 without those fields, retaining
all other supported preference values.

Regression coverage: `tests/ui/test_popup_layout.py`,
`tests/ui/test_inline_pill.py`, `tests/ui/test_primary_surface.py`,
`tests/platform/test_json_guidance_preferences.py`, and `tests/ui/test_tray.py`.
