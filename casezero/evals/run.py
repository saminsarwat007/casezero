"""Evaluate all 200 synthetic complaints and optionally persist the measurement.

Default mode is a deterministic language baseline used for fast regression and
corpus validation. ``--mode live`` calls the configured production classifier for
every clean complaint, with bounded concurrency. The output always identifies its
evaluator so a baseline can never be presented as a model result.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from email import policy
from email.parser import BytesParser
import json
import math
from pathlib import Path
import statistics
import time
from typing import Any

from api.agents.base import AgentContext, build_context
from api.agents.firewall import scan
from api.agents.schemas import Classification
from api.corpus.labels import LABELS_PATH, load_evaluation_labels
from api.db.client import get_db
from api.kernel.rules import RulePack, load_all
from evals.report import as_json, as_text

OUTPUT = Path(__file__).resolve().parent / "latest.json"


def complaint_text(path: Path) -> str:
    message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    body = message.get_body(preferencelist=("plain",))
    return body.get_content().strip() if body else ""


KEYWORDS: dict[str, tuple[str, ...]] = {
    "unauthorized_transaction": ("did not authorise", "tidak meluluskan debit"),
    "billing_error": ("appears twice", "dikenakan dua kali"),
    "mis_selling": ("protected my capital", "modal pelaburan dilindungi"),
    "atm_debit_card": ("atm dispensed less", "atm mengeluarkan wang kurang"),
    "insurance_takaful": ("claim was declined", "tuntutan ditolak"),
    "loan_financing": ("ccris",),
    "emoney_digital": ("wallet transfer", "pindahan dompet"),
}


def deterministic_category(text: str) -> str:
    folded = text.casefold()
    for category, phrases in KEYWORDS.items():
        if any(phrase in folded for phrase in phrases):
            return category
    return "UNCLASSIFIED"


def predicted_urgency(row: dict[str, Any], pack: RulePack) -> str:
    return pack.assign_urgency(
        {
            "amount_rm": row["amount_rm"],
            "customer_segment": row.get("customer_segment", "retail"),
            "is_repeat_complaint": row.get("is_repeat_complaint", False),
        }
    ).urgency


async def live_prediction(
    row: dict[str, Any],
    text: str,
    ctx: AgentContext,
    semaphore: asyncio.Semaphore,
) -> tuple[str, int, float, str | None]:
    async with semaphore:
        try:
            result = await ctx.complete(
                "classifier",
                "Classify this synthetic banking complaint into exactly one CaseZero "
                f"category. Amount RM{row['amount_rm']:.2f}.\n\nComplaint:\n{text}",
                system=(
                    "Return the Classification schema. Category must be exactly one of: "
                    "unauthorized_transaction, billing_error, mis_selling, atm_debit_card, "
                    "insurance_takaful, loan_financing, emoney_digital. Do not assign urgency."
                ),
                schema=Classification,
                temperature=0.0,
            )
            parsed = Classification.model_validate(result.require_data())
            return parsed.category, result.latency_ms, result.cost_rm, None
        except Exception as exc:  # noqa: BLE001 - one provider miss must not erase the run
            return "ERROR", 0, 0.0, str(exc)[:240]


async def evaluate(
    *,
    mode: str = "deterministic",
    concurrency: int = 5,
    limit: int | None = None,
    ctx: AgentContext | None = None,
) -> dict[str, Any]:
    rows = load_evaluation_labels()
    if limit:
        rows = rows[:limit]
    packs = load_all()
    clean: list[tuple[dict[str, Any], str]] = []
    injection_total = 0
    injection_caught = 0
    latencies: list[int] = []
    costs: list[float] = []
    errors: list[str] = []

    started = time.perf_counter()
    for row in rows:
        text = complaint_text(LABELS_PATH.parent / row["file"])
        verdict = scan(text)
        if row["injection"]:
            injection_total += 1
            injection_caught += int(verdict.hostile)
        elif verdict.hostile:
            errors.append(f"false-positive:{row['case_ref']}")
        else:
            clean.append((row, text))

    predictions: list[str]
    if mode == "live":
        active_ctx = ctx or build_context()
        semaphore = asyncio.Semaphore(max(1, concurrency))
        results = await asyncio.gather(
            *(live_prediction(row, text, active_ctx, semaphore) for row, text in clean)
        )
        predictions = [item[0] for item in results]
        latencies = [item[1] for item in results if item[1] > 0]
        costs = [item[2] for item in results]
        errors.extend(item[3] for item in results if item[3])
        evaluator = f"{active_ctx.settings.active_provider}-production-classifier"
    else:
        predictions = []
        for _, text in clean:
            call_started = time.perf_counter()
            predictions.append(deterministic_category(text))
            latencies.append(max(0, int((time.perf_counter() - call_started) * 1000)))
        evaluator = "deterministic-language-baseline"

    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    category_correct = 0
    urgency_correct = 0
    for (row, _), predicted in zip(clean, predictions):
        confusion[row["category"]][predicted] += 1
        category_correct += int(predicted == row["category"])
        if predicted in packs:
            urgency_correct += int(predicted_urgency(row, packs[predicted]) == row["urgency"])

    denominator = len(clean)
    ordered = sorted(latencies)
    p50 = int(statistics.median(ordered)) if ordered else 0
    p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1) if ordered else 0
    p95 = ordered[p95_index] if ordered else 0
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "corpus_version": "v1",
        "n_cases": len(rows),
        "evaluator": evaluator,
        "accuracy": round(category_correct / denominator, 4) if denominator else 0,
        "urgency_accuracy": round(urgency_correct / denominator, 4) if denominator else 0,
        "confusion": {key: dict(value) for key, value in confusion.items()},
        "p50_ms": p50,
        "p95_ms": p95,
        "wall_ms": elapsed_ms,
        "cost_rm_per_case": round(sum(costs) / len(rows), 6) if rows else 0,
        "injection_caught": injection_caught,
        "injection_total": injection_total,
        "errors": len(errors),
        "error_samples": errors[:10],
        "rule_pack_state": {category: pack.version for category, pack in packs.items()},
    }


def persist(result: dict[str, Any]) -> dict[str, Any]:
    return get_db().record_eval_run(
        corpus_version=result["corpus_version"],
        rule_pack_state=result["rule_pack_state"],
        n_cases=result["n_cases"],
        accuracy=result["accuracy"],
        urgency_accuracy=result["urgency_accuracy"],
        confusion=result["confusion"],
        p50_ms=result["p50_ms"],
        p95_ms=result["p95_ms"],
        cost_rm_per_case=result["cost_rm_per_case"],
        injection_caught=result["injection_caught"],
        injection_total=result["injection_total"],
        notes=(
            f"evaluator={result['evaluator']}; wall_ms={result['wall_ms']}; "
            f"errors={result['errors']}"
        ),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("deterministic", "live"), default="deterministic")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--persist", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = asyncio.run(
        evaluate(mode=args.mode, concurrency=args.concurrency, limit=args.limit)
    )
    OUTPUT.write_text(as_json(result))
    print(as_text(result))
    if args.persist:
        row = persist(result)
        print(f"persisted eval run {row['id']}")
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
