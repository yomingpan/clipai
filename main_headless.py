from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clipai.capabilities.actions.action_registry import load_app_config
from clipai.capabilities.actions.action_runner import ActionRunner, RunRequest
from clipai.capabilities.actions.output_applier import OutputModeError
from clipai.services.runtime_context import build_runtime_context


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the minimal headless Ollama flow.")
    parser.add_argument("prompt", nargs="*", help="Prompt text. If omitted, stdin or interactive input is used.")
    parser.add_argument("--action", default=None, help="Action id from config/actions.yaml.")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config.yaml.")
    parser.add_argument("--model", default=None, help="Override model name.")
    parser.add_argument("--base-url", default=None, help="Override Ollama base URL.")
    parser.add_argument("--list-actions", action="store_true", help="List available actions and exit.")
    parser.add_argument("--apply-output", action="store_true", help="Apply the action output mode instead of only printing.")
    parser.add_argument("--use-selection", action="store_true", help="Try to capture highlighted text via Ctrl+C before falling back to clipboard.")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming output.")
    return parser.parse_args()


def _read_explicit_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return " ".join(args.prompt).strip()
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    return ""


def main() -> int:
    args = _parse_args()
    bundle = load_app_config(args.config)

    if args.list_actions:
        for action in bundle.actions:
            action_id = action.get("id", "")
            name = action.get("name", "")
            hotkey = action.get("hotkey", "")
            print(f"{action_id}\t{name}\t{hotkey}")
        return 0

    default_action_id = str(bundle.app_cfg.get("default_action") or "translate_zh_tw")
    action_id = args.action or default_action_id
    action_def = bundle.action_map.get(action_id)
    if not action_def:
        print(f"Unknown action: {action_id}", file=sys.stderr)
        return 1

    output_mode = str(action_def.get("output_mode") or "stdout")
    should_stream_to_stdout = (not args.apply_output) or output_mode == "stdout"
    runner = ActionRunner(bundle)
    runtime = build_runtime_context(
        mode="headless_cli",
        apply_output=args.apply_output,
        use_selection=args.use_selection,
        stream_enabled=not args.no_stream,
        stream_to_stdout=(not args.no_stream and should_stream_to_stdout),
    )

    if args.apply_output:
        try:
            outcome = runner.run(
                RunRequest(
                    action_id=action_id,
                    explicit_text=_read_explicit_prompt(args),
                    model_override=args.model,
                    base_url_override=args.base_url,
                ),
                runtime,
            )
        except OutputModeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if not args.no_stream:
            print()
        return 0

    try:
        outcome = runner.run(
            RunRequest(
                action_id=action_id,
                explicit_text=_read_explicit_prompt(args),
                model_override=args.model,
                base_url_override=args.base_url,
            ),
            runtime,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.no_stream:
        print(outcome.result.content)
    elif not runtime.stream_to_stdout:
        print(outcome.result.content)
    else:
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
