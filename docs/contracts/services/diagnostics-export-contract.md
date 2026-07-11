# Diagnostics Export Contract

Tray emits `ExportDiagnostics`; runtime supervises an injected exporter and reports completion through `UserNotifier`.

The archive contains curated application/runtime metadata and a bounded, redacted log tail. It must not contain credentials, environment values, clipboard or selection text, prompts, provider input/output, or archive content. Sensitive key assignments and resolved secret values are redacted before writing.

Unexpected failures receive a short incident ID. Full traceback stays in the log; user-facing feedback contains only the incident reference.
