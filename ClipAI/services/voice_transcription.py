from __future__ import annotations

import io
import os
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class OpenAITranscriptionConfig:
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str = "https://api.openai.com/v1"
    model: str = "whisper-1"
    language: str = "zh"
    timeout_sec: int = 60

    @classmethod
    def from_mapping(cls, cfg: dict[str, Any] | None) -> "OpenAITranscriptionConfig":
        raw = cfg or {}
        return cls(
            api_key_env=str(raw.get("api_key_env") or "OPENAI_API_KEY"),
            base_url=str(raw.get("base_url") or "https://api.openai.com/v1").rstrip("/"),
            model=str(raw.get("model") or "whisper-1"),
            language=str(raw.get("language") or "zh"),
            timeout_sec=int(raw.get("timeout_sec") or 60),
        )


class OpenAITranscriptionClient:
    def __init__(self, config: OpenAITranscriptionConfig) -> None:
        self._config = config

    def transcribe_webm(self, audio_bytes: bytes) -> str:
        api_key = os.getenv(self._config.api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(f"{self._config.api_key_env} is not set.")
        if not audio_bytes:
            return ""

        response = requests.post(
            f"{self._config.base_url}/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            data={
                "model": self._config.model,
                "language": self._config.language,
                "response_format": "json",
            },
            files={"file": ("speech.webm", io.BytesIO(audio_bytes), "audio/webm")},
            timeout=self._config.timeout_sec,
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload.get("text") or "").strip()
