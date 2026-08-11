"""The swappable model layer.

One env var moves every agent between Gemini, Groq and Hunyuan. That is not a
hedge against a signup problem — a bank will demand model sovereignty, so the
abstraction is the right architecture regardless.

Every call returns its own token counts, latency and ringgit cost, which is what
makes the live cost-per-case panel real rather than decorative.
"""

from __future__ import annotations

import abc
import json
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from pydantic import BaseModel

from api.config import Settings, get_settings
from api.llm.pricing import cost_myr, is_metered


class LLMError(RuntimeError):
    """Raised when a provider call fails after its retry."""


@dataclass(slots=True)
class LLMResult:
    """One model call, with everything the telemetry table needs."""

    text: str
    provider: str
    model: str
    agent: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    cost_rm: float = 0.0
    metered: bool = True
    #: Populated when a schema was requested.
    data: dict[str, Any] | None = None
    parsed: BaseModel | None = None
    raw: Any = field(default=None, repr=False)

    @property
    def tokens_total(self) -> int:
        return self.tokens_in + self.tokens_out

    def require_data(self) -> dict[str, Any]:
        """Structured accessor for agents that cannot proceed without a schema hit."""
        if self.data is None:
            raise LLMError(
                f"{self.agent}: expected structured output from {self.model} "
                f"but the response did not parse. Raw text: {self.text[:400]!r}"
            )
        return self.data


#: (bytes, mime_type) — e.g. (pdf_page_png, "image/png")
ImagePart = tuple[bytes, str]


class LLMProvider(abc.ABC):
    """Contract every provider satisfies."""

    name: str = "base"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    @abc.abstractmethod
    def default_model(self) -> str: ...

    @abc.abstractmethod
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
        """Return (text, tokens_in, tokens_out, raw_response)."""

    @property
    def supports_vision(self) -> bool:
        return False

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        schema: type[BaseModel] | None = None,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        model: str | None = None,
        images: Sequence[ImagePart] | None = None,
        agent: str = "unknown",
        retries: int = 1,
    ) -> LLMResult:
        """Run a completion, with timing, cost and one retry on transient failure."""
        if images and not self.supports_vision:
            raise LLMError(
                f"{self.name} cannot accept images. Route OCR to the Gemini provider."
            )

        chosen = model or self.default_model
        last_error: Exception | None = None

        for attempt in range(retries + 1):
            started = time.perf_counter()
            try:
                text, tin, tout, raw = await self._complete(
                    prompt,
                    system=system,
                    schema=schema,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    model=chosen,
                    images=images,
                )
            except Exception as exc:  # noqa: BLE001 - normalised into LLMError below
                last_error = exc
                if attempt >= retries:
                    break
                continue

            latency_ms = int((time.perf_counter() - started) * 1000)
            result = LLMResult(
                text=text,
                provider=self.name,
                model=chosen,
                agent=agent,
                tokens_in=tin,
                tokens_out=tout,
                latency_ms=latency_ms,
                cost_rm=cost_myr(chosen, tin, tout),
                metered=is_metered(chosen),
                raw=raw,
            )
            if schema is not None:
                _attach_structured(result, schema)
            return result

        raise LLMError(f"{self.name}/{chosen} failed for agent {agent!r}: {last_error}") from last_error

    async def vision(
        self,
        prompt: str,
        images: Sequence[ImagePart],
        *,
        system: str | None = None,
        schema: type[BaseModel] | None = None,
        agent: str = "ocr",
        **kwargs: Any,
    ) -> LLMResult:
        """Read a scanned statement or a photographed receipt.

        Vision OCR is the primary document path, which is why there is no tesseract
        anywhere in this project.
        """
        return await self.complete(
            prompt, images=images, system=system, schema=schema, agent=agent, **kwargs
        )


def _attach_structured(result: LLMResult, schema: type[BaseModel]) -> None:
    """Parse and validate JSON output, tolerating fenced or prefixed text.

    Models occasionally wrap JSON in a code fence even when told not to. Recovering
    from that here means no agent needs its own repair logic.
    """
    text = result.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
        text = text.strip()

    if not text.startswith(("{", "[")):
        start = min(
            (i for i in (text.find("{"), text.find("[")) if i != -1),
            default=-1,
        )
        if start != -1:
            text = text[start:]

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return  # leave data=None; require_data() will raise with context

    try:
        model_instance = schema.model_validate(payload)
    except Exception:  # noqa: BLE001 - a schema miss must not crash the pipeline
        result.data = payload if isinstance(payload, dict) else {"value": payload}
        return

    result.parsed = model_instance
    result.data = model_instance.model_dump()


