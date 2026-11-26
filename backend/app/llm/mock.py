"""Mock LLM provider for deterministic offline testing and CI."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Optional, Type, TypeVar
from pydantic import BaseModel

from app.llm.base import LLMError, LLMProvider, LLMTimeoutError, LLMValidationError

T = TypeVar("T", bound=BaseModel)


class MockLLMProvider(LLMProvider):
    """Deterministic mock LLM provider with error simulation capabilities."""

    def __init__(
        self,
        default_text: str = "Mock generated text response.",
        structured_responses: Optional[Dict[str, BaseModel]] = None,
        simulate_timeout: bool = False,
        simulate_validation_error: bool = False,
        call_delay_seconds: float = 0.0,
    ) -> None:
        self.default_text = default_text
        self.structured_responses = structured_responses or {}
        self.simulate_timeout = simulate_timeout
        self.simulate_validation_error = simulate_validation_error
        self.call_delay_seconds = call_delay_seconds
        self.call_history: list[dict[str, Any]] = []

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        self.call_history.append({"prompt": prompt, "system_prompt": system_prompt})
        if self.call_delay_seconds > 0:
            await asyncio.sleep(self.call_delay_seconds)
        if self.simulate_timeout:
            raise LLMTimeoutError("Simulated mock timeout error")
        return self.default_text

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> T:
        self.call_history.append({
            "prompt": prompt,
            "response_model": response_model.__name__,
            "system_prompt": system_prompt,
        })
        if self.call_delay_seconds > 0:
            await asyncio.sleep(self.call_delay_seconds)
        if self.simulate_timeout:
            raise LLMTimeoutError("Simulated mock timeout error")
        if self.simulate_validation_error:
            raise LLMValidationError(f"Simulated validation error for {response_model.__name__}")

        model_name = response_model.__name__
        if model_name in self.structured_responses:
            res = self.structured_responses[model_name]
            if isinstance(res, response_model):
                return res

        # Try to construct default instance or minimal mock
        try:
            return response_model()
        except Exception:
            # If default construction requires mandatory fields, inspect schema or return from test fixture
            raise LLMValidationError(
                f"No mock response configured for {model_name} and cannot construct empty instance."
            )
