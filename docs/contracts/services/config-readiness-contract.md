# Config And Readiness Contract

- App config currently uses schema v2, the canonical Action skeleton uses schema v11, shortcuts use schema v1, output-profile skeleton uses schema v2, entry-panel config uses schema v1, and Action Language Pack registry/manifest/resources use their own schema v1 contracts. Each loader owns its supported version instead of relying on one global catalog version.
- Missing or unsupported versions are rejected. User files are never rewritten implicitly.
- Future schema versions are rejected with file and version information.
- Only the composition root reads environment variables. Provider credentials are injected and their values never appear in repr, logs, or diagnostics.
- Missing active-provider credentials and an incomplete Custom provider connection (URL or model not yet configured) are non-fatal readiness issues: the app starts, tray stays warning, opens Provider Settings, and actions fail in their popup before input or network work. A configured Custom provider is not contacted during startup; an unavailable third-party service is reported only after the user explicitly runs an Action or validates the settings.
- Malformed YAML, unsupported fields, invalid values, unsupported logging levels, and an invalid default Action Language Pack are fatal startup errors shown through the startup error surface. Invalid non-default packs are omitted; an invalid selected pack falls back atomically to the valid default without rewriting selection.
