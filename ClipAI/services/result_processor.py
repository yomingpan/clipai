from __future__ import annotations

import logging

from ClipAI.core.models import ProcessedResult
from ClipAI.services.output_profiles import OutputProfileCatalog

_DEBUG_PREFIXES = ("Input:", "Role:", "Goal:", "Constraints:", "Structure:")
logger = logging.getLogger("clipai.result_processor")


class ResultProcessor:
    def __init__(self, output_profiles: OutputProfileCatalog | None = None) -> None:
        self._output_profiles = output_profiles or OutputProfileCatalog([])

    def process(self, text: str, output_profile: str = "plain_text") -> ProcessedResult:
        profile = self._output_profiles.get(output_profile)
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
        result = "\n".join(compact).strip()
        missing = [marker for marker in profile.required_markers if marker not in result]
        if missing:
            logger.warning("Output profile %s is missing markers: %s", profile.id, ", ".join(missing))
        return ProcessedResult(
            text=result,
            output_profile=profile.id,
            presentation=profile.presentation,
        )
