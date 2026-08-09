# Voice Input V1 completion audit

This audit maps the clean-rebuild plan to evidence on `feature/voice-input`.
It is intentionally not a release approval: hardware and interactive-WebView
evidence is still required before Voice Input V1 can be marked released.

## Implementation and ticket evidence

| Plan area | Branch evidence |
| --- | --- |
| Plan, reconstruction boundary, and tiny-commit sequence | `c17c803`, [development plan](../specs/voice-input-v1-rebuild-development-plan.md) |
| Typed identities, commands, controller state machine, single-flight press mapping, and race policy | `311dbb5`, `0f35027`, `1cf58d5`, `61ef794`; `tests/core/test_voice_contracts.py`, `tests/services/test_voice_input.py` |
| Workflow-owned draft, selection/caret insertion, explicit Action/Back, and frozen Paste target | `79387af`, `be8d9ee`, `0a61efb`, `801cbae`; `tests/services/test_voice_workflow_origin.py` |
| Queue-based runtime composition, preferences, supported language, and one supported backend | `723e73b`, `91a270d`, `fdbd0dc`, `4fa7616`, `512e9f6`, `60019af`, `1288ba4`; `tests/app/test_config.py`, `tests/app/test_runtime_voice_input.py` |
| Browser Speech protocol, host lifecycle, terminal settlement, EOF/write failure, and safety watchdog | `5310ccc`, `8c859ff`, `f360ef0`, `63f8fd6`; `tests/platform/test_browser_speech.py`, `tests/platform/test_voice_webview_host_integration.py` |
| Setup/privacy, Tray projection and permission repair, editable Review, stop/cancel, and shortcut guide | `695300e`, `6d1b6ce`, `0a330e7`, `3bb721a`, `540aeac`, `8d7d6e0`, `055fecb`; `tests/ui/test_result_dialog.py`, `tests/ui/test_tray.py` |
| Listener shutdown, workflow close, disable and cleanup behavior | `b1bd499`, `dfe0db2`, `76825ad`; platform/service/runtime Voice tests |
| Release checklist and bridge invocation | `92fb7e6`, `09435a2`, `63f8fd6`; [manual release checklist](voice-input-v1-manual-release-checklist.md) |

## Automated evidence

Recorded on this branch after `63f8fd6`:

```text
python -m pytest tests/architecture tests/core tests/services tests/app tests/platform tests/ui -m "not integration"
650 passed, 5 deselected

python -m pytest -m integration
4 passed, 1 skipped, 684 deselected

python -m compileall ClipAI scripts tests
PASS
```

The skipped test is the controlled WebView bridge harness. It correctly
requires an interactive Windows desktop with Edge WebView2 Runtime, and is
enabled only with `CLIPAI_RUN_VOICE_WEBVIEW_INTEGRATION=1`. It uses fake media
and recognition implementations; it is not evidence about a real microphone.

Wheel packaging remains unverified in this local virtual environment. It lacks
`setuptools` and `wheel`; installing them fails inside the existing pip/
truststore stack with a `RecursionError`. The development plan explicitly
excludes the unrelated pip certificate/build-isolation change, so this branch
does not alter that tooling. Run the release wheel build in the clean CI or
release environment after its standard build dependencies are available.

## Remaining release evidence

Before release approval, run the controlled bridge integration and every row in
the manual matrix on both Windows 10 and Windows 11. Record dates, OS build,
WebView2 Runtime version, microphone device, and permission state in the
[manual release checklist](voice-input-v1-manual-release-checklist.md).

The release decision must remain pending until those dated results exist. In
particular, only that matrix can establish real microphone indicator cleanup,
browser permission persistence/repair behavior, and actual external-app Paste
target behavior.
