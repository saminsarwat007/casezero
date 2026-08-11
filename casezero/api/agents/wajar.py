"""Axiom — the governed natural-language operating agent.

Axiom is deliberately not a general-purpose chat completion sitting next to the
bank. It is a constrained planner over named CaseZero capabilities. Natural
language selects an action; code resolves its scope, role, confirmation and gate.
Write actions are planned first and then re-planned server-side at execution, so
editing a browser payload cannot turn navigation into an administrative write.

Two layers, and the split matters:

* **Understanding is a model problem.** `resolve_intent` asks the deployed LLM to
  map free-form English or Malay onto one action from a closed registry. This is
  why an operator can say "which complaints will blow their deadline this week"
  without knowing that the internal capability is called `SHOW_SLA_RISK`.
* **Authority is not.** Every plan is still assembled by `_make`, which decides
  role, confirmation and gates from code. The model chooses a *label*; it never
  chooses whether an operator may act on it. A model that returned
  `UPDATE_SETTING` for a non-Admin still yields `permitted=False`.

The deterministic matcher runs first and answers most commands with zero tokens
and zero latency. The model is the fallback for phrasing, not the primary path.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

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
    #: Plain-language answer shown in the conversation. Written by the model when
    #: one was consulted, and by code otherwise. Never load-bearing.
    reply: str = ""
    #: "deterministic" or "model" — shown in the UI so an operator always knows
    #: whether a language model was involved in reading their request.
    understood_by: str = "deterministic"

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["gates"] = list(self.gates)
        payload["reply"] = self.reply or self.summary
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
    reply: str = "",
    understood_by: str = "deterministic",
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
        reply=reply,
        understood_by=understood_by,
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


def _invite_parameters(cleaned: str) -> dict[str, Any]:
    """Pull a name, work email and role out of an invitation request."""
    email = EMAIL.search(cleaned)
    role_match = re.search(r"\b(OPS|INVESTIGATOR|COMPLIANCE|ADMIN)\b", cleaned, re.I)
    role_value = role_match.group(1).upper() if role_match else "OPS"
    name = re.sub(r"\b(?:invite|add operator|add colleague)\b", "", cleaned, flags=re.I)
    if email:
        name = name.replace(email.group(0), "")
    name = re.sub(r"\b(?:at|as|with role)\b", " ", name, flags=re.I)
    name = re.sub(r"\b(?:OPS|INVESTIGATOR|COMPLIANCE|ADMIN)\b", "", name, flags=re.I)
    name = " ".join(name.strip(" ,.-").split())
    return {
        "full_name": name,
        "email": email.group(0).lower() if email else None,
        "role": role_value,
    }


def detect(cleaned: str) -> tuple[Action, dict[str, Any]] | None:
    """Deterministic intent match. Returns None when only a model can read this.

    Runs before any model call, so the common commands cost nothing and cannot
    drift with a prompt change.
    """
    lower = cleaned.lower()

    setting = _setting_request(cleaned)
    if setting:
        key, value = setting
        return "UPDATE_SETTING", {"key": key, "value": value}

    if "invite" in lower or "add operator" in lower or "add colleague" in lower:
        return "INVITE_OPERATOR", _invite_parameters(cleaned)

    case_ref_match = CASE_REF.search(cleaned)
    if case_ref_match:
        case_ref = case_ref_match.group(0).upper()
        if any(word in lower for word in ("verify", "audit", "chain", "integrity")):
            return "VERIFY_CHAIN", {"case_ref": case_ref}
        return "OPEN_CASE", {"case_ref": case_ref}

    if any(phrase in lower for phrase in ("sla risk", "at risk", "deadline", "breach")):
        return "SHOW_SLA_RISK", {}
    if any(
        phrase in lower
        for phrase in ("summarise", "summarize", "today", "operations", "how are we doing")
    ):
        return "SUMMARISE_OPERATIONS", {}

    for terms, action in (
        (("review", "queue"), "OPEN_REVIEW"),
        (("policy", "rule"), "OPEN_POLICY"),
        (("setting", "control register"), "OPEN_SETTINGS"),
        (("quarantine", "hostile"), "OPEN_QUARANTINE"),
    ):
        if any(term in lower for term in terms):
            return action, {}  # type: ignore[return-value]

    return None


NAVIGATION_TARGETS: dict[str, tuple[str, str]] = {
    "OPEN_REVIEW": ("Open the review queue", "/review"),
    "OPEN_POLICY": ("Open rules and policies", "/policy"),
    "OPEN_SETTINGS": ("Open settings", "/settings"),
    "OPEN_QUARANTINE": ("Open blocked intake", "/quarantine"),
}


def build(
    cleaned: str,
    role: str,
    db: Any,
    action: Action,
    parameters: dict[str, Any],
    *,
    controls: dict[str, Any],
    reply: str = "",
    understood_by: str = "deterministic",
) -> WajarPlan:
    """Assemble the plan for one action. All authority is decided here, in code.

    Whether the action label came from a regex or from a language model makes no
    difference below this line, which is the point: the model cannot widen its own
    permissions by phrasing a request differently.
    """
    common = {"reply": reply, "understood_by": understood_by}

    if action == "UPDATE_SETTING":
        key = str(parameters.get("key") or "")
        value = parameters.get("value")
        valid = key in SETTABLE_CONTROLS and not (
            key == "sla_warning_hours" and not (isinstance(value, int) and 1 <= value <= 120)
        )
        return _make(
            cleaned,
            role,
            "UPDATE_SETTING",
            title="Change an operating control",
            summary=f"Set {key.replace('_', ' ')} to {value!s}.",
            effect="The singleton control register changes and a hash-chained settings event is appended.",
            authority="Admin only",
            confirmation_required=True,
            permitted=role == "ADMIN" and valid,
            route="/settings",
            parameters={"key": key, "value": value},
            gates=(
                "Admin role",
                "Explicit confirmation",
                "Server-side value validation",
                "Hash-chained settings event",
            ),
            result={} if valid else {"error": "That control or value is not accepted."},
            **common,
        )

    if action == "INVITE_OPERATOR":
        email = parameters.get("email")
        name = str(parameters.get("full_name") or "")
        role_value = str(parameters.get("role") or "OPS").upper()
        complete = bool(email and len(name) >= 2 and role_value in ROLES)
        return _make(
            cleaned,
            role,
            "INVITE_OPERATOR",
            title="Invite a bank operator",
            summary=(
                f"Invite {name} at {email} as {role_value}."
                if complete
                else "An invitation needs a full name, work email, and CaseZero role."
            ),
            effect="Supabase sends one single-use invitation email and the assigned role is written to app_users.",
            authority="Admin only",
            confirmation_required=True,
            permitted=role == "ADMIN" and complete,
            route="/admin/users",
            parameters={"full_name": name, "email": email, "role": role_value},
            gates=(
                "Admin role",
                "Explicit confirmation",
                "Unique work email",
                "Supabase single-use invitation",
            ),
            **common,
        )

    if action == "VERIFY_CHAIN":
        case_ref = str(parameters.get("case_ref") or "").upper()
        case = db.get_case_by_ref(case_ref) if case_ref else None
        if case is None:
            result: dict[str, Any] = {"found": False, "case_ref": case_ref}
        else:
            chain = db.verify_case_chain(str(case["id"]))
            result = {
                "found": True,
                "case_ref": case_ref,
                "ok": chain.ok,
                "first_bad_seq": chain.first_bad_seq,
                "reason": chain.reason,
                "links": len(db.get_events(str(case["id"]))),
            }
        return _make(
            cleaned,
            role,
            "VERIFY_CHAIN",
            title=f"Verify {case_ref}" if case_ref else "Verify a case chain",
            summary="Recompute every link from canonical event payloads and locate the first mismatch.",
            effect="Read-only integrity check; no case data changes.",
            route=f"/case/{case_ref}" if case_ref else "/audit",
            parameters={"case_ref": case_ref},
            gates=("RLS-visible case", "SHA-256 chain recomputation"),
            result=result,
            **common,
        )

    if action == "OPEN_CASE":
        case_ref = str(parameters.get("case_ref") or "").upper()
        return _make(
            cleaned,
            role,
            "OPEN_CASE",
            title=f"Open {case_ref}" if case_ref else "Open a case",
            summary="Open the evidence, events, journal and customer-communication record for this case.",
            effect="Navigate only; no case data changes.",
            route=f"/case/{case_ref}" if case_ref else "/simple",
            parameters={"case_ref": case_ref},
            gates=("RLS-visible case",),
            **common,
        )

    if action == "SHOW_SLA_RISK":
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
            gates=(
                "RLS-visible cases",
                f"Control register warning horizon = {warning_hours} hours",
            ),
            result=result,
            **common,
        )

    if action == "SUMMARISE_OPERATIONS":
        result = _operations_result(_safe_cases(db))
        return _make(
            cleaned,
            role,
            "SUMMARISE_OPERATIONS",
            title="Operations summary",
            summary=(
                f"{result['total']} cases are visible; {result['needs_attention']} need "
                f"attention and {result['communicated']} are communicated."
            ),
            effect="Read-only aggregation; no customer content is sent to a model.",
            route="/pro",
            gates=("RLS-visible cases", "PII-free deterministic aggregation"),
            result=result,
            **common,
        )

    if action in NAVIGATION_TARGETS:
        title, route = NAVIGATION_TARGETS[action]
        return _make(
            cleaned,
            role,
            action,
            title=title,
            summary=f"Take the operator to {title.lower().removeprefix('open ')}.",
            effect="Navigate only; no customer or policy data changes.",
            route=route,
            gates=("Signed-in operator",),
            **common,
        )

    return _make(
        cleaned,
        role,
        "HELP",
        title="I can prepare a governed action",
        summary=HELP_SUMMARY,
        effect="No capability matched, so nothing was read or changed.",
        gates=("Closed action registry",),
        **common,
    )


HELP_SUMMARY = (
    "Try “summarise operations”, “show cases at SLA risk”, “verify MYB-2026-000012”, "
    "“open review”, or an Admin command such as “set SLA warning to 12 hours”."
)

SETTABLE_CONTROLS = (
    "bank_display_name",
    "complaints_email",
    "sla_warning_hours",
    "default_workspace",
    "wajar_enabled",
    "automatic_resolution_enabled",
)


class ResolvedIntent(BaseModel):
    """What the model is allowed to return: one closed label, plus a sentence."""

    action: str = Field(description="One action name from the provided registry.")
    case_ref: str = ""
    setting_key: str = ""
    setting_value: str = ""
    invite_email: str = ""
    invite_name: str = ""
    invite_role: str = ""
    reply: str = Field(default="", description="One or two sentences for the operator.")


INTENT_SYSTEM = """You are Axiom, the operations assistant inside CaseZero, a governed
banking-complaint system for a Malaysian bank. You do not execute anything. You only
choose which named capability the operator is asking for, and write one short reply.

