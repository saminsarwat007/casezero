"""Authorisation tickets.

The gate's ruling has to survive leaving the process. These tests are the argument
that it does: a ticket cannot be forged, edited, replayed against another case, or
stretched to a larger amount.
"""

import time

import pytest

from api.kernel import tickets
from api.kernel.tickets import TicketError

CASE = "11111111-1111-1111-1111-111111111111"
OTHER_CASE = "22222222-2222-2222-2222-222222222222"
ACCOUNT = "7142556890"


def mint(**overrides) -> str:
    kwargs = dict(
        case_id=CASE,
        account_no=ACCOUNT,
        amount_rm=2450.00,
        entry_type="REVERSAL",
        issued_by="kernel:gates",
    )
    kwargs.update(overrides)
    return tickets.issue(**kwargs)


def check(token, **overrides):
    kwargs = dict(
        case_id=CASE,
        account_no=ACCOUNT,
        amount_rm=2450.00,
        entry_type="REVERSAL",
    )
    kwargs.update(overrides)
    return tickets.verify(token, **kwargs)


class TestHappyPath:
    def test_a_freshly_minted_ticket_verifies(self):
        ticket = check(mint())
        assert ticket.case_id == CASE
        assert ticket.amount_rm == 2450.00
        assert ticket.issued_by == "kernel:gates"

    def test_amounts_survive_the_round_trip_exactly(self):
        """Money is carried in sen so a float never decides whether a payout matches."""
        for amount in (0.01, 99.99, 2450.00, 1234.56, 250000.00):
            assert check(mint(amount_rm=amount), amount_rm=amount).amount_rm == amount

    def test_a_ticket_is_opaque_and_url_safe(self):
        token = mint()
        assert "." in token
        assert " " not in token
        assert ACCOUNT not in token  # the account is signed over, not printed


class TestRefusals:
    def test_no_ticket_is_refused_with_an_explanation(self):
        with pytest.raises(TicketError, match="has not been authorised"):
            check(None)

    def test_an_empty_ticket_is_refused(self):
        with pytest.raises(TicketError):
            check("")

    def test_a_malformed_ticket_is_refused(self):
        with pytest.raises(TicketError, match="Malformed"):
            check("not-a-ticket")

    def test_a_forged_signature_is_refused(self):
        payload, _, _ = mint().partition(".")
        with pytest.raises(TicketError, match="signature is invalid"):
            check(f"{payload}.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")

    def test_an_edited_payload_is_refused(self):
        """The attack that matters: raise the amount and keep the signature."""
        import base64
        import json

        payload, _, signature = mint().partition(".")
        claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
        claims["amount_sen"] = 999_999_00
        edited = base64.urlsafe_b64encode(
            json.dumps(claims, sort_keys=True, separators=(",", ":")).encode()
        ).decode().rstrip("=")

        with pytest.raises(TicketError, match="signature is invalid"):
            check(f"{edited}.{signature}", amount_rm=999_999.00)

    def test_an_expired_ticket_is_refused(self):
        token = mint(ttl_seconds=-1)
        with pytest.raises(TicketError, match="expired"):
            check(token)

    def test_a_ticket_cannot_be_replayed_against_another_case(self):
        with pytest.raises(TicketError, match="case"):
            check(mint(), case_id=OTHER_CASE)

    def test_a_ticket_cannot_be_pointed_at_another_account(self):
        with pytest.raises(TicketError, match="account"):
            check(mint(), account_no="7142559999")

    def test_a_ticket_cannot_be_presented_for_a_larger_amount(self):
        with pytest.raises(TicketError, match="amount"):
            check(mint(amount_rm=90.00), amount_rm=9000.00)

    def test_even_one_sen_over_is_refused(self):
        with pytest.raises(TicketError, match="amount"):
            check(mint(amount_rm=2450.00), amount_rm=2450.01)

    def test_a_ticket_cannot_change_the_entry_type(self):
        """A reversal and a credit adjustment mean different things to the ledger."""
        with pytest.raises(TicketError, match="entry type"):
            check(mint(), entry_type="CREDIT_ADJUSTMENT")

    def test_a_ticket_for_nothing_is_never_minted(self):
        for amount in (0, -1, -2450.00):
            with pytest.raises(TicketError):
                mint(amount_rm=amount)


class TestExpiry:
    def test_the_default_window_is_short(self):
        assert tickets.DEFAULT_TTL_SECONDS <= 300

    def test_a_ticket_is_valid_inside_its_window(self):
        token = mint(ttl_seconds=60)
        assert check(token).expires_at > int(time.time())
