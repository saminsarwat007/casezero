"""Turn recorded chain events into what each agent said to the next one.

Nothing here calls a model. Every sentence is assembled in code from a payload
that is already on the hash chain, which is the only reason the boardroom view is
allowed to exist: it is the audit trail rendered as speech, not a narration
running alongside it. If a stage has no event, it has no line — the UI shows the
seat waiting rather than inventing a plausible thing for it to have said.

This is also why the model's own words are never quoted as system truth. The
classifier's `reasoning` is the one field an LLM wrote, and it is rendered as a
quoted aside attributed to the model, not as a statement of fact.
"""

from __future__ import annotations

from typing import Any

from api.agents.roster import PIPELINE_STAGES, STAGE_ROLES, baseline_minutes

CATEGORY_LABELS: dict[str, str] = {
    "unauthorized_transaction": "an unauthorised transaction",
    "billing_error": "a billing error",
    "mis_selling": "mis-selling",
    "atm_debit_card": "an ATM or debit card dispute",
    "insurance_takaful": "an insurance or takaful claim",
    "loan_financing": "a loan or financing dispute",
    "emoney_digital": "an e-money or digital payment dispute",
}

LANGUAGE_LABELS: dict[str, str] = {"en": "English", "ms": "Malay"}

GATE_LABELS: dict[str, str] = {
    "POST": "Approved for automatic resolution",
    "MANUAL_REVIEW": "Held for a human decision",
    "DENY": "Refused",
}


def _money(value: Any) -> str:
    try:
        return f"RM{float(value):,.2f}"
    except (TypeError, ValueError):
        return "an unstated amount"


def _fact(label: str, value: Any) -> dict[str, str]:
    return {"label": label, "value": str(value)}


