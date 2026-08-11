"""The public composer accepts a stakeholder's own words, not their customers' data.

These tests exist because the composer is the one place where an unauthenticated
person types free text into a bank pipeline. The interesting assertions are all
refusals.
"""

import pytest

from api.security.public_intake import (
    ALLOWED_PERSONAS,
    MAX_ATTACHMENT_BYTES,
    PublicIntakeRefused,
    admit,
)

AHMAD = ALLOWED_PERSONAS[0]

BASE = {
    "account_no": AHMAD["account_no"],
    "from_name": AHMAD["full_name"],
    "from_email": AHMAD["email"],
    "subject": "Unauthorised card transaction",
    "body": "I did not authorise this card payment. Please investigate and reverse it.",
    "amount_rm": "2450.00",
    "merchant": "TECHWORLD KL",
}


def submit(**overrides):
    return admit(**{**BASE, **overrides})


def test_a_stakeholder_may_write_their_own_complaint():
    complaint = submit(
        subject="My debit card was charged twice",
        body="Two identical charges appeared on the same day. I only made one purchase.",
        amount_rm="180.50",
        merchant="LOTUS KOTA DAMANSARA",
    )

    assert complaint.subject == "My debit card was charged twice"
    assert complaint.amount_rm == 180.50
    assert complaint.merchant == "LOTUS KOTA DAMANSARA"
    assert complaint.has_attachment is False


def test_a_foreign_account_number_is_refused_not_scrubbed():
    """Silently stripping it would teach the visitor that real data is accepted."""
    with pytest.raises(PublicIntakeRefused) as refused:
        submit(body="Please check account 9988776655 for the disputed debit of RM90.")

    assert refused.value.code == "FOREIGN_ACCOUNT"


def test_naming_a_different_allow_listed_account_is_refused():
    other = ALLOWED_PERSONAS[1]["account_no"]
    with pytest.raises(PublicIntakeRefused) as refused:
        submit(body=f"The debit came from account {other}, please reverse it now.")

    assert refused.value.code == "ACCOUNT_MISMATCH"


def test_an_nric_is_always_refused():
    with pytest.raises(PublicIntakeRefused) as refused:
        submit(body="My NRIC is 880412-14-5521 and I dispute the charge shown above.")

    assert refused.value.code == "NRIC_PRESENT"


def test_a_real_inbox_cannot_be_used_as_the_sender():
    with pytest.raises(PublicIntakeRefused) as refused:
        submit(from_email="someone@gmail.com")

    assert refused.value.code == "FOREIGN_SENDER"


def test_an_unknown_account_cannot_be_disputed():
    with pytest.raises(PublicIntakeRefused) as refused:
        submit(account_no="1234567890")

    assert refused.value.code == "UNKNOWN_ACCOUNT"


def test_an_amount_outside_the_public_band_is_refused():
    with pytest.raises(PublicIntakeRefused) as refused:
        submit(amount_rm="480000")

    assert refused.value.code == "AMOUNT_OUT_OF_RANGE"


def test_a_pdf_attachment_is_accepted_for_vision_ocr():
    complaint = submit(
        attachment_name="statement.pdf",
        attachment_type="application/pdf",
        attachment_bytes=b"%PDF-1.4 minimal",
    )

    assert complaint.has_attachment is True
    assert complaint.attachment_name == "statement.pdf"


def test_a_non_pdf_masquerading_as_pdf_is_refused():
    with pytest.raises(PublicIntakeRefused) as refused:
        submit(
            attachment_name="payload.pdf",
            attachment_type="application/pdf",
            attachment_bytes=b"MZ\x90\x00 not a pdf at all",
        )

    assert refused.value.code == "ATTACHMENT_CORRUPT"


def test_an_oversized_attachment_is_refused():
    with pytest.raises(PublicIntakeRefused) as refused:
        submit(
            attachment_name="huge.pdf",
            attachment_type="application/pdf",
            attachment_bytes=b"%PDF-" + b"0" * MAX_ATTACHMENT_BYTES,
        )

    assert refused.value.code == "ATTACHMENT_TOO_LARGE"


def test_an_empty_complaint_is_refused():
    with pytest.raises(PublicIntakeRefused) as refused:
        submit(body="stolen")

    assert refused.value.code == "BODY_TOO_SHORT"
