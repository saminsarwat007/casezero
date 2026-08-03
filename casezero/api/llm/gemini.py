"""Gemini 2.5 Flash — the primary provider.

Chosen for two capabilities the pipeline depends on:

* **Native vision**, which lets a scanned or photographed bank statement be read
  directly. This removes tesseract, the flakiest system dependency in the original
  plan, along with its entire class of installation failures.
* **Schema-native structured output**, so a classification comes back conforming to
  a Pydantic model instead of arriving as prose that needs a JSON-repair loop.
"""

from __future__ import annotations

from typing import Any, Sequence

from pydantic import BaseModel

from api.config import Settings
from api.llm.provider import ImagePart, LLMError, LLMProvider


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)
        if not self.settings.gemini_key:
            raise LLMError(
                "GOOGLE_API_KEY (or GEMINI_API_KEY) is not set. "
                "Get one free at https://aistudio.google.com/apikey"
            )
        self._client: Any | None = None

    @property
    def default_model(self) -> str:
        return self.settings.gemini_model

    @property
    def supports_vision(self) -> bool:
        return True

    @property
    def client(self) -> Any:
        """Lazily constructed so importing this module never requires the SDK."""
        if self._client is None:
            try:
                from google import genai
            except ImportError as exc:  # pragma: no cover
                raise LLMError(
                    "google-genai is not installed. Run: pip install -r api/requirements.txt"
                ) from exc
            self._client = genai.Client(api_key=self.settings.gemini_key)
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
        from google.genai import types

        parts: list[Any] = []
        # Images first: the model attends better when the document precedes the
        # instruction about what to extract from it.
        for data, mime_type in images or ():
            parts.append(types.Part.from_bytes(data=data, mime_type=mime_type))
        parts.append(types.Part.from_text(text=prompt))

        config_kwargs: dict[str, Any] = {"temperature": temperature}
        if system:
            config_kwargs["system_instruction"] = system
        if max_tokens:
            config_kwargs["max_output_tokens"] = max_tokens
        if schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = schema

        response = await self.client.aio.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(**config_kwargs),
        )

        usage = getattr(response, "usage_metadata", None)
        tokens_in = getattr(usage, "prompt_token_count", 0) or 0
        tokens_out = getattr(usage, "candidates_token_count", 0) or 0

        text = response.text or ""
        if not text and schema is not None:
            # Some SDK versions surface a parsed object without a text payload.
            parsed = getattr(response, "parsed", None)
            if parsed is not None:
                text = (
                    parsed.model_dump_json()
                    if isinstance(parsed, BaseModel)
                    else str(parsed)
                )

        return text, tokens_in, tokens_out, response
