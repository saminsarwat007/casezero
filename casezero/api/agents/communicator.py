"""Agent 5 — Communicator. The model writes the human half; the kernel owns the rest.

A letter to a complainant carries obligations: acknowledge the complaint, quote the
reference, state the deadline as a date rather than a duration, give a contact
channel, and — where the customer may still be dissatisfied — tell them about the
Financial Markets Ombudsman Service and their six-month window.

A model *asked* to include all of that will include it almost every time. Almost
every time is not a compliance posture. So the flow here is:

    draft (model) → lint (kernel, deterministic) → repair → authorize_send (kernel)

`lint_outbound` inserts the FMOS clause verbatim from the rule pack when it is
required and absent. Anything it cannot repair — a prohibited promise, a missing
figure — blocks the send, and `authorize_send` returns DENY. A blocked letter is
not rewritten until it passes; it goes to a person.

The customer's name never reaches the model. The draft is written to "Dear
Customer" and the name is substituted locally afterwards, so the outbound path
adds no PII to the prompt surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from api.agents import firewall
from api.agents.base import KERNEL, Event, agent_actor
from api.agents.classifier import ClassifierResult
from api.agents.schemas import Draft
from api.agents.verifier import VerifierResult
from api.kernel import gates
from api.kernel.gates import GateDecision
from api.kernel.lint import LintContext, LintReport, amount_renderings, lint_outbound
from api.kernel.rules import RulePack

ACTOR = agent_actor("communicator")

NAME_PLACEHOLDER = "Dear Customer"

COMMUNICATOR_SYSTEM = (
    firewall.CONTAINMENT_PREAMBLE
    + " You write the explanatory part of complaint-resolution letters for a "
    "Malaysian bank. You produce exactly two things: a plain-language summary in "
    "two to four short sentences, and one paragraph in a formal register. You do "
    "not write the greeting, the case reference, the deadline, the contact details "
    "or the sign-off — those are added by the bank's compliance system and any "
    "attempt to write them yourself will be discarded. State only facts you are "
    "given: never invent a date, an amount or a reason. Do not offer legal advice "
    "and do not promise anything about a future outcome."
)

#: How each outcome is described to the customer, and in the subject line.
OUTCOME_LINES: dict[str, tuple[str, str]] = {
    "RESOLVED_IN_FULL": (
        "resolved",
        "We have completed our investigation, upheld your complaint, and credited "
        "the disputed amount back to your account.",
    ),
    "PARTIALLY_RESOLVED": (
        "partially resolved",
        "We have completed our investigation and upheld part of your complaint.",
    ),
    "REJECTED": (
        "our decision",
        "We have completed our investigation and are unable to uphold your "
        "complaint on the evidence available to us.",
    ),
    "PENDING": (
        "under review",
        "Your complaint is with our investigation team. We will write to you again "
        "with our decision.",
    ),
    "CUSTOMER_DISSATISFIED": (
        "our final decision",
        "We have reviewed your complaint again and our decision is unchanged.",
    ),
}


@dataclass
class CommunicatorResult:
    subject: str
    body: str
    report: LintReport
    decision: GateDecision
    sent: bool
    source: str = "model"  # model | template
    attempts: int = 1
    events: list[Event] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return not self.sent


# ─── The regulatory half, written by code ───────────────────────────────────
# Every sentence here discharges an obligation, so none of them is paraphrased by
# a model. The Malay wording is the bank's own; the deadline is rendered
# identically in both languages because it is a date, not a translation.

ENGLISH = {
    "ack": "We acknowledge receipt of your complaint. Your case reference is {ref}.",
    "amount": "The amount in dispute is RM {amount}.",
    "deadline": "Under Bank Negara Malaysia's complaints handling requirements, we "
                "will complete our handling of this complaint by {date}.",
    "contact": "If you have any questions about this complaint, please contact us "
               "at {email}.",
    "note": "Please also note: {items}.",
    "signoff": "Yours sincerely,\nComplaints Resolution, {bank}",
}

MALAY = {
    "ack": "Kami mengesahkan penerimaan aduan anda. Rujukan kes anda ialah {ref}.",
    "amount": "Jumlah yang dipertikaikan ialah RM {amount}.",
    "deadline": "Selaras dengan keperluan pengendalian aduan Bank Negara Malaysia, "
                "kami akan menyelesaikan pengendalian aduan ini menjelang {date}.",
    "contact": "Sekiranya anda mempunyai sebarang pertanyaan, sila hubungi kami di "
               "{email}.",
    "note": "Sila ambil perhatian: {items}.",
    "signoff": "Yang benar,\nPenyelesaian Aduan, {bank}",
}


def outstanding_phrases(pack: RulePack, body: str) -> list[str]:
    """Disclosure phrases a pack requires that the letter does not yet carry.

    Swept rather than hardcoded per category: a new pack that demands the NSRC
    hotline or a CCRIS correction notice gets a compliant letter without a code
    change, which is the test of whether adding a category is really configuration.
    """
    lowered = body.lower()
    missing: list[str] = []
    for disclosure in pack.mandatory_disclosures:
        for phrase in disclosure.get("text_contains", ()):
            if str(phrase).lower() not in lowered and str(phrase) not in missing:
                missing.append(str(phrase))
    return missing


def section(
    context: LintContext,
    *,
    plain: str,
    formal: str,
    bank_name: str,
    contact_email: str,
    words: dict[str, str] = ENGLISH,
    greeting: str = NAME_PLACEHOLDER,
    extra: Sequence[str] = (),
    include_amount: bool = True,
) -> str:
    """One language of the letter: greeting, obligations, explanation, sign-off.

    Structure is owned here rather than requested in a prompt, which is why the
    letter always has paragraph breaks, always opens by acknowledging the
    complaint and always closes with a contact channel.
    """
    paragraphs = [f"{greeting},", words["ack"].format(ref=context.case_ref)]
    if plain.strip():
        paragraphs.append(plain.strip())
    if formal.strip():
        paragraphs.append(formal.strip())
    if include_amount and context.amount_rm is not None:
        paragraphs.append(
            words["amount"].format(amount=f"{float(context.amount_rm):,.2f}")
        )
    if context.due_date_display:
        paragraphs.append(words["deadline"].format(date=context.due_date_display))
    paragraphs.append(words["contact"].format(email=contact_email))
    paragraphs.extend(extra)
    paragraphs.append(words["signoff"].format(bank=bank_name))
    return "\n\n".join(paragraphs)


def assemble(
    pack: RulePack,
    context: LintContext,
    *,
    plain: str,
    formal: str,
    bank_name: str,
    contact_email: str,
    plain_ms: str = "",
    formal_ms: str = "",
) -> str:
    """The whole letter, in every language the pack requires.

    The two repair passes are both about not saying the same thing twice. The
    disclosure sweep runs once over the finished text rather than per language,
    because a phrase satisfied in the English half is satisfied and appending an
    English compliance phrase to a Malay paragraph would be worse than useless.
    The amount sentence is added only when the figure is not already stated
    exactly — checked against `lint.amount_renderings`, so the writer and the
    checker cannot drift apart.
    """
    def build(extra: Sequence[str] = (), *, include_amount: bool = False) -> str:
        english = section(
            context,
            plain=plain,
            formal=formal,
            bank_name=bank_name,
            contact_email=contact_email,
            extra=extra,
            include_amount=include_amount,
        )
        if "ms" not in pack.languages:
            return english
        malay = section(
            context,
            plain=plain_ms,
            formal=formal_ms,
            bank_name=bank_name,
            contact_email=contact_email,
            words=MALAY,
            greeting="Pelanggan yang Dihormati",
            include_amount=include_amount,
        )
        return f"{english}\n\n---\n\n{malay}"

    body = build()

    state_amount = context.amount_rm is not None and not any(
        rendering in body for rendering in amount_renderings(float(context.amount_rm))
    )
    if state_amount:
        body = build(include_amount=True)

    missing = outstanding_phrases(pack, body)
    if missing:
        body = build(
            extra=[ENGLISH["note"].format(items="; ".join(missing))],
            include_amount=state_amount,
        )
    return body


def compose_template(
    pack: RulePack,
    context: LintContext,
    *,
    bank_name: str,
    contact_email: str,
    reasons: list[str] | None = None,
) -> str:
    """The letter when no model is available.

    The same assembly, with the explanatory paragraphs written from the outcome
    and the verifier's findings instead of by a model. It is not as warm, and it
    is fully compliant.
    """
    _, outcome_sentence = OUTCOME_LINES.get(context.outcome, OUTCOME_LINES["PENDING"])
    formal = ""
    if reasons:
        formal = "Our investigation found: " + " ".join(
            r.rstrip(".") + "." for r in reasons[:3]
        )

    return assemble(
        pack,
        context,
        plain=outcome_sentence,
        formal=formal,
        bank_name=bank_name,
        contact_email=contact_email,
    )


# ─── The model draft ────────────────────────────────────────────────────────


def _requirements(pack: RulePack, context: LintContext) -> str:
    """The brief handed to the model.

    Short, because the model is no longer responsible for the obligations — code
    writes those. What is left is what a model is actually good at: explaining a
    decision to a person who is upset about money.
    """
    items = [
        "Write the plain summary for someone with no banking background.",
        "Do not write a greeting, a sign-off, the case reference, a deadline "
        "date or a contact address — they are added afterwards.",
    ]
    if context.amount_rm is not None:
        items.append(
            f"If you mention the amount, write it as RM "
            f"{float(context.amount_rm):,.2f}."
        )
    for phrase in pack.prohibited_phrases:
        items.append(f"Never write: {phrase!r}.")
    if "ms" in pack.languages:
        items.append("Provide Bahasa Malaysia versions of both paragraphs.")
    return "\n".join(f"- {item}" for item in items)


async def draft(
    pack: RulePack,
    context: LintContext,
    ctx: Any,
    *,
    summary: str,
    reasons: list[str],
    repair_notes: str = "",
) -> tuple[str, str, str]:
    """(subject, body, source). Falls back to the template on any model failure."""
    heading, outcome_sentence = OUTCOME_LINES.get(
        context.outcome, OUTCOME_LINES["PENDING"]
    )
    subject = f"Your complaint {context.case_ref} — {heading}"

    prompt = (
        f"Write a complaint-resolution letter.\n\n"
        f"Case reference: {context.case_ref}\n"
        f"Outcome: {context.outcome} — {outcome_sentence}\n"
        f"What the customer told us: {summary or '(not summarised)'}\n"
        f"What our investigation found:\n"
        + ("\n".join(f"- {r}" for r in reasons[:5]) or "- (no findings recorded)")
        + f"\n\nRequirements:\n{_requirements(pack, context)}\n"
    )
    if repair_notes:
        prompt += (
            f"\nA previous draft was rejected by the compliance linter for these "
            f"reasons. Fix every one of them:\n{repair_notes}\n"
        )

    fallback = lambda: (  # noqa: E731 - one expression, used twice
        subject,
        compose_template(
            pack,
            context,
            bank_name=ctx.settings.bank_name,
            contact_email=ctx.settings.bank_complaints_email,
            reasons=reasons,
        ),
        "template",
    )

    try:
        result = await ctx.complete(
            "communicator", prompt, system=COMMUNICATOR_SYSTEM, schema=Draft,
            temperature=0.3,
        )
    except Exception as exc:  # noqa: BLE001 - a letter must still go out
        ctx.note_degraded(f"communicator model unavailable: {exc}")
        return fallback()

    data = result.data or {}
    plain = str(data.get("plain_summary") or "").strip()
    formal = str(data.get("formal_paragraph") or "").strip()
    if not plain and not formal:
        ctx.note_degraded("communicator returned an empty draft")
        return fallback()

    body = assemble(
        pack,
        context,
        plain=plain,
        formal=formal,
        plain_ms=str(data.get("plain_summary_ms") or "").strip(),
        formal_ms=str(data.get("formal_paragraph_ms") or "").strip(),
        bank_name=ctx.settings.bank_name,
        contact_email=ctx.settings.bank_complaints_email,
    )
    return str(data.get("subject") or subject), body, "model"


# ─── The agent ──────────────────────────────────────────────────────────────


async def run(
    case: dict[str, Any],
    classification: ClassifierResult,
    verification: VerifierResult,
    ctx: Any,
    *,
    outcome: str,
    summary: str = "",
    customer_name: str | None = None,
    amount_rm: float | None = None,
) -> CommunicatorResult:
    pack = classification.pack
    context = LintContext(
        case_ref=str(case.get("case_ref", "")),
        amount_rm=amount_rm,
        outcome=outcome,
        due_date_display=classification.sla.due_date_display,
        language=classification.pack.languages[0] if pack.languages else "en",
    )
    reasons = list(verification.reasons)

    subject, body, source = await draft(
        pack, context, ctx, summary=summary, reasons=reasons
    )
    report = lint_outbound(pack, body, context)
    attempts = 1

    # One repair pass. If the model cannot satisfy the requirements when told
    # exactly which ones it missed, the letter is not going to be fixed by asking
    # a third time — it goes to a person.
    if report.blocked and source == "model":
        notes = "\n".join(f"- {f.rule_id}: {f.detail}" for f in report.failures)
        subject, body, source = await draft(
            pack, context, ctx, summary=summary, reasons=reasons, repair_notes=notes
        )
        report = lint_outbound(pack, body, context)
        attempts = 2

    # Personalise after linting: the name is local data and was never in a prompt.
    if customer_name:
        report.body = report.body.replace(NAME_PLACEHOLDER, f"Dear {customer_name}")

    decision = gates.authorize_send(report)
    sent = decision.allowed

    events = [
        Event(
            type="DRAFT_LINTED",
            actor=KERNEL,
            payload={
                "source": source,
                "attempts": attempts,
                "summary": report.summary(),
                "repaired": report.repaired,
                "findings": [
                    {
                        "rule_id": f.rule_id,
                        "requirement": f.requirement,
                        "status": f.status,
                        "detail": f.detail,
                    }
                    for f in report.findings
                ],
            },
        ),
        Event(
            type="MESSAGE_SENT" if sent else "MESSAGE_BLOCKED",
            actor=ACTOR if sent else KERNEL,
            payload={
                "subject": subject,
                "outcome": outcome,
                "body": report.body,
                "chars": len(report.body),
                "gate": "authorize_send",
                "action": decision.action,
                "reasons": list(decision.reasons),
                "citations": list(decision.citations),
            },
        ),
    ]

    return CommunicatorResult(
        subject=subject,
        body=report.body,
        report=report,
        decision=decision,
        sent=sent,
        source=source,
        attempts=attempts,
        events=events,
    )
