"""Factory function to instantiate configured LLM provider."""

from __future__ import annotations

from app.core.config import settings
from app.llm.base import LLMProvider
from app.llm.gemini import GeminiProvider
from app.llm.mock import MockLLMProvider
from app.llm.openai import OpenAIProvider


def get_llm_provider(provider_name: str | None = None) -> LLMProvider:
    """Return an instance of the configured LLM provider."""
    name = (provider_name or settings.LLM_PROVIDER or "gemini").lower()

    if name == "mock":
        return MockLLMProvider()

    if name in ("gemini", "google"):
        api_key = settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else ""
        if not api_key or api_key.startswith("mock") or api_key.startswith("test-"):
            return MockLLMProvider()
        return GeminiProvider(api_key=api_key, model=settings.GEMINI_MODEL)

    if name == "openai":
        api_key = settings.OPENAI_API_KEY.get_secret_value() if settings.OPENAI_API_KEY else ""
        if not api_key or api_key.startswith("sk-test-") or api_key == "mock":
            # If no API key configured in dev/testing, fallback to MockLLMProvider
            return MockLLMProvider()
        return OpenAIProvider(api_key=api_key)

    raise ValueError(f"Unsupported LLM provider: {name}")
