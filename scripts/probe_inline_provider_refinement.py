"""Exercise the production Inline refinement Action with a fixed test phrase.

Uses the current Action pack, provider binding, prompt builder, provider transport,
result processor, and Inline coordinator. It neither accesses the clipboard nor
dispatches Paste, and it never persists the response text. It may make one real
provider API request.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import threading

from dotenv import dotenv_values

from ClipAI.app.application_paths import build_application_paths
from ClipAI.app.inline_dictation import INLINE_REFINEMENT_TIMEOUT_SECONDS, InlineDictationCoordinator
from ClipAI.app.language_pack_bootstrap import bootstrap_action_language_config
from ClipAI.app.provider_configuration import build_provider_snapshot
from ClipAI.app.provider_execution import ProviderExecutionModule
from ClipAI.core.models import PasteTarget
from ClipAI.platform.action_language_selection import JsonActionLanguagePackSelectionStore
from ClipAI.providers.http_transport import HttpxAsyncTransport
from ClipAI.services.execute_action import ActionExecutor
from ClipAI.services.input_resolver import InputResolver
from ClipAI.services.prompt_builder import PromptBuilder
from ClipAI.services.result_processor import ResultProcessor

if __package__:
    from .probe_inline_voice_chain import _reference
else:
    from probe_inline_voice_chain import _reference


ROOT = Path(__file__).resolve().parents[1]


class NoClipboard:
    def read_text(self) -> str:
        raise AssertionError("Inline refinement probe must not read the clipboard")


@dataclass(frozen=True)
class Settlement:
    returned_nonempty: bool
    output_changed: bool
    failure_reason: str | None


def content_safe_report(
    *, fixture_sha256: str, provider: str, pack: str,
    settlement: Settlement | None, paste_calls: int,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "scope": "live_inline_refinement_provider_boundary",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "fixture_sha256": fixture_sha256,
        "provider": provider,
        "action_pack": pack,
        "status": (
            "pass" if settlement is not None and settlement.returned_nonempty
            and settlement.failure_reason is None and paste_calls == 0
            else "blocked" if settlement is None else "fail"
        ),
        "returned_nonempty": settlement.returned_nonempty if settlement else False,
        "output_changed": settlement.output_changed if settlement else None,
        "failure_reason": settlement.failure_reason if settlement else "settlement_not_observed",
        "paste_calls": paste_calls,
        "response_text_saved": False,
        "limits": "No WebView recognition, physical shortcut, Tk frame, or target insertion is exercised.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-file", type=Path, required=True, help="SHA-matched fixed fixture whose phrase is sent to the provider")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.audio_file.resolve()
    phrase = _reference(source)
    if not phrase:
        parser.error("audio fixture must have a SHA-matched manifest phrase")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    paths = build_application_paths(ROOT, os.environ)
    bootstrap = bootstrap_action_language_config(
        JsonActionLanguagePackSelectionStore(paths.state_file("action_language_pack.json")),
        app_config_path=paths.config_file("config.yaml"),
        actions_path=paths.config_file("actions.yaml"),
        shortcuts_path=paths.config_file("shortcuts.yaml"),
        output_profiles_path=paths.config_file("output_profiles.yaml"),
        entry_panel_path=paths.config_file("entry_panel.yaml"),
    )
    bundle = bootstrap.bundle
    action = bundle.actions.resolve("intent_preserving_dictation_editor", "short")
    environment = {**os.environ, **{
        key: value for key, value in dotenv_values(paths.secrets_file).items()
        if value is not None
    }}
    transport = HttpxAsyncTransport()
    snapshot = build_provider_snapshot(bundle, environment, transport)
    binding = next(item for item in snapshot.bindings if item.provider_id == snapshot.active_provider)
    if binding.readiness_issues:
        report = content_safe_report(
            fixture_sha256=digest, provider=binding.provider_id,
            pack=bootstrap.state.active_pack.pack_id, settlement=None, paste_calls=0,
        )
        report["failure_reason"] = "provider_not_ready"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report))
        return 2
    executor = ActionExecutor(
        input_resolver=InputResolver(NoClipboard()),
        prompt_builder=PromptBuilder(bundle.app.system_prompt, bundle.output_profiles),
        result_processor=ResultProcessor(bundle.output_profiles),
        default_temperature=bundle.app.temperature,
    )
    provider_execution = ProviderExecutionModule(transport)
    completed = threading.Event()
    settlements: list[Settlement] = []
    paste_calls: list[None] = []

    def settled(_interaction_id, _operation_id, text, error, failure_reason) -> None:
        settlements.append(Settlement(not error and bool(text.strip()), text != phrase if text else False, failure_reason))
        completed.set()

    coordinator = InlineDictationCoordinator(
        provider_execution=provider_execution,
        executor=executor,
        refine_action=action,
        binding=lambda: binding,
        paste=lambda *_args: paste_calls.append(None),
        on_refine_settled=settled,
    )
    try:
        admitted = coordinator.submit(
            phrase, PasteTarget("probe-only", 0, "Probe", "test", 0),
            refine=True, interaction_id="probe-inline", operation_id="probe-refine",
        )
        if admitted:
            completed.wait(timeout=INLINE_REFINEMENT_TIMEOUT_SECONDS + 5)
    finally:
        provider_execution.shutdown()
    report = content_safe_report(
        fixture_sha256=digest, provider=binding.provider_id,
        pack=bootstrap.state.active_pack.pack_id,
        settlement=settlements[0] if settlements else None,
        paste_calls=len(paste_calls),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
