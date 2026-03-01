from __future__ import annotations

import argparse
import os
import re
import sys

from dotenv import load_dotenv

from ClipAI.app_factory import build_app
from ClipAI.core.llm_provider import LLMError, LLMRateLimitError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ClipAI v2 launcher")
    parser.add_argument("--provider", default="gemini", help="Provider name: gemini|olama|azure_openai|openai_compact")
    parser.add_argument("--ui", action="store_true", help="Enable Tk UI event loop")
    parser.add_argument("--action", default="summarize", help="Action key from actions registry")
    parser.add_argument("--model", default="", help="Override model name for current run")
    return parser.parse_args()


def _build_runtime_config(provider: str, ui_enabled: bool) -> dict:
    provider_l = provider.lower()
    cfg: dict = {"provider": provider_l, "enable_ui": ui_enabled}

    if provider_l == "gemini":
        cfg["gemini_api_key"] = os.getenv("GEMINI_API_KEY", "")
        cfg["gemini_base_url"] = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")
        cfg["default_model"] = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    elif provider_l == "olama":
        cfg["olama_base_url"] = os.getenv("OLAMA_BASE_URL", "http://localhost:11434")
        cfg["default_model"] = os.getenv("OLAMA_MODEL", "gemma3:1b")
    elif provider_l == "azure_openai":
        cfg["azure_api_key"] = os.getenv("AZURE_OPENAI_API_KEY", "")
        cfg["azure_endpoint"] = os.getenv("AZURE_OPENAI_ENDPOINT", "")
        cfg["default_model"] = os.getenv("AZURE_OPENAI_MODEL", "")
    elif provider_l == "openai_compact":
        cfg["openai_api_key"] = os.getenv("OPENAI_API_KEY", "")
        cfg["default_model"] = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    return cfg


def _extract_retry_seconds(message: str) -> float | None:
    patterns = [
        r"retry in\s+([0-9]+(?:\.[0-9]+)?)s",
        r'"retryDelay"\s*:\s*"([0-9]+)s"',
    ]
    for p in patterns:
        m = re.search(p, message, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return None
    return None


def main() -> int:
    load_dotenv()
    args = parse_args()
    runtime_cfg = _build_runtime_config(args.provider, args.ui)
    app = build_app(runtime_cfg)

    if args.ui:
        lifecycle = app.get("dialog_lifecycle")
        if lifecycle is None:
            print("UI requested but dialog lifecycle is unavailable.", file=sys.stderr)
            return 1
        lifecycle.run()
        return 0

    controller = app["controller"]
    runtime_flags: dict = {}
    model = args.model.strip() or str(runtime_cfg.get("default_model", "")).strip()
    if model:
        runtime_flags["model"] = model

    try:
        action_id = controller.run_action(args.action, runtime_flags=runtime_flags or None)
        print(f"Action completed: {action_id}")
        return 0
    except LLMRateLimitError as exc:
        msg = str(exc)
        retry_after = exc.retry_after if exc.retry_after is not None else _extract_retry_seconds(msg)
        print("[ERROR] Gemini quota/rate limit exceeded.", file=sys.stderr)
        if retry_after is not None:
            print(f"[HINT] Retry after about {retry_after:.1f} seconds.", file=sys.stderr)
        print("[HINT] Check Gemini billing/quota, or run local provider: .\\run_clipai.bat --provider olama", file=sys.stderr)
        return 2
    except LLMError as exc:
        print(f"[ERROR] LLM error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
