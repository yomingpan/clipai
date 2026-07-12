# Config And Readiness Contract

- App, shortcuts, and output-profile catalogs currently use schema v1; actions use schema v3 for explicit `input_policy`. Each loader owns its supported version instead of relying on one global catalog version.
- Missing version is legacy v0 and is migrated only in memory. User files are never rewritten implicitly.
- Future schema versions are rejected with file and version information.
- Only the composition root reads environment variables. Provider credentials are injected and their values never appear in repr, logs, or diagnostics.
- Missing active-provider credentials are non-fatal readiness issues: the app starts, tray stays warning, and actions fail in their popup before input or network work.
- Malformed YAML, unsupported fields, invalid values, and unsupported logging levels are fatal startup errors shown through the startup error surface.
