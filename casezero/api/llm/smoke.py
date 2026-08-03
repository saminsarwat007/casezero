"""Block 0 gate: both providers answering with valid structured output, and the
vision path reading a real PDF.

Run:  .venv/bin/python -m api.llm.smoke

Three things must pass before any pipeline code is worth writing:

1. **Gemini structured output** — a classification arrives conforming to a Pydantic
   model, with no JSON-repair loop.
2. **Groq structured output** — the same schema through a different provider, which
   is what makes "one env var swaps the brain" a fact rather than a claim.
3. **Gemini document vision** — a generated statement PDF is read and the disputed
   line item is located. This is the bet that let us delete tesseract, so it gets
   verified on day one rather than discovered on stage.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Literal

from pydantic import BaseModel, Field

from api.config import get_settings
from api.corpus.statement_pdf import demo_statement, demo_statement_pdf
from api.llm.provider import LLMError, LLMResult, ModelRouter, get_provider

DISPUTE_EMAIL = """\
Subject: Unauthorised transaction on my account - urgent

Dear MYBank,

Saya nak report satu transaction yang saya tak buat. On 18 July 2026 there was a
charge of RM2,450.00 to TECHWORLD KL at 3:02 in the morning. I was asleep at home
and my card never left my wallet. Tolong reverse it.

My account is 7142556890. Attached is my July statement.

Ahmad bin Ismail
"""


class Classification(BaseModel):
    """The classifier contract. Mirrors the spec's own vocabulary."""

    category: Literal[
        "unauthorized_transaction",
        "billing_error",
        "mis_selling",
        "atm_debit_card",
        "insurance_takaful",
        "loan_financing",
        "emoney_digital",
    ]
    urgency: Literal["High", "Medium", "Low"]
    confidence: float = Field(ge=0.0, le=1.0)
    amount_rm: float | None = None
    account_no: str | None = None
    reasoning: str


class StatementLineOut(BaseModel):
    """One transcribed row. No interpretation, no judgment."""

    date: str
    description: str
    amount_rm: float
    is_credit: bool = False


class StatementExtract(BaseModel):
    """The OCR agent's contract: transcribe, do not adjudicate.

    Deciding which line is *suspicious* is the kernel's job, measured against the
    amount the customer actually claimed. Asking the model to make that call would
    hand judgment to the layer we deliberately keep judgment away from.
    """

    account_no: str
    statement_period: str
    opening_balance_rm: float | None = None
    closing_balance_rm: float | None = None
    lines: list[StatementLineOut] = Field(default_factory=list)


SYSTEM = (
    "You are a Malaysian retail banking dispute classifier for MYBank Berhad. "
    "Customers write in English, Bahasa Malaysia, or a mix of both. "
    "Assign High urgency to unauthorised transactions at or above RM5,000 and to "
    "vulnerable customers; Medium at or above RM500; otherwise Low. "
    "Report genuine confidence — a low score routes the case to a human, which is "
    "the correct outcome when the text is ambiguous."
)

PASS = "\033[32m PASS \033[0m"
FAIL = "\033[31m FAIL \033[0m"
DIM = "\033[2m"
OFF = "\033[0m"


def report(label: str, result: LLMResult) -> None:
    print(
        f"  {DIM}{result.provider}/{result.model}{OFF}  "
        f"{result.latency_ms} ms  "
        f"{result.tokens_in}+{result.tokens_out} tok  "
        f"RM {result.cost_rm:.6f}"
        + ("" if result.metered else f"  {DIM}(rate estimated){OFF}")
    )


async def test_gemini_structured() -> tuple[bool, float]:
    print("\n[1/3] Gemini structured classification")
    try:
        provider = get_provider("gemini")
        result = await provider.complete(
            DISPUTE_EMAIL,
            system=SYSTEM,
            schema=Classification,
            agent="classifier",
        )
        data = result.require_data()
        report("gemini", result)
        print(
            f"        category={data['category']}  urgency={data['urgency']}  "
            f"confidence={data['confidence']}  amount={data.get('amount_rm')}"
        )

        ok = data["category"] == "unauthorized_transaction"
        if not ok:
            print(f"  {FAIL} expected unauthorized_transaction, got {data['category']}")
            return False, result.cost_rm

        # RM2,450 is under the RM5,000 High threshold, so Medium is the correct
        # answer. Getting this right means the model read the rule, not the vibe.
        if data["urgency"] != "Medium":
            print(
                f"  {DIM}note: urgency={data['urgency']}; the rule pack says Medium "
                f"for RM2,450. The kernel overrides this deterministically.{OFF}"
            )

        print(f"  {PASS} structured output validated against the Pydantic schema")
        return True, result.cost_rm
    except LLMError as exc:
        print(f"  {FAIL} {exc}")
        return False, 0.0


