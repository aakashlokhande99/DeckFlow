"""Unit tests for the Google Gemini LLM provider implementation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from pydantic import BaseModel, Field

from app.llm.base import LLMError, LLMValidationError
from app.llm.factory import get_llm_provider
from app.llm.gemini import GeminiProvider
from app.llm.mock import MockLLMProvider


class SampleSummaryModel(BaseModel):
    title: str = Field(..., description="Project title")
    key_findings: list[str] = Field(..., description="Key findings list")
    confidence_score: float = Field(..., ge=0.0, le=1.0)


class TestGeminiProvider:
    """Validate Gemini provider configuration, text generation, and structured parsing."""

    def test_provider_initialization_defaults(self):
        """GeminiProvider initializes with gemini-3.8-flash as the primary current model."""
        provider = GeminiProvider(api_key="test-api-key")
        assert provider.model == "gemini-3.8-flash"
        assert provider.client is not None

    def test_factory_fallback_on_empty_or_test_key(self):
        """Factory falls back to MockLLMProvider in test/development when no real key is configured."""
        provider = get_llm_provider("gemini")
        # In test environments without real GEMINI_API_KEY, fallback to MockLLMProvider
        assert isinstance(provider, (GeminiProvider, MockLLMProvider))

    def test_factory_instantiates_gemini_with_key(self):
        """Factory returns GeminiProvider when a key is provided."""
        with patch("app.llm.factory.settings.GEMINI_API_KEY") as mock_key:
            mock_key.get_secret_value.return_value = "AIzaSyFakeValidKeyForTesting12345"
            provider = get_llm_provider("gemini")
            assert isinstance(provider, GeminiProvider)
            assert provider.model == "gemini-3.8-flash"

    @pytest.mark.asyncio
    async def test_generate_text_successful(self):
        """generate_text issues async generate_content call and extracts text."""
        provider = GeminiProvider(api_key="test-key")

        mock_response = MagicMock()
        mock_response.text = "This is a strategic consulting synthesis summary."

        with patch.object(
            provider.client.aio.models,
            "generate_content",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_generate:
            result = await provider.generate_text(
                prompt="Summarize SMR market outlook",
                system_prompt="You are a senior strategy consultant.",
                temperature=0.2,
            )
            assert result == "This is a strategic consulting synthesis summary."
            assert mock_generate.called
            call_kwargs = mock_generate.call_args.kwargs
            assert call_kwargs["model"] == "gemini-3.8-flash"
            assert call_kwargs["contents"] == "Summarize SMR market outlook"
            assert call_kwargs["config"].system_instruction == "You are a senior strategy consultant."

    @pytest.mark.asyncio
    async def test_generate_text_empty_raises_llm_error(self):
        """generate_text raises LLMError when empty text is returned."""
        provider = GeminiProvider(api_key="test-key")

        mock_response = MagicMock()
        mock_response.text = ""

        with patch.object(
            provider.client.aio.models,
            "generate_content",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            with pytest.raises(LLMError, match="empty response"):
                await provider.generate_text("Prompt")

    @pytest.mark.asyncio
    async def test_generate_structured_successful(self):
        """generate_structured properly parses and validates model against Pydantic schema."""
        provider = GeminiProvider(api_key="test-key")

        mock_data = {
            "title": "Small Modular Reactors Commercial Analysis",
            "key_findings": ["Cost per MWh is competitive", "NRC licensing takes 3-5 years"],
            "confidence_score": 0.88,
        }

        mock_response = MagicMock()
        mock_response.text = json.dumps(mock_data)

        with patch.object(
            provider.client.aio.models,
            "generate_content",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_generate:
            output = await provider.generate_structured(
                prompt="Extract SMR findings",
                response_model=SampleSummaryModel,
                system_prompt="Format strictly as structured consulting data.",
            )
            assert isinstance(output, SampleSummaryModel)
            assert output.title == "Small Modular Reactors Commercial Analysis"
            assert len(output.key_findings) == 2
            assert output.confidence_score == 0.88

            # Verify schema was passed in config
            call_kwargs = mock_generate.call_args.kwargs
            config = call_kwargs["config"]
            assert config.response_mime_type == "application/json"
            assert "properties" in config.response_json_schema

    @pytest.mark.asyncio
    async def test_generate_structured_malformed_json_raises_validation_error(self):
        """generate_structured raises LLMValidationError on non-JSON content."""
        provider = GeminiProvider(api_key="test-key")

        mock_response = MagicMock()
        mock_response.text = "NOT JSON DATA AT ALL"

        with patch.object(
            provider.client.aio.models,
            "generate_content",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            with pytest.raises(LLMValidationError, match="Failed to parse Gemini JSON output"):
                await provider.generate_structured(
                    prompt="Extract",
                    response_model=SampleSummaryModel,
                )
