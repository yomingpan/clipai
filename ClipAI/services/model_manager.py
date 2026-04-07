from __future__ import annotations

import logging
from typing import Any

from clipai.app.config import AppConfigBundle
from clipai.providers.factory import build_provider

logger = logging.getLogger("clipai.model_manager")


class ModelManager:
    def __init__(self, bundle: AppConfigBundle) -> None:
        self._bundle = bundle

    @property
    def default_model(self) -> str:
        return str(self._bundle.provider_cfg.get("default_model") or "")

    @default_model.setter
    def default_model(self, model_id: str) -> None:
        self._bundle.provider_cfg["default_model"] = str(model_id or "").strip()

    def list_models(self) -> list[str]:
        provider_cfg = dict(self._bundle.provider_cfg)
        configured_models = self._collect_configured_models()
        try:
            models = build_provider(provider_cfg).list_models()
        except Exception as exc:
            logger.warning(
                "[clipai] Failed to list models for provider=%s: %s",
                provider_cfg.get("provider", ""),
                exc,
            )
            models = []
        return self._merge_models(models, configured_models)

    def _collect_configured_models(self) -> list[str]:
        models: list[str] = []
        default_model = self.default_model
        if default_model:
            models.append(default_model)
        for action in self._bundle.actions:
            model = str(action.get("model") or "").strip()
            if model:
                models.append(model)
            variants = action.get("press_variants") or {}
            if isinstance(variants, dict):
                for variant in variants.values():
                    if isinstance(variant, dict):
                        variant_model = str(variant.get("model") or "").strip()
                        if variant_model:
                            models.append(variant_model)
        return models

    @staticmethod
    def _merge_models(primary: list[str], secondary: list[str]) -> list[str]:
        merged: list[str] = []
        for model in [*primary, *secondary]:
            normalized = str(model or "").strip()
            if normalized and normalized not in merged:
                merged.append(normalized)
        return merged
