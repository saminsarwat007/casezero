"""Evaluation harness regression tests over the complete v1 corpus."""

from __future__ import annotations

import asyncio

from evals.run import evaluate


def test_deterministic_full_corpus_measurement() -> None:
    result = asyncio.run(evaluate())
    assert result["n_cases"] == 200
    assert result["accuracy"] == 1.0
    assert result["urgency_accuracy"] == 1.0
    assert result["injection_caught"] == result["injection_total"] == 5
    assert result["errors"] == 0
    assert result["evaluator"] == "deterministic-language-baseline"

