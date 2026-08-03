"""Groq — throughput.

Used for Batch Storm, where fifty disputes are processed at once and the tokens
per second *is* the visual, and for the Agent Theater ticker where sub-100ms
summaries are effectively free.

Named groq_provider rather than groq so it can never shadow the installed SDK.
Text only: any document that needs reading goes to the Gemini vision path.
"""

from __future__ import annotations

from typing import Any, Sequence

from pydantic import BaseModel

from api.config import Settings
from api.llm.provider import ImagePart, LLMError, LLMProvider


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)
        if not self.settings.groq_api_key:
            raise LLMError(
                "GROQ_API_KEY is not set. Get one free at https://console.groq.com/keys"
            )
        self._client: Any | None = None

    @property
    def default_model(self) -> str:
        return self.settings.groq_model

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                from groq import AsyncGroq
            except ImportError as exc:  # pragma: no cover
                raise LLMError(
                    "groq is not installed. Run: pip install -r api/requirements.txt"
                ) from exc
            self._client = AsyncGroq(api_key=self.settings.groq_api_key)
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
            raise LLMError("GroqProvider is text-only; route OCR to Gemini.")

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})

        user_content = prompt
        if schema is not None:
            # Groq has no response_schema, so the shape is supplied in-prompt and
            # validated on our side. json_object mode still guarantees valid JSON.
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
