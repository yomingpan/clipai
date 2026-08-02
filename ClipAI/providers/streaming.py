from __future__ import annotations

from collections.abc import AsyncIterator
import json
from typing import Any


async def iter_json_events(lines: AsyncIterator[str]) -> AsyncIterator[dict[str, Any]]:
    """Parse SSE data records and tolerate a gateway returning one JSON body."""
    async for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith(("event:", "id:", "retry:", ":")):
            continue
        data = line[5:].strip() if line.startswith("data:") else line
        if data == "[DONE]":
            return
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            yield payload
