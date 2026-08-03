"""Axiom — the governed natural-language operating agent.

Axiom is deliberately not a general-purpose chat completion sitting next to the
bank. It is a constrained planner over named CaseZero capabilities. Natural
language selects an action; code resolves its scope, role, confirmation and gate.
Write actions are planned first and then re-planned server-side at execution, so
editing a browser payload cannot turn navigation into an administrative write.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from api.agents.firewall import scan

Action = Literal[
    "HELP",
    "SUMMARISE_OPERATIONS",
    "SHOW_SLA_RISK",
    "OPEN_REVIEW",
    "OPEN_POLICY",
    "OPEN_SETTINGS",
    "OPEN_QUARANTINE",
    "OPEN_CASE",
    "VERIFY_CHAIN",
    "INVITE_OPERATOR",
    "UPDATE_SETTING",
    "REFUSED",
]

CASE_REF = re.compile(r"\bMYB-\d{4}-\d{6}\b", re.I)
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
ROLES = ("OPS", "INVESTIGATOR", "COMPLIANCE", "ADMIN")


@dataclass(frozen=True)
class WajarPlan:
    plan_id: str
    action: Action
    title: str
    summary: str
    effect: str
    authority: str
    confirmation_required: bool
    permitted: bool
    route: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    gates: tuple[str, ...] = ()
    result: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["gates"] = list(self.gates)
        return payload


def _plan_id(command: str, role: str, action: str) -> str:
    material = f"{role}|{action}|{' '.join(command.lower().split())}"
    return "AXP-" + hashlib.sha256(material.encode()).hexdigest()[:12].upper()


def _make(
    command: str,
    role: str,
    action: Action,
    *,
    title: str,
    summary: str,
    effect: str,
    authority: str = "Any signed-in operator",
    confirmation_required: bool = False,
    permitted: bool = True,
    route: str | None = None,
    parameters: dict[str, Any] | None = None,
    gates: tuple[str, ...] = (),
    result: dict[str, Any] | None = None,
) -> WajarPlan:
    return WajarPlan(
        plan_id=_plan_id(command, role, action),
        action=action,
        title=title,
        summary=summary,
        effect=effect,
        authority=authority,
        confirmation_required=confirmation_required,
        permitted=permitted,
        route=route,
        parameters=parameters or {},
        gates=gates,
        result=result or {},
    )


def _safe_cases(db: Any) -> list[dict[str, Any]]:
    return list(db.list_cases(limit=500))


def _operations_result(cases: list[dict[str, Any]]) -> dict[str, Any]:
    terminal = {"COMMUNICATED", "CLOSED", "QUARANTINED"}
    attention = {"VERIFIED", "REVIEW_PENDING", "QUARANTINED"}
    by_status: dict[str, int] = {}
    for case in cases:
        status = str(case.get("status") or "UNKNOWN")
        by_status[status] = by_status.get(status, 0) + 1
    return {
        "total": len(cases),
        "open": sum(str(case.get("status")) not in terminal for case in cases),
        "needs_attention": sum(str(case.get("status")) in attention for case in cases),
        "communicated": sum(str(case.get("status")) in {"COMMUNICATED", "CLOSED"} for case in cases),
        "by_status": by_status,
    }


def _risk_result(cases: list[dict[str, Any]], warning_hours: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=warning_hours)
    at_risk: list[dict[str, Any]] = []
    terminal = {"COMMUNICATED", "CLOSED", "QUARANTINED"}
    for case in cases:
        if str(case.get("status")) in terminal:
            continue
        raw_due = case.get("sla_due")
        if not raw_due:
            continue
        try:
            due = datetime.fromisoformat(str(raw_due).replace("Z", "+00:00"))
            due = due if due.tzinfo else due.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if due <= horizon:
            at_risk.append(
                {
                    "case_ref": case.get("case_ref"),
                    "status": case.get("status"),
                    "urgency": case.get("urgency"),
                    "due": due.isoformat(),
                    "breached": due < now,
                }
            )
    at_risk.sort(key=lambda row: str(row["due"]))
    return {"warning_hours": warning_hours, "count": len(at_risk), "cases": at_risk[:20]}


def _setting_request(command: str) -> tuple[str, Any] | None:
    lower = command.lower().strip()
    number = re.search(r"(?:sla|deadline)[^\d]{0,30}(\d{1,3})\s*(?:hour|hours|hr|hrs)", lower)
    if number:
        return "sla_warning_hours", int(number.group(1))
    if re.search(r"(?:automatic|auto)[ -]?resolution", lower):
        if re.search(r"\b(off|disable|disabled|stop)\b", lower):
            return "automatic_resolution_enabled", False
        if re.search(r"\b(on|enable|enabled|start)\b", lower):
            return "automatic_resolution_enabled", True
    if "axiom" in lower or "wajar" in lower:  # legacy command name remains accepted
        if re.search(r"\b(off|disable|disabled)\b", lower):
            return "wajar_enabled", False
        if re.search(r"\b(on|enable|enabled)\b", lower):
            return "wajar_enabled", True
    workspace = re.search(r"default (?:workspace|view|page)[^a-z]+(simple|pro)\b", lower)
    if workspace:
        return "default_workspace", f"/{workspace.group(1)}"
    found_email = EMAIL.search(command)
    if found_email and any(word in lower for word in ("complaint", "inbox", "email")):
        return "complaints_email", found_email.group(0).lower()
    bank = re.search(r"(?:bank (?:display )?name|organisation name|organization name)\s+(?:to|as)\s+(.+)$", command, re.I)
    if bank:
        return "bank_display_name", bank.group(1).strip(" .")
    return None


def plan(command: str, role: str, db: Any) -> WajarPlan:
    """Translate one command into a closed, inspectable capability plan."""
    cleaned = " ".join(command.strip().split())
    if not cleaned:
        return _make(
            command,
            role,
            "HELP",
            title="What should Axiom do?",
            summary="Ask for the operating summary, cases at SLA risk, a case chain check, navigation, an operator invitation, or an administrative control change.",
            effect="No action has been selected.",
        )

    verdict = scan(cleaned)
    if verdict.hostile:
        return _make(
            cleaned,
            role,
            "REFUSED",
            title="Command refused",
            summary="The deterministic instruction firewall found an attempt to override controls or invoke protected tools.",
            effect="Nothing was read, changed, or sent.",
            authority="Instruction firewall",
            permitted=False,
            gates=("Pre-model injection firewall", "No capability selected"),
            result={"detectors": list(verdict.detectors)},
        )

    lower = cleaned.lower()
    controls = db.get_stakeholder_settings()
    if not controls.get("wajar_enabled", True):
        return _make(
            cleaned,
            role,
            "REFUSED",
            title="Axiom is paused",
            summary="An administrator disabled the operating agent in the control register.",
            effect="Nothing was read or changed. An Admin can re-enable Axiom in Settings.",
            authority="Admin control register",
            permitted=False,
            route="/settings",
            gates=("stakeholder_settings.wajar_enabled = false",),
        )

    setting = _setting_request(cleaned)
    if setting:
        key, value = setting
        valid = not (key == "sla_warning_hours" and not 1 <= int(value) <= 120)
        permitted = role == "ADMIN" and valid
        return _make(
            cleaned,
            role,
            "UPDATE_SETTING",
            title="Change an operating control",
            summary=f"Set {key.replace('_', ' ')} to {value!s}.",
            effect="The singleton control register changes and a hash-chained settings event is appended.",
            authority="Admin only",
            confirmation_required=True,
            permitted=permitted,
            route="/settings",
            parameters={"key": key, "value": value},
            gates=("Admin role", "Explicit confirmation", "Server-side value validation", "Hash-chained settings event"),
            result={} if valid else {"error": "SLA warning must be between 1 and 120 hours."},
        )

    if "invite" in lower or "add operator" in lower or "add colleague" in lower:
        email = EMAIL.search(cleaned)
        role_match = re.search(r"\b(OPS|INVESTIGATOR|COMPLIANCE|ADMIN)\b", cleaned, re.I)
        role_value = role_match.group(1).upper() if role_match else "OPS"
        name = re.sub(r"\b(?:invite|add operator|add colleague)\b", "", cleaned, flags=re.I)
        if email:
            name = name.replace(email.group(0), "")
        name = re.sub(r"\b(?:at|as|with role)\b", " ", name, flags=re.I)
        name = re.sub(r"\b(?:OPS|INVESTIGATOR|COMPLIANCE|ADMIN)\b", "", name, flags=re.I)
        name = " ".join(name.strip(" ,.-").split())
        complete = bool(email and len(name) >= 2 and role_value in ROLES)
        return _make(
            cleaned,
            role,
            "INVITE_OPERATOR",
            title="Invite a bank operator",
            summary=(f"Invite {name} at {email.group(0).lower()} as {role_value}." if complete else "An invitation needs a full name, work email, and CaseZero role."),
            effect="Supabase sends one single-use invitation email and the assigned role is written to app_users.",
            authority="Admin only",
            confirmation_required=True,
            permitted=role == "ADMIN" and complete,
            route="/admin/users",
            parameters={"full_name": name, "email": email.group(0).lower() if email else None, "role": role_value},
            gates=("Admin role", "Explicit confirmation", "Unique work email", "Supabase single-use invitation"),
        )

    case_ref_match = CASE_REF.search(cleaned)
    case_ref = case_ref_match.group(0).upper() if case_ref_match else None
    if case_ref and any(word in lower for word in ("verify", "audit", "chain", "integrity")):
        case = db.get_case_by_ref(case_ref)
        if case is None:
            result = {"found": False, "case_ref": case_ref}
        else:
            verdict = db.verify_case_chain(str(case["id"]))
            result = {
                "found": True,
                "case_ref": case_ref,
                "ok": verdict.ok,
                "first_bad_seq": verdict.first_bad_seq,
                "reason": verdict.reason,
                "links": len(db.get_events(str(case["id"]))),
            }
        return _make(
            cleaned,
            role,
            "VERIFY_CHAIN",
            title=f"Verify {case_ref}",
            summary="Recompute every link from canonical event payloads and locate the first mismatch.",
            effect="Read-only integrity check; no case data changes.",
            route=f"/case/{case_ref}",
            parameters={"case_ref": case_ref},
            gates=("RLS-visible case", "SHA-256 chain recomputation"),
            result=result,
        )
    if case_ref:
        return _make(
            cleaned,
            role,
            "OPEN_CASE",
            title=f"Open {case_ref}",
            summary="Open the evidence, events, journal and customer-communication record for this case.",
            effect="Navigate only; no case data changes.",
            route=f"/case/{case_ref}",
            parameters={"case_ref": case_ref},
            gates=("RLS-visible case",),
        )

    if any(phrase in lower for phrase in ("sla risk", "at risk", "deadline", "breach")):
        warning_hours = int(controls.get("sla_warning_hours") or 24)
        result = _risk_result(_safe_cases(db), warning_hours)
        return _make(
            cleaned,
            role,
            "SHOW_SLA_RISK",
            title="Cases approaching deadline",
            summary=f"Check open cases due within the configured {warning_hours}-hour warning horizon.",
            effect="Read-only prioritisation; no case data changes.",
            route="/simple",
            gates=("RLS-visible cases", f"Control register warning horizon = {warning_hours} hours"),
            result=result,
        )
    if any(phrase in lower for phrase in ("summarise", "summarize", "today", "operations", "how are we doing")):
        result = _operations_result(_safe_cases(db))
        return _make(
            cleaned,
            role,
            "SUMMARISE_OPERATIONS",
            title="Operations summary",
            summary=f"{result['total']} cases are visible; {result['needs_attention']} need attention and {result['communicated']} are communicated.",
            effect="Read-only aggregation; no customer content is sent to a model.",
            route="/pro",
            gates=("RLS-visible cases", "PII-free deterministic aggregation"),
            result=result,
        )

    navigation = (
        (("review", "queue"), "OPEN_REVIEW", "Open the review queue", "/review"),
        (("policy", "rule"), "OPEN_POLICY", "Open Policy Studio", "/policy"),
        (("setting", "control register"), "OPEN_SETTINGS", "Open Settings", "/settings"),
        (("quarantine", "hostile"), "OPEN_QUARANTINE", "Open Quarantine", "/quarantine"),
    )
    for terms, action, title, route in navigation:
        if any(term in lower for term in terms):
            return _make(
                cleaned,
                role,
                action,  # type: ignore[arg-type]
                title=title,
                summary=f"Take the operator to {title.lower()}.",
                effect="Navigate only; no customer or policy data changes.",
                route=route,
                gates=("Signed-in operator",),
            )

    return _make(
        cleaned,
        role,
        "HELP",
        title="I can prepare a governed action",
        summary="Try “summarise operations”, “show cases at SLA risk”, “verify MYB-2026-000012”, “open review”, or an Admin command such as “set SLA warning to 12 hours”.",
        effect="No capability matched, so nothing was read or changed.",
        gates=("Closed action registry",),
    )


def receipt_payload(
    command: str,
    role: str,
    action: str,
    parameters: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    command_hash = hashlib.sha256(command.strip().encode()).hexdigest()
    material = json.dumps(
        {"command_hash": command_hash, "role": role, "action": action, "parameters": parameters, "result": result},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    receipt_id = "AXR-" + hashlib.sha256(material.encode()).hexdigest()[:16].upper()
    return {"receipt_id": receipt_id, "command_hash": command_hash}
