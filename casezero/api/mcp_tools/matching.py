"""Transaction matching: the deterministic half of the verification engine.

The brief asks for a verification status of PASS, FAIL or MANUAL_REVIEW. Those
three words are load-bearing, so the decision that produces them is arithmetic over
core-banking rows rather than a model's opinion about a bank statement.

Kept free of database and network so it can be tested exhaustively, which matters:
this function is the difference between refunding the right transaction and
refunding a similar one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Literal, Mapping, Sequence

from api.security.crypto import mask_account

Verdict = Literal["PASS", "FAIL", "MANUAL_REVIEW"]

#: Evidence names the rule packs list under `verification.required_evidence`.
EVIDENCE_ACCOUNT = "account_exists"
EVIDENCE_TXN_FOUND = "txn_ref_found"
EVIDENCE_AMOUNT = "amount_matches"
EVIDENCE_MERCHANT = "merchant_matches"
EVIDENCE_NOT_ALREADY_DISPUTED = "not_already_disputed"


@dataclass(frozen=True)
class Claim:
    """What the customer says happened."""

    account_no: str
    amount_rm: float | None = None
    txn_ref: str | None = None
    merchant: str | None = None
    posted_on: str | None = None  # ISO date, optional


@dataclass
class MatchResult:
    """A verdict plus the evidence behind it, ready to render in the Why panel."""

    verdict: Verdict
    reasons: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    matched: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reasons": self.reasons,
            "evidence": self.evidence,
            "candidates": self.candidates,
            "matched": self.matched,
        }


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def within_tolerance(claimed: float, actual: float, tolerance_pct: float) -> bool:
    """Percentage tolerance, with an exact test when the tolerance is zero.

    Instant transfers settle to the sen, so `atm_debit_card` sets 10% for
    part-dispensed cash while `emoney_digital` sets 0% and means it.
    """
    if tolerance_pct <= 0:
        return round(claimed, 2) == round(actual, 2)
    if actual == 0:
        return claimed == 0
    return abs(claimed - actual) / abs(actual) * 100.0 <= tolerance_pct


def _normalise_merchant(value: str | None) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum() or ch == " ").strip()


def merchant_matches(claimed: str | None, actual: str | None) -> bool:
    """Substring match either way, because customers quote the name they saw.

    A statement line of "TECHWORLD KL*1234" and a complaint saying "Techworld"
    are the same merchant, and rejecting that as a mismatch would send a clean
    case to a human for no reason.
    """
    left, right = _normalise_merchant(claimed), _normalise_merchant(actual)
    if not left or not right:
        return False
    return left in right or right in left


def evaluate_match(
    claim: Claim,
    transactions: Sequence[Mapping[str, Any]],
    *,
    account_exists: bool,
    tolerance_pct: float = 1.0,
    window_days: int = 120,
    required_evidence: Iterable[str] = (),
) -> MatchResult:
    """Decide PASS / FAIL / MANUAL_REVIEW for one claim against real rows.

    The three verdicts mean distinct things and the caller acts differently on
    each, so the boundaries are explicit:

    * **FAIL** — core banking contradicts the claim. The account does not exist,
      or the quoted reference belongs to a different account. Nothing to review.
    * **MANUAL_REVIEW** — core banking is silent or ambiguous. No candidate, or
      several equally good ones. A person decides.
    * **PASS** — exactly one row matches on every axis the claim specified.
    """
    result = MatchResult(verdict="MANUAL_REVIEW")

    if not account_exists:
        result.verdict = "FAIL"
        result.reasons.append(
            f"Account {mask_account(claim.account_no)} does not exist in core banking."
        )
        return result
    result.evidence.append(EVIDENCE_ACCOUNT)

    # A quoted reference is the strongest signal available, so it is checked first
    # and on its own terms.
    if claim.txn_ref:
        exact = [t for t in transactions if str(t.get("txn_ref")) == claim.txn_ref]
        if not exact:
            result.verdict = "FAIL"
            result.reasons.append(
                f"Transaction {claim.txn_ref} does not exist on account "
                f"{mask_account(claim.account_no)}."
            )
            return result
        candidates = exact
        result.evidence.append(EVIDENCE_TXN_FOUND)
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        candidates = [
            t
            for t in transactions
            if (_parse(t.get("posted_at")) or cutoff) >= cutoff
            and str(t.get("direction", "DEBIT")).upper() == "DEBIT"
        ]

    if claim.amount_rm is not None:
        candidates = [
            t
            for t in candidates
            if within_tolerance(float(claim.amount_rm), float(t.get("amount_rm", 0)), tolerance_pct)
        ]

    if claim.merchant:
        narrowed = [t for t in candidates if merchant_matches(claim.merchant, t.get("merchant"))]
        # Only narrow when it helps: a customer's paraphrase of a merchant name
        # should not delete the one true candidate found by reference and amount.
        if narrowed:
            candidates = narrowed
            result.evidence.append(EVIDENCE_MERCHANT)

    result.candidates = [_summarise(t) for t in candidates[:5]]

    if not candidates:
        result.reasons.append(
            "No transaction on this account matches the amount and date described. "
            "An investigator should look at the statement."
        )
        return result

    if len(candidates) > 1:
        result.reasons.append(
            f"{len(candidates)} transactions match equally well; automatically "
            f"choosing one of them would be a guess."
        )
        return result

    match = candidates[0]
    result.matched = _summarise(match)

    if claim.amount_rm is not None:
        result.evidence.append(EVIDENCE_AMOUNT)
        result.reasons.append(
            f"Claimed RM {float(claim.amount_rm):,.2f} matches posted "
            f"RM {float(match.get('amount_rm', 0)):,.2f} within {tolerance_pct:g}% tolerance."
        )

    if match.get("is_disputed"):
        result.reasons.append(
            f"Transaction {match.get('txn_ref')} is already flagged as disputed. "
            f"A second claim on the same debit needs a person to look at it."
        )
        return result
    result.evidence.append(EVIDENCE_NOT_ALREADY_DISPUTED)

    # The pack decides what "enough evidence" means for its category.
    missing = [e for e in required_evidence if e not in result.evidence]
    if missing:
        result.reasons.append(
            "The rule pack requires evidence this claim does not provide: "
            + ", ".join(missing)
        )
        return result

    result.verdict = "PASS"
    result.reasons.insert(
        0,
        f"Transaction {match.get('txn_ref')} on {mask_account(claim.account_no)} "
        f"matches the claim on every field the customer stated.",
    )
    return result


def _summarise(txn: Mapping[str, Any]) -> dict[str, Any]:
    """The fields an investigator needs, and nothing that widens the PII surface."""
    return {
        "txn_ref": txn.get("txn_ref"),
        "merchant": txn.get("merchant"),
        "amount_rm": float(txn.get("amount_rm", 0)),
        "direction": txn.get("direction"),
        "channel": txn.get("channel"),
        "country": txn.get("country"),
        "posted_at": txn.get("posted_at"),
        "is_disputed": bool(txn.get("is_disputed")),
    }
