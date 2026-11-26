"""Google Gemini LLM provider implementation with native structured output."""

from __future__ import annotations

import json
from typing import Any, Optional, Type, TypeVar
import structlog
from google import genai
from google.genai import types
from google.genai.errors import APIError, ServerError
from pydantic import BaseModel, ValidationError
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.llm.base import LLMError, LLMProvider, LLMTimeoutError, LLMValidationError

logger = structlog.get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


class GeminiProvider(LLMProvider):
    """Google Gemini API implementation using the official google-genai SDK."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.8-flash",
        max_retries: int = 5,
    ) -> None:
        self.model = model
        self.max_retries = max_retries
        self.client = genai.Client(api_key=api_key)

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """Generate unstructured text using Gemini."""
        config = types.GenerateContentConfig(
            system_instruction=system_prompt if system_prompt else None,
            temperature=temperature,
            max_output_tokens=max_tokens if max_tokens else None,
        )

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential_jitter(initial=3, max=25),
                retry=retry_if_exception_type((APIError, ServerError)),
                reraise=True,
            ):
                with attempt:
                    response = await self.client.aio.models.generate_content(
                        model=self.model,
                        contents=prompt,
                        config=config,
                    )
            text = response.text
            if not text:
                raise LLMError("Gemini returned an empty response.")
            return text
        except Exception as exc:
            if isinstance(exc, (LLMTimeoutError, LLMError)):
                raise
            raise LLMError(f"Gemini text generation failed: {exc}") from exc

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> T:
        """Generate structured output strictly validated against a Pydantic schema."""
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=response_model.model_json_schema(),
            system_instruction=system_prompt if system_prompt else None,
            temperature=temperature,
            max_output_tokens=max_tokens if max_tokens else None,
        )

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential_jitter(initial=3, max=25),
                retry=retry_if_exception_type((APIError, ServerError)),
                reraise=True,
            ):
                with attempt:
                    response = await self.client.aio.models.generate_content(
                        model=self.model,
                        contents=prompt,
                        config=config,
                    )
            text = response.text
            if not text:
                raise LLMValidationError("Gemini returned empty structured output.")

            data = json.loads(text)
            return response_model.model_validate(data)
        except json.JSONDecodeError as exc:
            raise LLMValidationError(f"Failed to parse Gemini JSON output: {exc}") from exc
        except ValidationError as exc:
            raise LLMValidationError(
                f"Failed to validate Gemini response against schema {response_model.__name__}: {exc}"
            ) from exc
        except Exception as exc:
            if isinstance(exc, (LLMTimeoutError, LLMValidationError, LLMError)):
                raise
            raise LLMError(f"Gemini structured generation failed: {exc}") from exc
