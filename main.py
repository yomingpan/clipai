from __future__ import annotations

import multiprocessing
import os
from pathlib import Path

from ClipAI.app.application_lifecycle import build_application_instance_gate
from ClipAI.app.application_paths import build_application_paths
from ClipAI.app.language_pack_bootstrap import bootstrap_action_language_config
from ClipAI.app.container import build_runtime
from ClipAI.core.errors import ConfigError
from ClipAI.core.ports import ApplicationInstanceGate
from ClipAI.platform.action_language_selection import JsonActionLanguagePackSelectionStore
from ClipAI.ui.startup_error import show_startup_error

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def main(*, instance_gate: ApplicationInstanceGate | None = None) -> None:
    paths = build_application_paths(Path(__file__).resolve().parent, os.environ)
    instance_gate = instance_gate or build_application_instance_gate()
    instance_lease = instance_gate.acquire()
    if instance_lease is None:
        show_startup_error("ClipAI is already running.")
        return
    try:
        if load_dotenv:
            load_dotenv(paths.secrets_file, override=True)

        bootstrap = bootstrap_action_language_config(
            JsonActionLanguagePackSelectionStore(
                paths.state_file("action_language_pack.json")
            ),
            app_config_path=paths.config_file("config.yaml"),
            actions_path=paths.config_file("actions.yaml"),
            shortcuts_path=paths.config_file("shortcuts.yaml"),
            output_profiles_path=paths.config_file("output_profiles.yaml"),
            entry_panel_path=paths.config_file("entry_panel.yaml"),
        )
        runtime = build_runtime(bootstrap, paths=paths)
        runtime.run_forever()
    except ConfigError as exc:
        show_startup_error(str(exc))
        raise SystemExit(2) from None
    finally:
        if instance_lease is not None:
            instance_lease.close()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
