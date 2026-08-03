"""Human review actions, with the same kernel gates as autonomous resolution."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from api.agents import communicator, resolver
from api.agents.base import KERNEL, AgentContext, Event
from api.kernel import gates
from api.kernel.lint import LintContext, lint_outbound
from api.security.crypto import decrypt, mask_account

ReviewAction = Literal["APPROVE", "REJECT", "REQUEST_INFO"]


def _append(db: Any, case_id: str, events: list[Event]) -> None:
    for event in events:
        db.append_event(case_id, event.type, event.actor, event.payload)


def _transition(
    db: Any,
    case: dict[str, Any],
    target: str,
    *,
    actor: str,
    reason: str,
    fields: dict[str, Any] | None = None,
) -> None:
    gates.assert_transition(
        str(case["status"]),
        target,
        verification_result=case.get("verification_result"),
    )
    previous = str(case["status"])
    db.update_case(str(case["id"]), status=target, **(fields or {}))
    case.update(status=target, **(fields or {}))
    db.append_event(
        str(case["id"]),
        "STATUS_CHANGED",
        actor,
        {"from": previous, "to": target, "reason": reason},
    )


def _due_display(case: dict[str, Any]) -> str:
    raw = case.get("sla_due")
    if not raw:
        return "the date shown in your case tracker"
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).strftime("%d %B %Y")
    except ValueError:
        return str(raw)


def _communication(
    db: Any,
    case: dict[str, Any],
    ctx: AgentContext,
    *,
    outcome: str,
    actor: str,
    reasons: list[str],
) -> str:
    pack = ctx.pack(str(case["category"]))
    lint_context = LintContext(
        case_ref=str(case["case_ref"]),
        amount_rm=float(case["amount_rm"]) if case.get("amount_rm") is not None else None,
        outcome=outcome,
        due_date_display=_due_display(case),
        language=pack.languages[0] if pack.languages else "en",
    )
    body = communicator.compose_template(
        pack,
        lint_context,
        bank_name=ctx.settings.bank_name,
        contact_email=ctx.settings.bank_complaints_email,
        reasons=reasons,
    )
    report = lint_outbound(pack, body, lint_context)
    decision = gates.authorize_send(report)
    _append(
        db,
        str(case["id"]),
        [
            Event(
                type="DRAFT_LINTED",
                actor=KERNEL,
                payload={
                    "source": "human_review_template",
                    "summary": report.summary(),
                    "repaired": report.repaired,
                    "findings": [
                        {
                            "rule_id": finding.rule_id,
                            "status": finding.status,
                            "detail": finding.detail,
                        }
                        for finding in report.findings
                    ],
                },
            ),
            Event(
                type="MESSAGE_SENT" if decision.allowed else "MESSAGE_BLOCKED",
                actor=actor if decision.allowed else KERNEL,
                payload={
                    "subject": f"Your complaint {case['case_ref']}",
                    "outcome": outcome,
                    "body": report.body,
                    "gate": "authorize_send",
                    "action": decision.action,
                    "reasons": list(decision.reasons),
                    "citations": list(decision.citations),
                },
            ),
        ],
    )
    if not decision.allowed:
        raise PermissionError(decision.explain())
    return report.body


async def decide(
    case: dict[str, Any],
    action: ReviewAction,
    ctx: AgentContext,
    *,
    user_id: str,
    dual_control_by: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    if case.get("status") != "REVIEW_PENDING":
        raise ValueError(f"Case {case.get('case_ref')} is not awaiting review.")

    db = ctx.db
    case_id = str(case["id"])
    actor = f"user:{user_id}"
    pack = ctx.pack(str(case["category"]))

    if action == "REQUEST_INFO":
        body = (
            f"We acknowledge your complaint {case['case_ref']}. We need additional "
            f"information to complete our investigation. Please reply to "
            f"{ctx.settings.bank_complaints_email}. Your current response deadline is "
            f"{_due_display(case)}.\n\n{note}".strip()
        )
        _append(
            db,
            case_id,
            [
                Event(
                    type="INFORMATION_REQUESTED",
                    actor=actor,
                    payload={"note": note, "sla_due": case.get("sla_due")},
                ),
                Event(
                    type="MESSAGE_SENT",
                    actor=actor,
                    payload={
                        "subject": f"Information needed — {case['case_ref']}",
                        "outcome": "PENDING",
                        "body": body,
                    },
                ),
            ],
        )
        return {"status": "REVIEW_PENDING", "outcome": "PENDING", "letter": body}

    if action == "REJECT":
        body = _communication(
            db,
            case,
            ctx,
            outcome="REJECTED",
            actor=actor,
            reasons=[note or "A human investigator reviewed the evidence and rejected the claim."],
        )
        _transition(
            db,
            case,
            "COMMUNICATED",
            actor=actor,
            reason="Human investigator rejected the claim and released a compliant decision.",
            fields={"outcome": "REJECTED"},
        )
        return {"status": "COMMUNICATED", "outcome": "REJECTED", "letter": body}

    decision = gates.authorize_resolution(
        pack,
        verification_result=case.get("verification_result"),
        confidence=float(case["confidence"]) if case.get("confidence") is not None else None,
        amount_rm=float(case["amount_rm"]) if case.get("amount_rm") is not None else None,
        approved_by=user_id,
        dual_control_by=dual_control_by,
    )
    db.append_event(
        case_id,
        "GATE_DECISION",
        KERNEL,
        {
            "gate": "authorize_resolution",
            "action": decision.action,
            "requires_dual_control": decision.requires_dual_control,
            "reasons": list(decision.reasons),
            "citations": list(decision.citations),
            "human_review": True,
            "approved_by": user_id,
            "dual_control_by": dual_control_by,
        },
    )
    if not decision.allowed:
        return {
            "status": "REVIEW_PENDING",
            "outcome": "PENDING",
            "requires_dual_control": decision.requires_dual_control,
            "reason": decision.explain(),
        }

    account_no = decrypt(str(case["account_no_enc"]))
    amount_rm = float(case["amount_rm"])
    entry_type = pack.journal_type
    ticket = resolver._mint(
        decision,
        case_id=case_id,
        account_no=account_no,
        amount_rm=amount_rm,
        entry_type=entry_type,
    )
    txn_ref = (case.get("txn_refs") or [None])[0]
    posting = await ctx.call_tool(
        "core-banking",
        "post_adjustment",
        case_id=case_id,
        account_no=account_no,
        entry_type=entry_type,
        debit_account=pack.debit_account,
        amount_rm=amount_rm,
        narrative=resolver.narrative(pack, case_ref=str(case["case_ref"]), txn_ref=txn_ref),
        posted_by=actor,
        authorisation=ticket,
        dual_control_by=dual_control_by,
        txn_ref=txn_ref,
    )
    db.append_event(
        case_id,
        "JOURNAL_POSTED",
        actor,
        {
            "posted": bool(posting.get("posted")),
            "entry_type": entry_type,
            "amount_rm": amount_rm,
            "debit_account": pack.debit_account,
            "credit_account_masked": mask_account(account_no),
            "balanced": bool(posting.get("balanced")),
            "authorised_by": posting.get("authorised_by_ticket"),
            "dual_control_by": dual_control_by,
            "citations": list(decision.citations),
        },
    )
    _transition(
        db,
        case,
        "FINANCIALLY_RESOLVED",
        actor=actor,
        reason=decision.explain(),
        fields={"outcome": "RESOLVED_IN_FULL", "resolved_at": datetime.now().astimezone().isoformat()},
    )
    body = _communication(
        db,
        case,
        ctx,
        outcome="RESOLVED_IN_FULL",
        actor=actor,
        reasons=list(decision.reasons),
    )
    _transition(
        db,
        case,
        "COMMUNICATED",
        actor=actor,
        reason="Human-approved resolution passed the outbound compliance gate.",
    )
    return {
        "status": "COMMUNICATED",
        "outcome": "RESOLVED_IN_FULL",
        "posted": True,
        "letter": body,
    }
