from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clipai.actions import build_action_map, load_actions, load_config
from clipai.core.cancellation import CancellationController
from clipai.core.constants import EVENT_PIPELINE_UPDATE
from clipai.core.event_bus import EventBus
from clipai.providers.factory import build_provider
from clipai.services.action_service import ActionService
from clipai.services.resolve_config import resolve_action_config


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the minimal headless Ollama flow.")
    parser.add_argument("prompt", nargs="*", help="Prompt text. If omitted, stdin or interactive input is used.")
    parser.add_argument("--action", default=None, help="Action id from config/actions.yaml.")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config.yaml.")
    parser.add_argument("--model", default=None, help="Override model name.")
    parser.add_argument("--base-url", default=None, help="Override Ollama base URL.")
    parser.add_argument("--list-actions", action="store_true", help="List available actions and exit.")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming output.")
    return parser.parse_args()


def _read_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return " ".join(args.prompt).strip()
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    return input("Prompt: ").strip()


def _compose_system_prompt(app_cfg: dict, action_def: dict) -> str:
    global_prompt = str(app_cfg.get("system_prompt", "")).strip()
    action_prompt = str(action_def.get("system_prompt", "")).strip()
    parts = [part for part in (global_prompt, action_prompt) if part]
    return "\n\n".join(parts)


def _build_messages(app_cfg: dict, action_def: dict, user_input: str) -> list[dict[str, str]]:
    system_prompt = _compose_system_prompt(app_cfg, action_def)
    prompt_template = str(action_def.get("prompt") or action_def.get("template") or "{input}")
    rendered = prompt_template.replace("{input}", user_input)

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": rendered})
    return messages


def main() -> int:
    args = _parse_args()
    cfg = load_config(args.config)
    actions = load_actions(args.config)
    action_map = build_action_map(actions)

    if args.list_actions:
        for action in actions:
            action_id = action.get("id", "")
            name = action.get("name", "")
            hotkey = action.get("hotkey", "")
            print(f"{action_id}\t{name}\t{hotkey}")
        return 0

    app_cfg = cfg.get("app", {}) or {}
    provider_cfg = dict(cfg.get("provider", {}) or {})

    if args.base_url:
        provider_cfg["ollama_base_url"] = args.base_url

    default_action_id = str(app_cfg.get("default_action") or "translate_zh_tw")
    action_id = args.action or default_action_id
    action_def = action_map.get(action_id)
    if not action_def:
        print(f"Unknown action: {action_id}", file=sys.stderr)
        return 1

    prompt = _read_prompt(args)
    if not prompt:
        print("Prompt is empty.", file=sys.stderr)
        return 1

    bus = EventBus()
    provider = build_provider(provider_cfg)
    service = ActionService(bus, provider)
    ctrl = CancellationController()

    if not args.no_stream:
        bus.subscribe(EVENT_PIPELINE_UPDATE, lambda payload: print(payload.get("content", ""), end="", flush=True))

    runtime_flags = {
        "provider": provider_cfg.get("provider", "ollama"),
        "model": args.model or provider_cfg.get("default_model"),
        "stream": not args.no_stream,
        "temperature": action_def.get("temperature", app_cfg.get("temperature", 0.2)),
    }
    config = resolve_action_config(
        action_def,
        mode="headless",
        runtime_flags=runtime_flags,
    )
    messages = _build_messages(app_cfg, action_def, prompt)

    result = service.run_action(
        config,
        messages,
        rhythm_params=None,
        cancellation_token=ctrl.token,
        source_meta=None,
    )

    if args.no_stream:
        print(result.content)
    else:
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
