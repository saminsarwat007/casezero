"""The shipped corpus is measured evidence, not an approximate folder of files."""

from __future__ import annotations

from collections import Counter
from email import policy
from email.parser import BytesParser
from pathlib import Path

from api.agents.firewall import scan
from api.corpus.labels import LABELS_PATH, load_evaluation_labels

CORPUS = LABELS_PATH.parent
EXPECTED = {
    "unauthorized_transaction": 70,
    "billing_error": 44,
    "mis_selling": 36,
    "atm_debit_card": 24,
    "insurance_takaful": 12,
    "loan_financing": 10,
    "emoney_digital": 4,
}


def test_corpus_has_exact_contract() -> None:
    rows = load_evaluation_labels()
    assert len(rows) == 200
    assert Counter(row["category"] for row in rows) == EXPECTED
    assert Counter(row["language"] for row in rows) == {"en": 100, "ms": 60, "mixed": 40}
    assert sum(row["injection"] for row in rows) == 5
    assert len(list(CORPUS.glob("CZ-*.eml"))) == 200
    assert len(list(CORPUS.glob("CZ-*.pdf"))) == 20


def test_every_email_parses_and_declares_synthetic_origin() -> None:
    for path in sorted(CORPUS.glob("CZ-*.eml")):
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        assert message["X-CaseZero-Synthetic"] == "true"
        assert message["From"].addresses[0].domain == "example.my"
        assert message.get_body(preferencelist=("plain",)).get_content().strip()


def test_all_injections_caught_with_zero_clean_false_positives() -> None:
    labels = {row["file"]: row for row in load_evaluation_labels()}
    for path in sorted(CORPUS.glob("CZ-*.eml")):
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        body = message.get_body(preferencelist=("plain",)).get_content()
        assert scan(body).hostile is bool(labels[path.name]["injection"])


def test_twenty_messages_carry_a_pdf_attachment() -> None:
    attached = 0
    for path in sorted(CORPUS.glob("CZ-*.eml")):
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        pdf_parts = [part for part in message.iter_attachments() if part.get_content_type() == "application/pdf"]
        attached += len(pdf_parts)
        for part in pdf_parts:
            fixture = CORPUS / part.get_filename()
            assert fixture.is_file()
            assert part.get_payload(decode=True) == fixture.read_bytes()
    assert attached == 20

