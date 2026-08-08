# Speech Speed Preferences Contract

`UserPreferencesCoordinator` is the single owner of persisted Speech Speed, its pending operation identity, stale-completion rejection, and failure rollback. It shares the atomic `data/user_preferences.json` aggregate and operation gate with first-use guidance; provider settings remain independently owned because they persist to `.env`.

The legal presets are `slow`, `normal`, `fast`, and `super_fast`, mapped to Edge TTS rates `-25%`, `+0%`, `+25%`, and `+50%`. Missing preference data preserves the configured `tts.rate`. A configured rate outside those presets remains effective and projects as Custom until an explicit preset is saved.

Tray emits `SetSpeechSpeed` and continues to show the previous checked preset while persistence is pending. Only the matching completion may commit or roll back the projection; repeated selection, unavailable speech, overlapping preference work, and stale completion are ignored.

`SpeechCoordinator` reads the effective rate when speech work begins and places it on the immutable `SpeechRequest`. Popup speech, global selection-or-clipboard speech, and shortcut-sequence speech all use this path. A later preference change affects only future speech and never restarts or mutates active playback.
