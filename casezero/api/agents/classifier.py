"""Agent 2 — Classifier. Proposes a category; the rule pack decides everything else.

The division of labour here is the argument of the whole project in miniature.

* The **model** reads the complaint and proposes a category with a confidence. It
  is good at this and nothing downstream trusts it further than that.
* The **rule pack** assigns urgency, deterministically, from facts fetched out of
  the CRM — not from the customer's tone. A furious email about RM40 is not High,
  and a polite one from an assisted-banking customer is.
* The **kernel** turns urgency into a deadline in Malaysian working days.

Two failure modes are handled explicitly rather than absorbed:

* A model that is unavailable or returns an unusable category falls back to a
  keyword classifier whose confidence is *capped below every pack's floor*. The
  case is still routed and still tracked, but it can only reach a human.
* CRM facts that cannot be fetched escalate urgency to the tightest SLA instead
  of quietly falling through to the category default — an unknown customer might
  be a vulnerable one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from api.agents import firewall
from api.agents.base import KERNEL, Event, agent_actor
from api.agents.intake import IntakeResult
from api.agents.schemas import Classification
from api.kernel.rules import CATEGORIES, RulePack, UrgencyDecision
from api.kernel.sla import SlaWindow, compute_sla

ACTOR = agent_actor("classifier")

#: The ceiling on a fallback classification. Every shipped pack's floor is 0.75 or
#: higher, so a keyword guess can never clear one. That is the point: the fallback
#: keeps the case moving to a human, it does not stand in for the model.
FALLBACK_CONFIDENCE = 0.30

#: Keyword evidence per category, used only when the model is unavailable.
KEYWORDS: dict[str, tuple[str, ...]] = {
    "unauthorized_transaction": (
        "unauthorised", "unauthorized", "did not make", "didn't make", "not mine",
        "never made", "fraud", "fraudulent", "stolen", "hacked", "someone else",
        "tidak dibenarkan", "bukan saya", "penipuan",
    ),
    "billing_error": (
        "charged twice", "double charge", "duplicate", "billing", "overcharge",
        "over charged", "wrong amount", "incorrect amount", "service fee",
        "maintenance fee", "caj", "salah caj", "dua kali",
    ),
    "mis_selling": (
        "mis-sold", "missold", "mis sold", "misled", "misrepresent", "was told",
        "promised", "guaranteed return", "unit trust", "investment product",
        "did not explain", "salah jual", "tidak dijelaskan",
    ),
    "atm_debit_card": (
        "atm", "cash machine", "dispensed", "did not dispense", "debit card",
        "card retained", "swallowed my card", "mesin atm", "wang tidak keluar",
    ),
    "insurance_takaful": (
        "insurance", "takaful", "policy", "premium", "claim was rejected",
        "claim rejected", "coverage", "insurans", "polisi", "tuntutan",
    ),
    "loan_financing": (
        "loan", "financing", "ccris", "instalment", "installment", "interest rate",
        "profit rate", "early settlement", "pinjaman", "pembiayaan", "ansuran",
    ),
    "emoney_digital": (
        "e-wallet", "ewallet", "duitnow", "touch 'n go", "touch n go", "tng",
        "grabpay", "boost", "shopeepay", "qr code", "dompet digital",
    ),
}

CLASSIFIER_SYSTEM = (
    firewall.CONTAINMENT_PREAMBLE
    + " You are a dispute classifier for a Malaysian bank. Choose exactly one "
    "category from the list. Report a calibrated confidence: below 0.75 means a "
    "human will review the case, which is the correct outcome when the message is "
    "ambiguous, mentions several products, or gives too little detail. Do not "
    "assign urgency or priority — that is not your decision."
)

CATEGORY_GUIDE = """
unauthorized_transaction — a debit the customer says they did not authorise.
billing_error            — a fee, charge or amount the bank applied incorrectly.
mis_selling              — a product sold on a misleading or incomplete basis.
atm_debit_card           — ATM or debit card failures: cash not dispensed, card retained.
insurance_takaful        — insurance or takaful policies, premiums, declined claims.
loan_financing           — loans and financing: instalments, rates, CCRIS records.
emoney_digital           — e-wallets, DuitNow, QR payments, digital transfers.
""".strip()


@dataclass
class ClassifierResult:
    """A category, an urgency, a deadline, and the reasons for all three."""

    category: str
    confidence: float
    urgency: str
    sla: SlaWindow
    pack: RulePack
    urgency_decision: UrgencyDecision
    facts: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""
    source: str = "model"  # model | keyword_fallback
    below_floor: bool = False
    events: list[Event] = field(default_factory=list)

    @property
    def needs_human(self) -> bool:
        return self.below_floor

    def governance_stamp(self) -> dict[str, Any]:
        """The provenance block the Case Detail 'Why?' panel renders.

        Every number on this stamp names where it came from, because a decision a
        regulator cannot trace to a written rule is not defensible.
        """
        return {
            "category": self.category,
            "confidence": round(float(self.confidence), 3),
            "confidence_floor": self.pack.confidence_floor,
            "confidence_source": self.source,
            "below_floor": self.below_floor,
            "urgency": self.urgency,
            "urgency_because": self.urgency_decision.because,
            "urgency_rule_index": self.urgency_decision.rule_index,
            "sla_working_days": self.sla.working_days,
            "sla_due": self.sla.due.isoformat(),
            "sla_due_display": self.sla.due_date_display,
            "rule_pack": f"{self.pack.category} v{self.pack.version}",
            "citations": [
                f"{self.pack.category}.urgency_rules[{self.urgency_decision.rule_index}]",
                f"{self.pack.category}.sla.{self.urgency}.working_days = "
                f"{self.sla.working_days}",
                f"{self.pack.category}.verification.confidence_floor = "
                f"{self.pack.confidence_floor}",
            ],
        }

    def case_fields(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "urgency": self.urgency,
            "confidence": round(float(self.confidence), 3),
            "rule_pack_version": self.pack.version,
            "sla_start": self.sla.start.isoformat(),
            "sla_due": self.sla.due.isoformat(),
            "sla_working_days": self.sla.working_days,
        }


# ─── Category ───────────────────────────────────────────────────────────────


def keyword_scores(text: str) -> dict[str, int]:
    lowered = text.lower()
    return {
        category: sum(len(re.findall(re.escape(word), lowered)) for word in words)
        for category, words in KEYWORDS.items()
    }


def classify_by_keyword(text: str) -> tuple[str, str]:
    """(category, why). The floor keeps this from ever auto-resolving anything."""
    scores = keyword_scores(text)
    best = max(scores, key=lambda c: scores[c])
    if scores[best] == 0:
        return (
            "unauthorized_transaction",
            "No category keywords matched; routed to the highest-volume category "
            "for triage only.",
        )
    hits = [word for word in KEYWORDS[best] if word in text.lower()]
    return best, f"Keyword evidence: {', '.join(hits[:4])}."


async def propose_category(text: str, ctx: Any) -> tuple[str, float, str, str]:
    """(category, confidence, reasoning, source)."""
    try:
        result = await ctx.complete(
            "classifier",
            f"Categories:\n{CATEGORY_GUIDE}\n\n"
            "Classify this customer message.\n\n" + firewall.wrap_untrusted(text),
            system=CLASSIFIER_SYSTEM,
            schema=Classification,
        )
    except Exception as exc:  # noqa: BLE001 - a model outage degrades, never crashes
        ctx.note_degraded(f"classifier model unavailable: {exc}")
        category, why = classify_by_keyword(text)
        return category, FALLBACK_CONFIDENCE, why, "keyword_fallback"

    data = result.data or {}
    category = str(data.get("category") or "").strip().lower()
    if category not in CATEGORIES:
        # An unusable answer is worse than no answer, because it looks like one.
        ctx.note_degraded(f"classifier returned unknown category {category!r}")
        fallback, why = classify_by_keyword(text)
        return (
            fallback,
            FALLBACK_CONFIDENCE,
            f"Model returned an unrecognised category {category!r}. {why}",
            "keyword_fallback",
        )

    confidence = float(data.get("confidence") or 0.0)
    return (
        category,
        max(0.0, min(1.0, confidence)),
        str(data.get("reasoning") or ""),
        "model",
    )


# ─── Facts ──────────────────────────────────────────────────────────────────


async def gather_facts(
    account_no: str | None,
    category: str,
    ctx: Any,
    *,
    exclude_case_id: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    """(facts, error). Facts come from the CRM, never from the model.

    `customer_segment` and `is_repeat_complaint` change the SLA by fifteen working
    days in every pack, so they are read from a system of record.
    """
    if not account_no:
        return {}, "No account number was extracted, so customer facts are unavailable."
    try:
        facts = await ctx.call_tool(
            "crm",
            "get_case_facts",
            account_no=account_no,
            category=category,
            exclude_case_id=exclude_case_id,
        )
    except Exception as exc:  # noqa: BLE001 - tool refusal is an answer, see below
        return {}, str(exc)
    return dict(facts), None


def assign_urgency(
    pack: RulePack,
    facts: dict[str, Any],
    amount_rm: float | None,
    *,
    facts_error: str | None,
) -> UrgencyDecision:
    """Urgency from the pack — or the tightest SLA when the facts are missing.

    `evaluate_condition` fails closed on an absent fact, which is right for a
    single rule and wrong for a whole missing fact set: a customer we know nothing
    about would silently land on the category default. So an unavailable CRM
    escalates rather than defaults, and says so.
    """
    if facts_error:
        return UrgencyDecision(
            urgency="High",
            because=(
                f"Customer facts could not be retrieved ({facts_error}) — urgency "
                f"escalated to High so an unknown customer is never treated as a "
                f"low-priority one."
            ),
            rule_index=None,
        )
    return pack.assign_urgency({**facts, "amount_rm": amount_rm})


# ─── The agent ──────────────────────────────────────────────────────────────


async def run(
    intake: IntakeResult,
    ctx: Any,
    *,
    received_at: datetime | None = None,
    exclude_case_id: str | None = None,
) -> ClassifierResult:
    text = "\n\n".join(
        [intake.subject, intake.body] + [a.text for a in intake.attachments if a.text]
    ).strip()

    category, confidence, reasoning, source = await propose_category(text, ctx)
    pack = ctx.pack(category)

    facts, facts_error = await gather_facts(
        intake.extracted.account_no, category, ctx, exclude_case_id=exclude_case_id
    )
    decision = assign_urgency(
        pack, facts, intake.extracted.amount_rm, facts_error=facts_error
    )

    window = compute_sla(
        received_at or intake.received_at,
        pack.sla_working_days(decision.urgency),
        ctx.holidays,
    )

    below_floor = confidence < pack.confidence_floor
    result = ClassifierResult(
        category=category,
        confidence=confidence,
        urgency=decision.urgency,
        sla=window,
        pack=pack,
        urgency_decision=decision,
        facts=facts,
        reasoning=reasoning,
        source=source,
        below_floor=below_floor,
    )

    result.events.append(
        Event(
            type="CLASSIFIED",
            actor=ACTOR,
            payload={
                "category": category,
                "confidence": round(confidence, 3),
                "reasoning": reasoning,
                "source": source,
                "keyword_scores": keyword_scores(text) if source != "model" else None,
            },
        )
    )
    result.events.append(
        Event(
            type="URGENCY_ASSIGNED",
            actor=KERNEL,  # deterministic: the pack decided this, not an agent
            payload={
                "urgency": decision.urgency,
                "because": decision.because,
                "rule_index": decision.rule_index,
                "facts": facts,
                "facts_error": facts_error,
                "sla_working_days": window.working_days,
                "sla_due": window.due.isoformat(),
                "citations": result.governance_stamp()["citations"],
            },
        )
    )
    if below_floor:
        result.events.append(
            Event(
                type="CONFIDENCE_BELOW_FLOOR",
                actor=KERNEL,
                payload={
                    "confidence": round(confidence, 3),
                    "floor": pack.confidence_floor,
                    "consequence": "Case cannot auto-resolve; a human decides.",
                    "citations": [
                        f"{pack.category}.verification.confidence_floor = "
                        f"{pack.confidence_floor}"
                    ],
                },
            )
        )

    return result
