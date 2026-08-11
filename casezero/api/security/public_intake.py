"""Admission control for the public complaint composer.

A stakeholder must be able to write their own complaint and attach their own
document, because a fixed fixture proves nothing about how the pipeline handles
their wording. But an unauthenticated compose box pointed at a bank pipeline is
an open PII intake channel, and no bank would accept that.

This module is the boundary that makes the composer safe:

* The complaint must be **filed against an allow-listed synthetic account.** The
  ledger only contains fictional customers, so nothing else can be verified.
* Any *other* Malaysian account number or NRIC in the text is **refused, not
  scrubbed.** Silently stripping identifiers would teach a stakeholder that the
  channel accepts real data.
* Free text and attachments are size-bounded before they reach a model.

Deterministic and LLM-free by design. Covered by api/tests/test_public_intake.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: The seeded synthetic customers from api/db/seed.py. These are the only
#: identities the public composer may file a complaint against, because they are
#: the only identities the synthetic core-banking ledger can verify.
ALLOWED_PERSONAS: tuple[dict[str, str], ...] = (
    {
        "account_no": "7142556890",
        "full_name": "Ahmad bin Ismail",
        "email": "ahmad.ismail@example.my",
        "segment": "retail",
        "product": "savings",
    },
    {
        "account_no": "7142001233",
        "full_name": "Siti binti Rahman",
        "email": "siti.rahman@example.my",
        "segment": "vulnerable",
        "product": "savings",
    },
    {
        "account_no": "7142778812",
        "full_name": "Lim Wei Jian",
        "email": "lim.weijian@example.my",
        "segment": "retail",
        "product": "credit_card",
    },
    {
        "account_no": "7142334455",
        "full_name": "Nur Aisyah binti Kamal",
        "email": "nur.aisyah@example.my",
        "segment": "retail",
        "product": "savings",
    },
    {
        "account_no": "7142889900",
        "full_name": "Rajesh Kumar",
        "email": "rajesh.kumar@example.my",
        "segment": "retail",
        "product": "current",
    },
    {
        "account_no": "7142112233",
        "full_name": "Chong Ka Wai",
        "email": "chong.kawai@example.my",
        "segment": "sme",
        "product": "current",
    },
)

ALLOWED_ACCOUNTS = frozenset(persona["account_no"] for persona in ALLOWED_PERSONAS)
ALLOWED_EMAILS = frozenset(persona["email"] for persona in ALLOWED_PERSONAS)

#: MYBank retail account numbers are ten digits. Matching the shape rather than
#: the exact value is what lets us refuse a *real* one.
ACCOUNT_SHAPE = re.compile(r"(?<!\d)\d{10}(?!\d)")

#: Malaysian NRIC: YYMMDD-PB-###G, with or without the hyphens.
NRIC_SHAPE = re.compile(r"(?<!\d)\d{6}[- ]?\d{2}[- ]?\d{4}(?!\d)")

#: Public composer bounds. Generous enough for a real complaint, small enough
#: that the channel is not a bulk upload surface.
MAX_SUBJECT = 160
MAX_BODY = 4000
MAX_ATTACHMENT_BYTES = 4 * 1024 * 1024
ALLOWED_ATTACHMENT_TYPES = frozenset({"application/pdf"})

MIN_AMOUNT_RM = 1.0
MAX_AMOUNT_RM = 100_000.0


class PublicIntakeRefused(ValueError):
    """The submitted complaint may not enter the public pipeline."""

    def __init__(self, reason: str, *, code: str) -> None:
        super().__init__(reason)
        self.code = code


@dataclass(frozen=True)
class AdmittedComplaint:
    """A public submission the guard is willing to execute."""

    account_no: str
    persona_name: str
    from_name: str
    from_email: str
    subject: str
    body: str
    amount_rm: float
    merchant: str
    attachment_name: str | None
    attachment_bytes: bytes | None

    @property
    def has_attachment(self) -> bool:
        return bool(self.attachment_bytes)


def persona_for(account_no: str) -> dict[str, str] | None:
    for persona in ALLOWED_PERSONAS:
        if persona["account_no"] == account_no:
            return persona
    return None


def _refuse_foreign_identifiers(text: str, allowed_account: str) -> None:
    """Refuse any identifier that is not the allow-listed synthetic account."""
    for found in ACCOUNT_SHAPE.findall(text):
        if found not in ALLOWED_ACCOUNTS:
            raise PublicIntakeRefused(
                "This public runner accepts only the listed fictional accounts. "
                f"Remove the account number ending {found[-4:]} and use the "
                "selected synthetic customer instead.",
                code="FOREIGN_ACCOUNT",
            )
        if found != allowed_account:
            raise PublicIntakeRefused(
                "The complaint text names a different fictional account than the "
                "one selected. Keep both consistent so core banking can verify it.",
                code="ACCOUNT_MISMATCH",
            )
    if NRIC_SHAPE.search(text):
        raise PublicIntakeRefused(
            "Identity numbers are never accepted through the public runner. "
            "Delete the NRIC and describe the dispute instead.",
            code="NRIC_PRESENT",
        )


def admit(
    *,
    account_no: str,
    from_name: str,
    from_email: str,
    subject: str,
    body: str,
    amount_rm: float | str,
    merchant: str,
    attachment_name: str | None = None,
    attachment_type: str | None = None,
    attachment_bytes: bytes | None = None,
) -> AdmittedComplaint:
    """Validate one public submission, or refuse it with a reason a person can act on."""
    account = (account_no or "").strip()
    persona = persona_for(account)
    if persona is None:
        raise PublicIntakeRefused(
            "Choose one of the listed fictional customers. The public runner cannot "
            "file a complaint against an account the synthetic ledger does not hold.",
            code="UNKNOWN_ACCOUNT",
        )

    clean_subject = " ".join((subject or "").split())
    if len(clean_subject) < 4:
        raise PublicIntakeRefused("Give the complaint a subject line.", code="SUBJECT_TOO_SHORT")
    if len(clean_subject) > MAX_SUBJECT:
        raise PublicIntakeRefused(
            f"Keep the subject under {MAX_SUBJECT} characters.", code="SUBJECT_TOO_LONG"
        )

    clean_body = (body or "").strip()
    if len(clean_body) < 20:
        raise PublicIntakeRefused(
            "Describe the dispute in at least a sentence so the classifier has something to read.",
            code="BODY_TOO_SHORT",
        )
    if len(clean_body) > MAX_BODY:
        raise PublicIntakeRefused(
            f"Keep the complaint under {MAX_BODY} characters.", code="BODY_TOO_LONG"
        )

    email = (from_email or persona["email"]).strip().lower()
    if email not in ALLOWED_EMAILS:
        raise PublicIntakeRefused(
            "The sender address must belong to the selected fictional customer. "
            "A real inbox is never used on the public runner.",
            code="FOREIGN_SENDER",
        )

    _refuse_foreign_identifiers(f"{clean_subject}\n{clean_body}", account)

    try:
        amount = round(float(amount_rm), 2)
    except (TypeError, ValueError) as exc:
        raise PublicIntakeRefused("Enter the disputed amount in ringgit.", code="BAD_AMOUNT") from exc
    if not MIN_AMOUNT_RM <= amount <= MAX_AMOUNT_RM:
        raise PublicIntakeRefused(
            f"The disputed amount must be between RM{MIN_AMOUNT_RM:,.2f} and RM{MAX_AMOUNT_RM:,.2f}.",
            code="AMOUNT_OUT_OF_RANGE",
        )

    clean_merchant = " ".join((merchant or "").split())[:80] or "UNSPECIFIED MERCHANT"

    payload: bytes | None = None
    name: str | None = None
    if attachment_bytes:
        if len(attachment_bytes) > MAX_ATTACHMENT_BYTES:
            raise PublicIntakeRefused(
                f"Attachments are limited to {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB "
                "on the public runner.",
                code="ATTACHMENT_TOO_LARGE",
            )
        declared = (attachment_type or "").split(";", 1)[0].strip().lower()
        is_pdf = attachment_bytes[:5] == b"%PDF-"
        if declared not in ALLOWED_ATTACHMENT_TYPES and not is_pdf:
            raise PublicIntakeRefused(
                "Only PDF evidence is accepted. The intake agent reads it with vision OCR.",
                code="ATTACHMENT_NOT_PDF",
            )
        if not is_pdf:
            raise PublicIntakeRefused(
                "That file is not a readable PDF. Export the statement or receipt as PDF and retry.",
                code="ATTACHMENT_CORRUPT",
            )
        payload = attachment_bytes
        name = " ".join((attachment_name or "evidence.pdf").split())[:120] or "evidence.pdf"

    return AdmittedComplaint(
        account_no=account,
        persona_name=persona["full_name"],
        from_name=" ".join((from_name or persona["full_name"]).split())[:120],
        from_email=email,
        subject=clean_subject,
        body=clean_body,
        amount_rm=amount,
        merchant=clean_merchant,
        attachment_name=name,
        attachment_bytes=payload,
    )
