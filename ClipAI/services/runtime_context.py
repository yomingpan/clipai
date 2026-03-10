from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeContext:
    mode: str
    apply_output: bool
    use_selection: bool
    stream_enabled: bool
    stream_to_stdout: bool


def build_runtime_context(
    *,
    mode: str,
    apply_output: bool,
    use_selection: bool,
    stream_enabled: bool,
    stream_to_stdout: bool,
) -> RuntimeContext:
    return RuntimeContext(
        mode=mode,
        apply_output=apply_output,
        use_selection=use_selection,
        stream_enabled=stream_enabled,
        stream_to_stdout=stream_to_stdout,
    )
