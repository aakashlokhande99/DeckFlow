"""OpenAI LLM provider implementation with native structured output parsing."""

from __future__ import annotations

import asyncio
from typing import Any, Optional, Type, TypeVar
import structlog
from openai import AsyncOpenAI, APITimeoutError, APIConnectionError, RateLimitError, InternalServerError
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.llm.base import LLMError, LLMProvider, LLMTimeoutError, LLMValidationError

logger = structlog.get_logger(__name__)
T = TypeVar("T", bound=BaseModel)

RETRYABLE_EXCEPTIONS = (APIConnectionError, RateLimitError, InternalServerError)


class OpenAIProvider(LLMProvider):
    """OpenAI API implementation using AsyncOpenAI."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        timeout: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = AsyncOpenAI(api_key=api_key, timeout=timeout)

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        @retry(
            retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            reraise=True,
        )
        async def _call() -> str:
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
                choice = response.choices[0]
                content = choice.message.content
                if not content:
                    raise LLMError("OpenAI returned an empty message content.")
                return content
            except APITimeoutError as exc:
                raise LLMTimeoutError(f"OpenAI request timed out after {self.timeout}s: {exc}") from exc
            except Exception as exc:
                if isinstance(exc, (LLMTimeoutError, LLMError)):
                    raise
                raise LLMError(f"OpenAI request failed: {exc}") from exc

        return await _call()

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> T:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        @retry(
            retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            reraise=True,
        )
        async def _call() -> T:
            try:
                completion = await self.client.beta.chat.completions.parse(
                    model=self.model,
                    messages=messages,
                    response_format=response_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
                parsed = completion.choices[0].message.parsed
                if parsed is None:
                    # If refusal or unable to parse
                    refusal = getattr(completion.choices[0].message, "refusal", None)
                    raise LLMValidationError(f"Model refused or returned unparseable content: {refusal}")
                return parsed
            except APITimeoutError as exc:
                raise LLMTimeoutError(f"OpenAI structured request timed out: {exc}") from exc
            except ValidationError as exc:
                raise LLMValidationError(f"Failed to validate response against schema {response_model.__name__}: {exc}") from exc
            except Exception as exc:
                if isinstance(exc, (LLMTimeoutError, LLMValidationError, LLMError)):
                    raise
                raise LLMError(f"OpenAI structured request failed: {exc}") from exc

        return await _call()
