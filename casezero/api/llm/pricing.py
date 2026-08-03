"""Token pricing, in Malaysian ringgit.

The dashboard shows a live cost-per-case figure. That number is only worth putting
on screen if it is computed from real token counts against real published rates,
so the rates live here in one auditable table rather than being sprinkled through
the agents.

Rates are USD per 1M tokens from each vendor's public pricing, converted at a
single fixed rate so the demo figure is stable and reproducible.
"""

from __future__ import annotations

USD_TO_MYR = 4.70

#: model -> (usd_per_1m_input, usd_per_1m_output)
_USD_PER_1M: dict[str, tuple[float, float]] = {
    # Google Gemini
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.0-flash": (0.10, 0.40),
    # Groq
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
    # Tencent Hunyuan (stub path)
    "hunyuan-turbos-latest": (0.11, 0.28),
}

#: Charged when a model is not in the table. Deliberately non-zero: an unknown
#: model must never make a case look free.
_FALLBACK_USD_PER_1M = (0.50, 1.50)


def rate_myr_per_1m(model: str) -> tuple[float, float]:
    """(input, output) ringgit per 1M tokens."""
    usd_in, usd_out = _USD_PER_1M.get(model, _FALLBACK_USD_PER_1M)
    return usd_in * USD_TO_MYR, usd_out * USD_TO_MYR


def cost_myr(model: str, tokens_in: int, tokens_out: int) -> float:
    """Cost of a single call in ringgit."""
    myr_in, myr_out = rate_myr_per_1m(model)
    return (tokens_in / 1_000_000) * myr_in + (tokens_out / 1_000_000) * myr_out


def is_metered(model: str) -> bool:
    """False when we are guessing the rate — surfaced in the UI so the cost
    figure is never presented as more precise than it is."""
    return model in _USD_PER_1M
