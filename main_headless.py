from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clipai.core.cancellation import CancellationController
from clipai.core.constants import EVENT_PIPELINE_UPDATE
from clipai.core.event_bus import EventBus
from clipai.providers.factory import build_provider
from clipai.services.action_service import ActionService
from clipai.services.resolve_config import resolve_action_config


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the minimal headless Ollama flow.")
    parser.add_argument("prompt", nargs="*", help="Prompt text. If omitted, stdin or interactive input is used.")
    parser.add_argument("--model", default="llama3.2", help="Ollama model name.")
    parser.add_argument("--base-url", default="http://localhost:11434", help="Ollama base URL.")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming output.")
    return parser.parse_args()


def _read_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return " ".join(args.prompt).strip()
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    return input("Prompt: ").strip()


def main() -> int:
    args = _parse_args()
    prompt = _read_prompt(args)
    if not prompt:
        print("Prompt is empty.", file=sys.stderr)
        return 1

    bus = EventBus()
    provider = build_provider(
        {
            "provider": "ollama",
            "ollama_base_url": args.base_url,
        }
    )
    service = ActionService(bus, provider)
    ctrl = CancellationController()

    if not args.no_stream:
        bus.subscribe(EVENT_PIPELINE_UPDATE, lambda payload: print(payload.get("content", ""), end="", flush=True))

    config = resolve_action_config(
        {
            "id": "headless_ollama",
            "name": "Headless Ollama",
            "model": args.model,
            "stream": not args.no_stream,
            "temperature": 0.2,
            "output_popup": False,
            "output_clipboard": False,
            "output_paste": False,
            "output_notify": False,
        },
        mode="headless",
    )

    result = service.run_action(
        config,
        [{"role": "user", "content": prompt}],
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
