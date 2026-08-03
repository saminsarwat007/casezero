"""Stable human and JSON rendering for evaluation results."""

from __future__ import annotations

import json
from typing import Any, Mapping


def as_json(result: Mapping[str, Any]) -> str:
    return json.dumps(dict(result), indent=2, sort_keys=True, default=str) + "\n"


def as_text(result: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "CaseZero evaluation",
            "=" * 68,
            f"corpus              {result['corpus_version']} / {result['n_cases']} cases",
            f"evaluator           {result['evaluator']}",
            f"classification      {result['accuracy']:.2%}",
            f"urgency             {result['urgency_accuracy']:.2%}",
            f"injection firewall  {result['injection_caught']}/{result['injection_total']}",
            f"latency             p50 {result['p50_ms']} ms / p95 {result['p95_ms']} ms",
            f"cost                RM {result['cost_rm_per_case']:.6f} per case",
            f"errors              {result['errors']}",
            "=" * 68,
        ]
    )