def _intake_line(payload: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    language = LANGUAGE_LABELS.get(str(payload.get("language") or "en"), "English")
    documents = payload.get("documents") or []
    amount = payload.get("amount_rm")
    merchant = str(payload.get("merchant") or "").strip()

    parts = [f"Clean. {language} complaint"]
    if amount is not None:
        parts.append(f"claiming {_money(amount)}")
    if merchant:
        parts.append(f"against {merchant}")
    says = ", ".join(parts) + "."
    if documents:
        methods = sorted({str(doc.get("method") or "text") for doc in documents})
        says += f" {len(documents)} attachment read by {', '.join(methods)}."
    says += " Account number encrypted before anything read it."

    facts = [
        _fact("Account", payload.get("account_no_masked") or "not quoted"),
        _fact("Amount", _money(amount) if amount is not None else "not stated"),
        _fact("Language", language),
        _fact("Attachments", len(documents)),
    ]
    return says, facts


def _classify_line(payload: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    category = str(payload.get("category") or "")
    label = CATEGORY_LABELS.get(category, category or "an unclassified complaint")
    confidence = float(payload.get("confidence") or 0)
    source = str(payload.get("source") or "model")

    says = f"This is {label}. I am {confidence:.0%} confident."
    if source == "keyword_fallback":
        says += " The model was unavailable, so this is a keyword match — treat it as weaker."

    facts = [
        _fact("Category", category or "—"),
        _fact("Confidence", f"{confidence:.0%}"),
        _fact("Decided by", "keyword fallback" if source != "model" else "language model"),
    ]
    reasoning = str(payload.get("reasoning") or "").strip()
    if reasoning:
        facts.append(_fact("Model's reasoning", reasoning))
    return says, facts


def _sla_line(payload: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    urgency = str(payload.get("urgency") or "—")
    days = payload.get("sla_working_days")
    due = str(payload.get("sla_due") or "")[:10]
    because = str(payload.get("because") or "").strip()

    says = f"{urgency} priority. {days} working days under the BNM window, due {due}."
    if because:
        says += f" {because}"

    facts = [
        _fact("Urgency", urgency),
        _fact("Working days", days if days is not None else "—"),
        _fact("Deadline", due or "—"),
    ]
    citations = payload.get("citations") or []
    if citations:
        facts.append(_fact("Rule", str(citations[0])))
    return says, facts


def _verify_line(payload: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    result = str(payload.get("result") or "—")
    evidence = payload.get("evidence") or []
    reasons = payload.get("reasons") or []
    tool_calls = payload.get("tool_calls") or []

    verdict = {
        "PASS": "Core banking confirms the claim",
        "FAIL": "Core banking contradicts the claim",
        "MANUAL_REVIEW": "Core banking cannot settle this",
    }.get(result, f"Core banking returned {result}")

    says = f"{verdict}. {len(evidence)} checks against the ledger."
    if reasons:
        says += f" {reasons[0]}"

    facts = [
        _fact("Verification", result),
        _fact("Evidence checks", len(evidence)),
        _fact("Bank tool calls", len(tool_calls)),
        _fact("Model calls", "none — this seat compares records, it does not reason"),
    ]
    return says, facts


def _gate_line(payload: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    action = str(payload.get("action") or "—")
    reasons = payload.get("reasons") or []
    inputs = payload.get("inputs") or {}
    dual = bool(payload.get("requires_dual_control"))

    says = GATE_LABELS.get(action, action) + "."
    if reasons:
        says += f" {reasons[0]}"
    if dual:
        says += " Two different approvers are required."

    facts = [
        _fact("Ruling", action),
        _fact("Verification input", inputs.get("verification_result") or "—"),
        _fact("Amount", _money(inputs.get("amount_rm"))),
        _fact("Dual control", "required" if dual else "not required"),
    ]
    citations = payload.get("citations") or []
    if citations:
        facts.append(_fact("Policy", str(citations[0])))
    return says, facts


def _journal_line(payload: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    amount = payload.get("amount_rm")
    entry_type = str(payload.get("entry_type") or "adjustment")
    balanced = bool(payload.get("balanced"))

    says = (
        f"{_money(amount)} {entry_type.lower()} posted. "
        f"Debit {payload.get('debit_account') or '—'}, "
        f"credit {payload.get('credit_account_masked') or '—'}."
    )
    says += " Books balance." if balanced else " The entry does not balance — flagged."

    facts = [
        _fact("Entry type", entry_type),
        _fact("Amount", _money(amount)),
        _fact("Balanced", "yes" if balanced else "no"),
        _fact("Authorised by", payload.get("authorised_by") or "signed kernel ticket"),
    ]
    return says, facts


def _communicate_line(payload: dict[str, Any], linted: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    outcome = str(payload.get("outcome") or "—")
    summary = str(linted.get("summary") or "").strip()
    findings = linted.get("findings") or []

    says = "Letter written and sent."
    if summary:
        says += f" Compliance lint {summary}."
    says += " The regulatory wording is inserted by the kernel, not by me."

    facts = [
        _fact("Outcome", outcome),
        _fact("Compliance checks", len(findings) or "—"),
        _fact("Letter length", f"{payload.get('chars') or 0} characters"),
        _fact("Repaired by kernel", "yes" if linted.get("repaired") else "no"),
    ]
    return says, facts


def _quarantine_line(payload: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    reason = str(payload.get("reason") or "The input carried an injected instruction.")
    return (
        f"Refused. {reason} I stopped before any model read this, so nothing "
        f"downstream ever saw it.",
        [
            _fact("Outcome", "QUARANTINED"),
            _fact("Model calls", "zero — the block happens before the first one"),
        ],
    )


def build_handoffs(recorded: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per pipeline stage, in order, each speaking only from its event.

    `recorded` maps event_type -> the event row. A stage whose event is absent
    returns `spoken: False` and no line at all.
    """
    quarantined = any(
        str((event.get("payload") or {}).get("to", "")) == "QUARANTINED"
        for event in recorded.values()
    )
    linted = (recorded.get("DRAFT_LINTED") or {}).get("payload") or {}

    builders = {
        "intake": lambda p: _intake_line(p),
        "classify": lambda p: _classify_line(p),
        "sla": lambda p: _sla_line(p),
        "verify": lambda p: _verify_line(p),
        "gate": lambda p: _gate_line(p),
        "journal": lambda p: _journal_line(p),
        "communicate": lambda p: _communicate_line(p, linted),
    }

    handoffs: list[dict[str, Any]] = []
    for stage_id, label, event_type, _agent in PIPELINE_STAGES:
        speaker, listener, _minutes = STAGE_ROLES.get(stage_id, ("kernel", "kernel", 0))
        event = recorded.get(event_type)
        entry: dict[str, Any] = {
            "stage": stage_id,
            "label": label,
            "event_type": event_type,
            "from": speaker,
            "to": listener,
            "spoken": event is not None,
            "says": "",
            "facts": [],
            "seq": (event or {}).get("seq"),
            "hash": (event or {}).get("hash"),
            "recorded_at": (event or {}).get("created_at"),
            "baseline_minutes": baseline_minutes(stage_id),
        }
        if event is not None:
            says, facts = builders[stage_id](event.get("payload") or {})
            entry["says"] = says
            entry["facts"] = facts
        elif stage_id == "intake" and quarantined:
            # The firewall stopped this before intake could report a clean read.
            # A refusal is an outcome, so it gets a line rather than silence.
            status = recorded.get("STATUS_CHANGED") or {}
            says, facts = _quarantine_line(status.get("payload") or {})
            entry.update({"spoken": True, "says": says, "facts": facts, "refused": True})
        handoffs.append(entry)

    return handoffs


def build_value(
    handoffs: list[dict[str, Any]],
    *,
    elapsed_seconds: float | None,
    baseline_total: int,
) -> dict[str, Any]:
    """Measured elapsed time against the brief's manual baseline.

    `baseline_minutes_realised` counts only the stages that actually ran, so a
    case that stopped at review does not claim the savings of the two stages it
    never reached.
    """
    realised = sum(int(h["baseline_minutes"]) for h in handoffs if h.get("spoken"))
    seconds = float(elapsed_seconds or 0)
    saved = max(realised - seconds / 60, 0.0)
    return {
        "baseline_minutes_total": baseline_total,
        "baseline_minutes_realised": realised,
        "elapsed_seconds": round(seconds, 2),
        "minutes_saved": round(saved, 1),
        "stages_spoken": sum(1 for h in handoffs if h.get("spoken")),
        "stages_total": len(handoffs),
    }
