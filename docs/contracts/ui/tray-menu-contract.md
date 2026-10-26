# Tray menu

Tray uses English interface labels and native language names (繁體中文,
English, 日本語). The ready menu is ordered as follows, with capability-dependent
entries omitted when their injected callback or state is unavailable:

1. Read-only application status, then provider/model summary.
2. Voice Input, Inline Dictation, Speech Speed.
3. Settings & Models…, Personal Styles…, Action Language, Shortcut Guide….
4. Support and Diagnostics (Show Last Error, Export Diagnostics…), About & Updates….
5. Quit.

Separators divide these groups. The tooltip retains application version and
status. Voice Input shows the selected language when ready, and the actual
capability state when setup, disabling, or recovery requires attention. Its
submenu lists language radios first, followed by a separator, microphone
permission settings, and the state-aware enable/disable command last, with
existing capability gates. Action Language normally has no language suffix;
its language radios show the saved selection. Pending, failed, and restart-only
selection states still show the current/next-start distinction in its label.

Inline Dictation contains only Full Choice and Minimal Input. Shortcut migration
and AltGr configuration guidance remain in Shortcut Guide. No menu exposes
position settings; all primary and Inline surfaces use fixed bottom-center
placement, as defined in `window-placement-contract.md`.

Voice language names belong to the UI's existing voice language labels. Action
Language names come from each pack's descriptor/manifest `display_name`; Tray
must not maintain an independent pack-name lookup. Pending writes retain the
saved radio selection and disable conflicting choices. Action Language must
distinguish the active pack from the saved next-start pack until restart.

Menu callbacks emit the existing typed commands through composition. Reordering
or relabeling does not create a new settings owner, change language-pack
behavior, or trigger provider/clipboard/voice side effects on menu opening.

Regression coverage: `tests/ui/test_tray.py` and
`tests/app/test_official_action_language_packs.py`.
