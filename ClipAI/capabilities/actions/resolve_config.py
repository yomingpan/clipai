from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedActionConfig:
    action_id: str
    action_name: str
    mode: str
    provider: str
    model: str
    stream: bool
    temperature: float
    output: dict[str, bool]
    template: str


def resolve_action_config(action_def: dict, mode: str, runtime_flags: dict | None = None) -> ResolvedActionConfig:
    flags = runtime_flags or {}
    return ResolvedActionConfig(
        action_id=str(flags.get("action_id") or action_def.get("id") or "action-default"),
        action_name=str(action_def.get("name") or "Unnamed Action"),
        mode=mode,
        provider=str(flags.get("provider") or action_def.get("provider") or "gemini"),
        model=str(flags.get("model") or action_def.get("model") or "gemini-1.5-flash"),
        stream=bool(flags.get("stream", action_def.get("stream", True))),
        temperature=float(flags.get("temperature", action_def.get("temperature", 0.3))),
        output={
            "popup": bool(action_def.get("output_popup", True)),
            "clipboard": bool(action_def.get("output_clipboard", False)),
            "paste": bool(action_def.get("output_paste", False)),
            "notify": bool(action_def.get("output_notify", False)),
        },
        template=str(action_def.get("template") or "{input}"),
    )
