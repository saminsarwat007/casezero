"""Who works this case, what human desk each one replaces, and what that desk costs.

The case study states a 90-minute average across multiple departments. That number
is only useful if it can be attributed, so it is split here across the seven
observable pipeline stages — and the split must sum to exactly 90, which
`test_roster.py` asserts. A savings figure nobody can decompose is a slogan.

Two things in this file are different in kind and are kept visibly apart:

* **Measured** — elapsed time, which comes from the timestamps on the hash chain.
  Nothing here invents it.
* **Baseline** — the manual minutes each stage replaces. This is an *assumption*
  derived from the brief's 90-minute figure, and it is labelled as one everywhere
  it surfaces. A judge who disputes the split can change it in one place.

`brain` is the routing key into `ModelRouter.ROUTES`. Where it is `None` the seat
makes no model call at all, and that is the point: the two seats standing closest
to the money — Verifier and Resolver — have no brain to talk out of.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: The manual baseline the case study gives for one dispute, end to end.
BASELINE_MINUTES_TOTAL = 90

#: Fully loaded cost of one Malaysian bank complaints analyst hour. An assumption,
#: surfaced as one, and adjustable by the viewer rather than buried in a slide.
DEFAULT_ANALYST_HOURLY_RM = 24.0


@dataclass(frozen=True)
class Seat:
    """One participant in the case, agent or kernel."""

    id: str
    name: str
    #: "agent" reasons and proposes. "kernel" decides and cannot be argued with.
    kind: str
    #: One line: what this seat is for.
    role: str
    #: Routing key into ModelRouter.ROUTES, or None when no model is ever called.
    brain: str | None
    #: The human desk this seat stands in for today.
    replaces: str
    #: What it is accountable for under the brief's regulatory framing.
    obligation: str


#: Order is the order they act in. The kernel sits between them all.
SEATS: tuple[Seat, ...] = (
    Seat(
        id="intake",
        name="Intake",
        kind="agent",
        role="Reads the email and any PDF, extracts the claim, blocks injected instructions",
        brain="intake",
        replaces="Complaints desk — opening mail, reading attachments, keying in details",
        obligation="Identifiers encrypted and redacted before any model sees them",
    ),
    Seat(
        id="classifier",
        name="Classifier",
        kind="agent",
        role="Decides which of the seven dispute categories this is, and how sure it is",
        brain="classifier",
        replaces="Complaints officer — categorising and writing up the case",
        obligation="Category and confidence stamped on the case record",
    ),
    Seat(
        id="kernel",
        name="Compliance Kernel",
        kind="kernel",
        role="Applies the rule pack: urgency, working-day deadline, and whether money may move",
        brain=None,
        replaces="Compliance officer and team lead — SLA diary and approval limits",
        obligation="BNM Complaints Handling working-day window; auto-approval and dual-control limits",
    ),
    Seat(
        id="verifier",
        name="Verifier",
        kind="agent",
        role="Queries core banking and CRM over MCP and compares the claim to the ledger",
        brain=None,
        replaces="Investigator — logging into core banking and CRM to pull the transaction",
        obligation="PASS, FAIL or MANUAL_REVIEW returned with the evidence behind it",
    ),
    Seat(
        id="resolver",
        name="Resolver",
        kind="agent",
        role="Posts the reversal or credit, but only against a signed kernel ticket",
        brain=None,
        replaces="Finance operations — raising the journal and chasing approval",
        obligation="Balanced double entry; posting refused without a signed authorisation",
    ),
    Seat(
        id="communicator",
        name="Communicator",
        kind="agent",
        role="Drafts the customer letter; the kernel inserts and enforces the regulatory text",
        brain="communicator",
        replaces="Compliance and communications — drafting and reviewing the reply",
        obligation="FMOS six-month referral right for eligible claims up to RM250,000",
    ),
    Seat(
        id="supervisor",
        name="Supervisor",
        kind="agent",
        role="Watches the deadline on every open case and escalates before it is missed",
        brain=None,
        replaces="Team lead — manually reviewing the deadline report",
        obligation="Deadline forecast ahead of breach, against the 11% miss rate today",
    ),
)

SEATS_BY_ID: dict[str, Seat] = {seat.id: seat for seat in SEATS}


#: The seven observable pipeline stages, in execution order. The persisted proof,
#: the live progress feed and the handoff builder all read this one list, so a
#: stage can never appear in one view and be missing from another.
#: (stage_id, label, event_type, agent)
PIPELINE_STAGES: tuple[tuple[str, str, str, str], ...] = (
    ("intake", "Check for harmful content", "INTAKE_EXTRACTED", "Intake agent"),
    ("classify", "Identify the complaint type", "CLASSIFIED", "Classifier agent"),
    ("sla", "Set priority and deadline", "URGENCY_ASSIGNED", "Compliance kernel"),
    ("verify", "Check against bank records", "VERIFICATION_COMPLETED", "Verifier agent (MCP)"),
    ("gate", "Decide: auto-resolve or human review", "GATE_DECISION", "Financial gate"),
    ("journal", "Move the money", "JOURNAL_POSTED", "Resolver agent"),
    ("communicate", "Send response to customer", "MESSAGE_SENT", "Communicator agent"),
)

#: stage_id -> (who speaks, who receives, manual minutes this stage replaces)
#:
#: The minutes sum to BASELINE_MINUTES_TOTAL. Weighted towards verification
#: because that is the step the brief describes as crossing departments.
STAGE_ROLES: dict[str, tuple[str, str, int]] = {
    "intake": ("intake", "classifier", 15),
    "classify": ("classifier", "kernel", 12),
    "sla": ("kernel", "verifier", 8),
    "verify": ("verifier", "kernel", 25),
    "gate": ("kernel", "resolver", 10),
    "journal": ("resolver", "communicator", 12),
    "communicate": ("communicator", "customer", 8),
}


def baseline_minutes(stage_id: str) -> int:
    entry = STAGE_ROLES.get(stage_id)
    return entry[2] if entry else 0


def roster(router: Any = None) -> dict[str, Any]:
    """The seats, each with the brain that will actually run behind it.

    `router.describe()` is asked rather than assumed, so a deployment missing a
    Groq key reports Gemini — the panel shows the routing that is running, not
    the routing that was intended.
    """
    seats: list[dict[str, Any]] = []
    for seat in SEATS:
        entry: dict[str, Any] = {
            "id": seat.id,
            "name": seat.name,
            "kind": seat.kind,
            "role": seat.role,
            "replaces": seat.replaces,
            "obligation": seat.obligation,
            "uses_model": seat.brain is not None,
            "provider": None,
            "model": None,
            "fallback_from": None,
        }
        if seat.brain is not None and router is not None:
            try:
                described = router.describe(seat.brain)
            except Exception:  # noqa: BLE001 - a roster must never break a page
                described = None
            if described:
                entry["provider"] = described.get("provider")
                entry["model"] = described.get("model")
                entry["fallback_from"] = described.get("fallback_from")
        seats.append(entry)

    distinct = sorted({str(s["provider"]) for s in seats if s["provider"]})
    return {
        "seats": seats,
        "providers": distinct,
        "baseline_minutes_total": BASELINE_MINUTES_TOTAL,
        "analyst_hourly_rm": DEFAULT_ANALYST_HOURLY_RM,
        "stage_baseline_minutes": {
            stage_id: minutes for stage_id, (_f, _t, minutes) in STAGE_ROLES.items()
        },
    }
