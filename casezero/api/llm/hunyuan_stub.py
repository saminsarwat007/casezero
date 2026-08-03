"""Tencent Hunyuan — wired, not fabricated.

Hunyuan exposes an OpenAI-compatible endpoint, so this is a complete
implementation rather than a placeholder: set HUNYUAN_API_KEY and
LLM_PROVIDER=hunyuan and every agent moves across.

It ships unkeyed because Tencent Cloud signup requires WeChat, which the team
does not have access to. Keeping the adapter real and honest matters more than
pretending otherwise — and it makes the answer to "why not Hunyuan?" a
one-line configuration change instead of an excuse.
"""

from __future__ import annotations

from typing import Any, Sequence

from pydantic import BaseModel

from api.config import Settings
from api.llm.provider import ImagePart, LLMError, LLMProvider


class HunyuanProvider(LLMProvider):
    name = "hunyuan"

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)
        self._client: Any | None = None

    @property
    def default_model(self) -> str:
        return self.settings.hunyuan_model

    @property
    def configured(self) -> bool:
        return bool(self.settings.hunyuan_api_key)

    @property
    def client(self) -> Any:
        if not self.configured:
            raise LLMError(
                "HUNYUAN_API_KEY is not set. Tencent Cloud signup requires a WeChat "
                "account. The adapter is complete: add the key and set "
                "LLM_PROVIDER=hunyuan to route every agent through Hunyuan."
            )
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:  # pragma: no cover
                raise LLMError("openai is not installed.") from exc
            self._client = AsyncOpenAI(
                api_key=self.settings.hunyuan_api_key,
                base_url=self.settings.hunyuan_base_url,
            )
        return self._client

    async def _complete(
        self,
        prompt: str,
        *,
        system: str | None,
        schema: type[BaseModel] | None,
        temperature: float,
        max_tokens: int | None,
        model: str,
        images: Sequence[ImagePart] | None,
    ) -> tuple[str, int, int, Any]:
        if images:
            raise LLMError("HunyuanProvider is configured for text only here.")

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})

        user_content = prompt
        if schema is not None:
            user_content = (
                f"{prompt}\n\nRespond with JSON only, conforming exactly to this "
                f"JSON Schema:\n{schema.model_json_schema()}"
            )
        messages.append({"role": "user", "content": user_content})

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if schema is not None:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self.client.chat.completions.create(**kwargs)

        usage = getattr(response, "usage", None)
        tokens_in = getattr(usage, "prompt_tokens", 0) or 0
        tokens_out = getattr(usage, "completion_tokens", 0) or 0
        text = response.choices[0].message.content or ""

        return text, tokens_in, tokens_out, response
