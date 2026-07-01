from __future__ import annotations

import os
from typing import Any

import requests

from ClipAI.core.provider import (
    ProviderConfigurationError,
    ProviderRequest,
    ProviderResponseError,
)


class GeminiProvider:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self._api_key = (
            config.get("gemini_api_key")
            or config.get("api_key")
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("LLM_API_KEY")
        )
        self._base_url = str(
            config.get("gemini_base_url")
            or os.getenv("GEMINI_BASE_URL")
            or "https://generativelanguage.googleapis.com"
        ).rstrip("/")
        self._timeout_sec = float(config.get("timeout_sec") or 60)

    def complete(self, request: ProviderRequest) -> str:
        if not self._api_key:
            raise ProviderConfigurationError("missing Gemini API key")

        url = f"{self._base_url}/v1beta/models/{request.model}:generateContent"
        params = {"key": self._api_key}
        payload = self.to_payload(request)

        try:
            response = requests.post(url, params=params, json=payload, timeout=self._timeout_sec)
        except requests.exceptions.Timeout as exc:
            raise ProviderResponseError("Gemini request timed out") from exc
        except requests.exceptions.ConnectionError as exc:
            raise ProviderResponseError("Gemini connection failed") from exc
        except requests.exceptions.RequestException as exc:
            raise ProviderResponseError(f"Gemini request failed: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text.strip()
            if len(detail) > 240:
                detail = f"{detail[:239]}..."
            raise ProviderResponseError(f"Gemini HTTP {response.status_code}: {detail}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseError("Gemini returned invalid JSON") from exc

        text = self.extract_text(payload).strip()
        if not text:
            raise ProviderResponseError("Provider returned an empty response.")
        return text

    @staticmethod
    def to_payload(request: ProviderRequest) -> dict[str, Any]:
        system_text = "\n\n".join(
            str(message.get("content") or "")
            for message in request.messages
            if message.get("role") == "system"
        ).strip()
        user_text = "\n\n".join(
            str(message.get("content") or "")
            for message in request.messages
            if message.get("role") != "system"
        ).strip()

        payload: dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_text}],
                }
            ],
            "generationConfig": {"temperature": request.temperature},
        }
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}
        return payload

    @staticmethod
    def extract_text(payload: Any) -> str:
        if isinstance(payload, list):
            return "".join(GeminiProvider.extract_text(item) for item in payload)
        if not isinstance(payload, dict):
            return ""

        texts: list[str] = []
        for candidate in payload.get("candidates") or []:
            content = candidate.get("content") or {}
            for part in content.get("parts") or []:
                texts.append(str(part.get("text") or ""))
        return "".join(texts)