Choose exactly one action:
SUMMARISE_OPERATIONS  - how the queue is doing right now, counts, workload, throughput
SHOW_SLA_RISK         - complaints near or past a regulatory deadline
OPEN_CASE             - look at one specific case (needs case_ref like MYB-2026-000012)
VERIFY_CHAIN          - check the audit chain / tamper evidence of one case
OPEN_REVIEW           - the human review queue
OPEN_POLICY           - category rules, thresholds, policy packs
OPEN_SETTINGS         - operating controls, bank name, automation switch
OPEN_QUARANTINE       - complaints blocked by the prompt-injection firewall
INVITE_OPERATOR       - add a colleague (needs invite_email; invite_role in OPS,
                        INVESTIGATOR, COMPLIANCE, ADMIN)
UPDATE_SETTING        - change one control. setting_key must be one of:
                        sla_warning_hours, automatic_resolution_enabled, wajar_enabled,
                        default_workspace, complaints_email, bank_display_name
HELP                  - the request is unclear or outside these capabilities

Rules:
- Never invent a case reference, an email address, or a numeric value. Leave the field
  empty if the operator did not say it.
- Never claim you performed an action. Authority is decided after you answer.
- Malay and English are both expected. Reply in the language the operator used.
- Keep `reply` under 220 characters, factual, no emoji, no promises.
Return JSON only."""


async def resolve_intent(cleaned: str, ctx: Any) -> ResolvedIntent | None:
    """Ask the deployed model which capability this phrasing means.

    Returns None when no model is attached or the call fails, so Axiom degrades to
    the deterministic matcher instead of going silent.
    """
    if ctx is None or getattr(ctx, "router", None) is None:
        return None
    try:
        result = await ctx.complete(
            "intel",
            f"Operator request:\n{cleaned}",
            system=INTENT_SYSTEM,
            schema=ResolvedIntent,
            temperature=0.0,
            max_tokens=400,
        )
    except Exception:  # noqa: BLE001 - a model outage must not break the assistant
        return None
    parsed = result.parsed
    return parsed if isinstance(parsed, ResolvedIntent) else None


def _intent_parameters(intent: ResolvedIntent) -> tuple[Action, dict[str, Any]]:
    """Coerce a model answer into a known action and validated parameters.

    Anything unrecognised collapses to HELP. A model that hallucinates an action
    name therefore gets no capability at all.
    """
    action = intent.action.strip().upper()
    known: set[str] = {
        "SUMMARISE_OPERATIONS",
        "SHOW_SLA_RISK",
        "OPEN_CASE",
        "VERIFY_CHAIN",
        "OPEN_REVIEW",
        "OPEN_POLICY",
        "OPEN_SETTINGS",
        "OPEN_QUARANTINE",
        "INVITE_OPERATOR",
        "UPDATE_SETTING",
    }
    if action not in known:
        return "HELP", {}

    if action in {"OPEN_CASE", "VERIFY_CHAIN"}:
        found = CASE_REF.search(intent.case_ref or "")
        if not found:
            return "HELP", {}
        return action, {"case_ref": found.group(0).upper()}  # type: ignore[return-value]

    if action == "UPDATE_SETTING":
        key = intent.setting_key.strip().lower()
        if key not in SETTABLE_CONTROLS:
            return "HELP", {}
        raw = intent.setting_value.strip()
        value: Any = raw
        if key == "sla_warning_hours":
            digits = re.search(r"\d{1,3}", raw)
            if not digits:
                return "HELP", {}
            value = int(digits.group(0))
        elif key in {"automatic_resolution_enabled", "wajar_enabled"}:
            value = raw.lower() in {"true", "on", "enable", "enabled", "yes", "1"}
        elif key == "default_workspace":
            if raw.lower().lstrip("/") not in {"simple", "pro"}:
                return "HELP", {}
            value = "/" + raw.lower().lstrip("/")
        elif not raw:
            return "HELP", {}
        return "UPDATE_SETTING", {"key": key, "value": value}

    if action == "INVITE_OPERATOR":
        email = EMAIL.search(intent.invite_email or "")
        role_value = intent.invite_role.strip().upper()
        return "INVITE_OPERATOR", {
            "full_name": " ".join(intent.invite_name.split())[:120],
            "email": email.group(0).lower() if email else None,
            "role": role_value if role_value in ROLES else "OPS",
        }

    return action, {}  # type: ignore[return-value]


def _preflight(command: str, role: str, db: Any) -> tuple[str, dict[str, Any]] | WajarPlan:
    """Shared guards: empty input, the injection firewall, and the kill switch."""
    cleaned = " ".join(command.strip().split())
    if not cleaned:
        return _make(
            command,
            role,
            "HELP",
            title="What should Axiom do?",
            summary=HELP_SUMMARY,
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
    return cleaned, controls


def plan(command: str, role: str, db: Any) -> WajarPlan:
    """Deterministic planning only. Used by execution re-planning and by tests."""
    guarded = _preflight(command, role, db)
    if isinstance(guarded, WajarPlan):
        return guarded
    cleaned, controls = guarded

    detected = detect(cleaned)
    action, parameters = detected if detected else ("HELP", {})
    return build(cleaned, role, db, action, parameters, controls=controls)


async def plan_with_model(command: str, role: str, db: Any, ctx: Any = None) -> WajarPlan:
    """Plan a command, consulting the model only when the fast matcher cannot read it.

    The model widens *understanding*, never authority: its answer is coerced into
    the closed registry and then handed to the same `build` used above.
    """
    guarded = _preflight(command, role, db)
    if isinstance(guarded, WajarPlan):
        return guarded
    cleaned, controls = guarded

    detected = detect(cleaned)
    if detected:
        action, parameters = detected
        return build(cleaned, role, db, action, parameters, controls=controls)

    intent = await resolve_intent(cleaned, ctx)
    if intent is None:
        return build(cleaned, role, db, "HELP", {}, controls=controls)

    action, parameters = _intent_parameters(intent)
    reply = " ".join((intent.reply or "").split())[:400]
    return build(
        cleaned,
        role,
        db,
        action,
        parameters,
        controls=controls,
        reply=reply,
        understood_by="model",
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
