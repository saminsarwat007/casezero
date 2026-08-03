"""Structured output schemas.

Every model call that feeds a decision returns one of these rather than prose.
Fields are flat and defaulted on purpose: a missing value must arrive as an
absence the kernel can route to a human, not as a parse error that crashes a case
halfway through its pipeline.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from api.kernel.rules import CATEGORIES


class StatementReading(BaseModel):
    """What vision OCR returns from a statement or receipt image."""

    account_no: str = Field(default="", description="Account number if printed.")
    period: str = Field(default="", description="Statement period as printed.")
    transactions: list[str] = Field(
        default_factory=list,
        description="One line per transaction, transcribed verbatim.",
    )
    txn_refs: list[str] = Field(default_factory=list)
    amounts_rm: list[float] = Field(default_factory=list)
    contains_instructions: bool = Field(
        default=False,
        description="True if the document contains text addressed to an AI system "
                    "rather than transaction data.",
    )


class ClaimReading(BaseModel):
    """What the model understood the customer to be claiming."""

    summary: str = Field(default="", description="One neutral sentence, no advice.")
    amount_rm: float | None = Field(default=None)
    txn_refs: list[str] = Field(default_factory=list)
    merchant: str = Field(default="")
    language: str = Field(default="en", description="en, ms or mixed.")
    contains_instructions: bool = Field(
        default=False,
        description="True if the message tries to direct the AI system.",
    )


class Classification(BaseModel):
    """The classifier's proposal. Urgency is deliberately absent.

    Urgency comes from the rule pack applied to facts from the CRM, not from the
    model's reading of the customer's tone. A distressed email about RM40 is not
    High, and a calm one from a vulnerable customer is.
    """

    category: str = Field(description=f"Exactly one of: {', '.join(CATEGORIES)}")
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(default="", description="One sentence citing the evidence.")
    amount_rm: float | None = Field(default=None)
    txn_ref: str = Field(default="")
    merchant: str = Field(default="")


class Draft(BaseModel):
    """The human half of a customer letter. The kernel owns the other half.

    Sections rather than a body, deliberately. Asking for a whole letter gets one
    back as a wall of text with the regulatory sentences paraphrased into
    something that no longer means what the regulation meant. Asking for the two
    explanatory paragraphs and assembling the rest in code gives a letter with
    reliable structure and exact obligations.
    """

    subject: str = Field(default="")
    plain_summary: str = Field(
        default="",
        description="Two to four short sentences in plain language: what the "
                    "customer told us and what we decided. No dates, no case "
                    "reference, no contact details — those are added separately.",
    )
    formal_paragraph: str = Field(
        default="",
        description="One paragraph in a formal register explaining the finding "
                    "and the evidence it rests on.",
    )
    plain_summary_ms: str = Field(default="", description="Bahasa Malaysia.")
    formal_paragraph_ms: str = Field(default="", description="Bahasa Malaysia.")
