from __future__ import annotations

from ClipAI.core.models import ProcessedResult

_DEBUG_PREFIXES = ("Input:", "Role:", "Goal:", "Constraints:", "Structure:")


class ResultProcessor:
    def process(self, text: str) -> ProcessedResult:
        lines = [line.rstrip() for line in text.strip().splitlines()]
        cleaned = [line for line in lines if not line.lstrip("# -*").startswith(_DEBUG_PREFIXES)]
        compact: list[str] = []
        previous_blank = False
        for line in cleaned:
            blank = not line.strip()
            if blank and previous_blank:
                continue
            compact.append(line)
            previous_blank = blank
        return ProcessedResult(text="\n".join(compact).strip())

