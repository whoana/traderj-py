"""LLM client protocol and implementations for Claude and OpenAI.

Uses httpx directly (no SDK dependencies), matching the TelegramNotifier pattern.
"""

from __future__ import annotations

import logging
import os
from typing import Protocol, runtime_checkable

import httpx

from engine.tuner.models import LLMResponse

logger = logging.getLogger(__name__)

_CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
_OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

# Cost per 1K tokens (USD) — approximations for budgeting
_CLAUDE_INPUT_COST = 0.003
_CLAUDE_OUTPUT_COST = 0.015
_OPENAI_INPUT_COST = 0.005
_OPENAI_OUTPUT_COST = 0.015


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM provider clients."""

    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> LLMResponse: ...


class ClaudeLLMClient:
    """Anthropic Claude API client via httpx."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        timeout: int = 30,
    ) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "claude"

    @property
    def model_name(self) -> str:
        return self._model

    async def start(self) -> None:
        self._client = httpx.AsyncClient(timeout=float(self._timeout))

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> LLMResponse:
        if not self._client:
            await self.start()
        assert self._client is not None

        resp = await self._client.post(
            _CLAUDE_API_URL,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self._model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()

        text = data["content"][0]["text"]
        input_tokens = data["usage"]["input_tokens"]
        output_tokens = data["usage"]["output_tokens"]
        cost = (input_tokens * _CLAUDE_INPUT_COST + output_tokens * _CLAUDE_OUTPUT_COST) / 1000

        logger.info("Claude API call: %d in / %d out tokens, $%.4f", input_tokens, output_tokens, cost)
        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            provider="claude",
            model=self._model,
        )


class OpenAILLMClient:
    """OpenAI API client via httpx."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
        timeout: int = 30,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._model = model
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    async def start(self) -> None:
        self._client = httpx.AsyncClient(timeout=float(self._timeout))

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> LLMResponse:
        if not self._client:
            await self.start()
        assert self._client is not None

        resp = await self._client.post(
            _OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()

        text = data["choices"][0]["message"]["content"]
        usage = data["usage"]
        input_tokens = usage["prompt_tokens"]
        output_tokens = usage["completion_tokens"]
        cost = (input_tokens * _OPENAI_INPUT_COST + output_tokens * _OPENAI_OUTPUT_COST) / 1000

        logger.info("OpenAI API call: %d in / %d out tokens, $%.4f", input_tokens, output_tokens, cost)
        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            provider="openai",
            model=self._model,
        )