# ─── Registry ───────────────────────────────────────────────────────────────


def get_provider(name: str | None = None, settings: Settings | None = None) -> LLMProvider:
    """Resolve a provider by name, defaulting to whatever .env selected."""
    cfg = settings or get_settings()
    key = (name or cfg.active_provider).lower()

    if key in ("gemini", "google"):
        from api.llm.gemini import GeminiProvider

        return GeminiProvider(cfg)
    if key == "groq":
        from api.llm.groq_provider import GroqProvider

        return GroqProvider(cfg)
    if key in ("hunyuan", "tencent"):
        from api.llm.hunyuan_stub import HunyuanProvider

        return HunyuanProvider(cfg)

    raise LLMError(f"Unknown LLM_PROVIDER {key!r}. Expected gemini, groq or hunyuan.")


def get_router(settings: Settings | None = None) -> "ModelRouter":
    return ModelRouter(settings or get_settings())


class ModelRouter:
    """Deliberate per-agent model routing (MASTERPLAN §8.1).

    Reasoning and vision go to Gemini; bulk throughput goes to Groq; ticker
    summaries go to the cheapest fast model. Routing is a design decision worth
    stating on stage, so it lives in one readable place.
    """

    #: agent -> (provider, model attribute on Settings)
    #:
    #: Each agent is a different job, so each gets the model that job needs
    #: rather than one model doing everything. Reading a scanned statement and
    #: reasoning about a complaint are Gemini work. Drafting a letter is bounded
    #: by a deterministic lint immediately afterwards, so it runs on Groq's Llama
    #: for latency and cost.
    #:
    #: `verifier` and `resolver` are deliberately absent. They make no model call
    #: at all — the verifier compares MCP evidence and the resolver asks the
    #: kernel gate — and an entry here would advertise a brain that never runs.
    ROUTES: dict[str, tuple[str, str]] = {
        "intake": ("gemini", "gemini_model"),
        "ocr": ("gemini", "gemini_model"),
        "classifier": ("gemini", "gemini_model"),
        "communicator": ("groq", "groq_model"),
        "composer": ("gemini", "gemini_model"),
        "intel": ("gemini", "gemini_model"),
        "batch": ("groq", "groq_model"),
        "ticker": ("groq", "groq_model_fast"),
    }

    #: provider -> the Settings attribute holding its credential.
    CREDENTIALS: dict[str, str] = {
        "gemini": "gemini_key",
        "groq": "groq_api_key",
        "hunyuan": "hunyuan_api_key",
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: dict[str, LLMProvider] = {}

    def _has_key(self, provider_name: str) -> bool:
        attr = self.CREDENTIALS.get(provider_name)
        return bool(attr and getattr(self.settings, attr, None))

    def describe(self, agent: str) -> dict[str, Any]:
        """The routing that will actually run for `agent`, and why.

        Resolved without constructing a provider, so a roster can be rendered on
        a deployment that is missing a key. `fallback_from` is set when the
        intended provider has no credential and the call will run somewhere
        else — a UI that claimed four brains while running one would be lying,
        and this is the field that stops it.
        """
        intended, model_attr = self.ROUTES.get(agent, ("gemini", "gemini_model"))
        provider_name = intended
        pinned = False
        fallback_from: str | None = None

        forced = self.settings.active_provider
        if forced not in ("gemini", "groq"):
            provider_name = forced
            model_attr = "hunyuan_model"
            pinned = True

        if not self._has_key(provider_name):
            default_name = "gemini" if self._has_key("gemini") else provider_name
            if default_name != provider_name:
                fallback_from = provider_name
                provider_name = default_name
                model_attr = "gemini_model"

        return {
            "agent": agent,
            "provider": provider_name,
            "model": getattr(self.settings, model_attr, ""),
            "intended_provider": intended,
            "pinned": pinned,
            "fallback_from": fallback_from,
        }

    def for_agent(self, agent: str) -> tuple[LLMProvider, str]:
        """(provider, model) for an agent.

        If .env pins a provider explicitly to something other than the default,
        that choice overrides routing — one var really does move everything.
        A routed provider with no credential falls back rather than failing the
        case; `describe()` reports that fallback so it is never silent.
        """
        resolved = self.describe(agent)
        provider_name = str(resolved["provider"])

        if provider_name not in self._cache:
            self._cache[provider_name] = get_provider(provider_name, self.settings)
        provider = self._cache[provider_name]
        return provider, str(resolved["model"]) or provider.default_model