async def test_groq_structured() -> tuple[bool, float]:
    print("\n[2/3] Groq structured classification (the provider swap)")
    try:
        provider = get_provider("groq")
        result = await provider.complete(
            DISPUTE_EMAIL,
            system=SYSTEM,
            schema=Classification,
            agent="batch",
        )
        data = result.require_data()
        report("groq", result)
        print(
            f"        category={data['category']}  urgency={data['urgency']}  "
            f"confidence={data['confidence']}"
        )
        if data["category"] != "unauthorized_transaction":
            print(f"  {FAIL} expected unauthorized_transaction, got {data['category']}")
            return False, result.cost_rm
        print(f"  {PASS} same schema, different provider, no code change")
        return True, result.cost_rm
    except LLMError as exc:
        print(f"  {FAIL} {exc}")
        return False, 0.0


async def test_gemini_vision() -> tuple[bool, float]:
    print("\n[3/3] Gemini document vision on a generated statement PDF")
    print(f"  {DIM}this is the bet that let us delete tesseract{OFF}")
    try:
        pdf_bytes = demo_statement_pdf()
        print(f"  {DIM}generated {len(pdf_bytes):,} byte statement{OFF}")

        provider = get_provider("gemini")
        result = await provider.vision(
            "Transcribe this bank statement exactly as printed. Return the account "
            "number, the statement period, the opening and closing balances, and "
            "every transaction row in order. Copy each amount and description "
            "verbatim from the document. Do not interpret, summarise, or omit rows, "
            "and do not judge whether any transaction is unusual.",
            images=[(pdf_bytes, "application/pdf")],
            schema=StatementExtract,
            agent="ocr",
        )
        data = result.require_data()
        report("gemini", result)

        spec = demo_statement()
        lines = data.get("lines", [])
        print(f"        account_no={data['account_no']}  period={data['statement_period']}")
        print(f"        transcribed {len(lines)}/{len(spec.lines)} rows")

        disputed = [l for l in lines if abs(l["amount_rm"] - 2450.00) < 0.01]
        for line in disputed:
            print(f"        RM2,450 row: {line['date']}  {line['description']}")

        printed_amounts = sorted(round(l.amount_rm, 2) for l in spec.lines)
        read_amounts = sorted(round(float(l["amount_rm"]), 2) for l in lines)

        checks: list[tuple[str, bool]] = [
            ("account number read correctly",
             spec.account_no in str(data["account_no"]).replace(" ", "")),
            ("every row transcribed", len(lines) == len(spec.lines)),
            ("every amount matches the printed figure", printed_amounts == read_amounts),
            ("the RM2,450.00 TECHWORLD line is present",
             any("TECHWORLD" in l["description"].upper() for l in disputed)),
            ("closing balance matches",
             data.get("closing_balance_rm") is not None
             and abs(float(data["closing_balance_rm"]) - spec.closing_balance_rm) < 0.01),
        ]
        for label, passed in checks:
            print(f"        {'ok  ' if passed else 'MISS'} {label}")

        if all(passed for _, passed in checks):
            print(f"  {PASS} vision OCR is exact — no tesseract, no system binaries")
            return True, result.cost_rm
        print(f"  {FAIL} transcription was not faithful")
        return False, result.cost_rm
    except LLMError as exc:
        print(f"  {FAIL} {exc}")
        return False, 0.0


def show_routing() -> None:
    settings = get_settings()
    router = ModelRouter(settings)
    print(f"\n{DIM}Per-agent model routing (MASTERPLAN 8.1){OFF}")
    for agent in ("classifier", "ocr", "communicator", "composer", "batch", "ticker"):
        provider_name, model_attr = router.ROUTES[agent]
        print(f"  {agent:<14} -> {provider_name}/{getattr(settings, model_attr)}")


async def main() -> int:
    settings = get_settings()
    print("=" * 68)
    print("  CaseZero - Block 0 gate")
    print("=" * 68)
    print(f"  LLM_PROVIDER      {settings.active_provider}")
    print(f"  Gemini key        {'set' if settings.gemini_key else 'MISSING'}")
    print(f"  Groq key          {'set' if settings.groq_api_key else 'MISSING'}")
    print(f"  Supabase URL      {'set' if settings.supabase_url else 'MISSING'}")
    print(f"  Fernet key        {'set' if settings.fernet_key else 'MISSING'}")
    print(f"  Confidence floor  {settings.classifier_confidence_floor}")

    results = [
        await test_gemini_structured(),
        await test_groq_structured(),
        await test_gemini_vision(),
    ]
    show_routing()

    passed = sum(1 for ok, _ in results if ok)
    total_cost = sum(cost for _, cost in results)

    print("\n" + "=" * 68)
    print(f"  {passed}/3 passed   total cost RM {total_cost:.6f}")
    if passed == 3:
        print("  GATE OPEN - the vertical slice can be built on this.")
    else:
        print("  GATE CLOSED - fix the above before writing pipeline code.")
    print("=" * 68)
    return 0 if passed == 3 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
