"""CaseZero FastAPI application: intake, governed review, RLS reads and SSE."""

from __future__ import annotations

# Vercel Services imports this file as top-level ``main`` from the ``api/``
# service root. Add the repository root only for that packaging mode so the
# same package-qualified imports used by pytest and Uvicorn keep working.
if __package__ in {None, ""}:
    import sys
    import types
    from pathlib import Path

    service_root = Path(__file__).resolve().parent
    package = types.ModuleType("api")
    package.__file__ = str(service_root / "__init__.py")
    package.__path__ = [str(service_root)]
    sys.modules.setdefault("api", package)

import base64
import copy
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from typing import Any, Literal

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sse_starlette.sse import EventSourceResponse

from api.agents import roster
from api.agents.base import AgentContext, build_context
from api.agents.handoff import build_handoffs, build_value
from api.agents.orchestrator import CaseRun, Orchestrator
from api.agents.wajar import plan as plan_wajar
from api.agents.wajar import plan_with_model as plan_wajar_with_model
from api.agents.wajar import receipt_payload
from api.config import get_settings
from api.corpus.labels import load_evaluation_labels
from api.db.client import Database
from api.db.invitations import (
    InvitationError,
    ROLES,
    StaffInvitationService,
    StaffInvite,
    invitation_service,
)
from api.kernel.composer import (
    ComposerError,
    candidate_from_intent,
    interpret_request,
)
from api.kernel.rules import load_yaml
from api.mcp_tools.gateway import close_gateway
from api.review import decide
from api.reports.fmos_pack import build_fmos_pack
from api.security.crypto import mask_account
from api.security.public_intake import (
    ALLOWED_ATTACHMENT_TYPES,
    ALLOWED_PERSONAS,
    MAX_ATTACHMENT_BYTES,
    MAX_AMOUNT_RM,
    MAX_BODY,
    MAX_SUBJECT,
    MIN_AMOUNT_RM,
    AdmittedComplaint,
    PublicIntakeRefused,
    admit as admit_public_complaint,
)
from api.web.auth import AuthUser, current_user, rls_database, service_database
from api.web.sse import hub


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_gateway()


app = FastAPI(
    title="CaseZero API",
    version="1.0.0",
    summary="Governed banking-dispute automation for MYBank Berhad.",
    lifespan=lifespan,
)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.dashboard_base_url, "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-WorkBuddy-Token"],
)


@app.middleware("http")
async def normalize_service_prefix(request: Request, call_next):
    """Strip the public Vercel Services prefix before FastAPI route matching."""
    path = request.scope.get("path", "")
    if path == "/api" or path.startswith("/api/"):
        normalized = path[4:] or "/"
        request.scope["path"] = normalized
        request.scope["raw_path"] = normalized.encode("utf-8")
    return await call_next(request)


def agent_context(db: Database = Depends(service_database)) -> AgentContext:
    ctx = build_context(db=db)
    try:
        controls = db.get_stakeholder_settings()
    except Exception:  # The first bootstrap can run before migration 005 exists.
        return ctx
    ctx.settings = ctx.settings.model_copy(
        update={
            "bank_name": controls.get("bank_display_name") or ctx.settings.bank_name,
            "bank_complaints_email": controls.get("complaints_email") or ctx.settings.bank_complaints_email,
        }
    )
    return ctx


def public_case(case: dict[str, Any]) -> dict[str, Any]:
    """Remove ciphertext and expose only the account suffix required by staff UI."""
    safe = {
        key: value
        for key, value in case.items()
        if key not in {"account_no_enc", "nric_enc"}
    }
    safe["account_no_masked"] = (
        f"******{case.get('account_last4')}" if case.get("account_last4") else None
    )
    return safe


def run_summary(run: CaseRun) -> dict[str, Any]:
    return {
        "case_id": run.case_id,
        "case_ref": run.case_ref,
        "status": run.status,
        "outcome": run.outcome,
        "category": run.category,
        "urgency": run.urgency,
        "confidence": run.confidence,
        "verification_result": run.verification_result,
        "amount_rm": run.amount_rm,
        "sla_due": run.sla_due,
        "posted": run.posted,
        "quarantined": run.quarantined,
        "letter": run.letter,
        "cost_rm": run.cost_rm,
        "degraded": run.degraded,
        "timeline": run.timeline(),
    }


def _public_demo_fingerprint(request: Request) -> str:
    """One-way rate key. No IP address or user agent is persisted."""
    forwarded = (
        request.headers.get("x-vercel-forwarded-for")
        or request.headers.get("x-forwarded-for")
        or (request.client.host if request.client else "unknown")
    )
    client_ip = forwarded.split(",", 1)[0].strip()
    user_agent = request.headers.get("user-agent", "unknown")[:300]
    secret = (settings.fernet_key or "casezero-unconfigured-demo-key").encode()
    material = f"public-live-demo-v1|{client_ip}|{user_agent}".encode()
    return hmac.new(secret, material, hashlib.sha256).hexdigest()


def _public_demo_email(*, txn_ref: str, posted_at: datetime) -> bytes:
    """An allow-listed test complaint; the public endpoint accepts no user PII."""
    message = EmailMessage()
    message["Subject"] = "Unauthorised card transaction"
    message["From"] = "Ahmad bin Ismail <ahmad.live@example.my>"
    message["To"] = settings.bank_complaints_email
    message["Date"] = format_datetime(posted_at)
    message.set_content(
        "Dear Complaints Team,\n\n"
        "I did not authorise the RM2,450.00 card payment to TECHWORLD KL on "
        f"account 7142556890. The transaction reference is {txn_ref}. My card "
        "has remained with me. Please investigate and reverse the charge.\n\n"
        "Thank you,\nAhmad bin Ismail\n"
    )
    return message.as_bytes()


#: The seven observable pipeline stages live in `api.agents.roster` alongside the
#: seat that speaks at each one and the manual minutes it replaces. Re-exported
#: here because the proof builder, the progress feed and existing callers all
#: read it from this module.
PIPELINE_STAGES = roster.PIPELINE_STAGES


def _event_stage(
    rows: dict[str, dict[str, Any]],
    *,
    stage_id: str,
    label: str,
    event_type: str,
    evidence: str,
    skipped: bool = False,
) -> dict[str, Any]:
    event = rows.get(event_type) or {}
    if event:
        status = "PASS"
    elif skipped:
        status = "SKIPPED"
    else:
        status = "MISSING"
    return {
        "id": stage_id,
        "label": label,
        "status": status,
        "event_type": event_type,
        "seq": event.get("seq"),
        "actor": event.get("actor"),
        "recorded_at": event.get("created_at"),
        "hash": event.get("hash"),
        "evidence": evidence,
    }


def _build_public_demo_proof(
    *,
    token: str,
    run: CaseRun,
    ctx: AgentContext,
    txn_ref: str,
    started_at: datetime,
    completed_at: datetime,
    duration_ms: int,
    model_start: int,
    tool_start: int,
) -> dict[str, Any]:
    case_id = str(run.case_id)
    event_rows = ctx.db.get_event_rows(case_id)
    by_type = {str(row["event_type"]): row for row in event_rows}
    chain = ctx.db.verify_case_chain(case_id)
    journal_rows = ctx.db.get_journal(case_id)
    model_calls = [
        {
            "agent": call.agent,
            "provider": call.provider,
            "model": call.model,
            "tokens_in": call.tokens_in,
            "tokens_out": call.tokens_out,
            "latency_ms": call.latency_ms,
            "cost_rm": round(float(call.cost_rm), 8),
            "metered": call.metered,
        }
        for call in ctx.llm_calls[model_start:]
    ]

    gateway_calls = list(getattr(ctx.gateway, "calls", []))[tool_start:]
    tool_calls = [
        {
            "server": call.server,
            "tool": call.tool,
            "transport": call.transport,
            "latency_ms": call.latency_ms,
            "ok": call.error is None,
        }
        for call in gateway_calls
    ]
    if not tool_calls:
        tool_calls = [
            {
                "server": str(call.get("server", "core-banking")),
                "tool": str(call.get("tool", "verify_claim")),
                "transport": str(call.get("transport", getattr(ctx.gateway, "transport", "unknown"))),
                "latency_ms": None,
                "ok": bool(call.get("ok")),
            }
            for call in run.tool_calls
        ]

    classified = (by_type.get("CLASSIFIED") or {}).get("payload") or {}
    urgency = (by_type.get("URGENCY_ASSIGNED") or {}).get("payload") or {}
    verified = (by_type.get("VERIFICATION_COMPLETED") or {}).get("payload") or {}
    gate = (by_type.get("GATE_DECISION") or {}).get("payload") or {}
    review = (by_type.get("REVIEW_REQUESTED") or {}).get("payload") or {}
    posted = (by_type.get("JOURNAL_POSTED") or {}).get("payload") or {}
    linted = (by_type.get("DRAFT_LINTED") or {}).get("payload") or {}
    message = (by_type.get("MESSAGE_SENT") or {}).get("payload") or {}

    gate_action = str(gate.get("action") or "—")
    gate_reasons = gate.get("reasons") or []
    gate_inputs = gate.get("inputs") or {}
    classify_source = str(classified.get("source") or "model")

    # Stage 06/07 are intentionally skipped when the gate does not say POST.
    # A stakeholder must see *why* they are missing, not just "missing".
    journal_skipped = gate_action != "POST"
    communicate_skipped = journal_skipped

    # ── Plain-English helpers for non-technical stakeholders ──────────────
    _CATEGORY_LABELS = {
        "unauthorized_transaction": "an unauthorised transaction",
        "billing_error": "a billing error",
        "mis_selling": "mis-selling of a product",
        "atm_debit_card": "an ATM or debit card problem",
        "insurance_takaful": "an insurance or takaful issue",
        "loan_financing": "a loan or financing issue",
        "emoney_digital": "an e-wallet or digital payment issue",
    }
    _VERIFY_LABELS = {
        "PASS": "confirmed the claim",
        "FAIL": "did not support the claim",
        "MANUAL_REVIEW": "could not fully confirm the claim",
    }
    _GATE_ACTION_LABELS = {
        "POST": "approved automatically",
        "MANUAL_REVIEW": "sent to a human for review",
        "DENY": "refused",
    }
    _URGENCY_LABELS = {
        "High": "high priority",
        "Medium": "medium priority",
        "Low": "low priority",
    }

    def _plain_gate_reason(reason: str) -> str:
        """Turn a technical gate reason into plain English for a stakeholder."""
        r = str(reason)
        if "below the" in r and "floor" in r:
            return "The AI was not sure enough about the category, so a human needs to decide."
        if "meets the" in r and "floor" in r:
            return "The AI was sure enough about the category."
        if "Verification returned FAIL" in r:
            return "The bank's records do not support this claim, so no money can be moved."
        if "Verification is" in r and "required" in r:
            return "The bank's records could not fully confirm the claim, so a human needs to check."
        if "Verification returned PASS" in r:
            return "The bank's records confirmed the claim."
        if "exceeds the" in r and "dual-control" in r:
            return "The amount is large enough that a second person must approve it."
        if "above the dual-control" in r:
            return "The amount is large enough that a second person must approve it."
        if "within the" in r and "auto-approval" in r:
            return "The amount is small enough to be resolved automatically."
        if "above the" in r and "auto-approve" in r:
            return "The amount is above the automatic limit, so a human must approve it."
        if "No classification confidence" in r:
            return "The AI did not provide a confidence score, so a human must decide."
        if "missing or not positive" in r:
            return "The disputed amount is missing or invalid, so the case cannot be processed automatically."
        if "Dual control requires two different people" in r:
            return "Two different people must approve this — the same person cannot approve twice."
        if "Compliance lint passed" in r:
            return "The response letter passed all compliance checks."
        if "Compliance lint" in r and "fail" in r.lower():
            return "The response letter did not pass compliance checks and needs to be fixed."
        return r

    category_label = _CATEGORY_LABELS.get(
        str(classified.get("category") or run.category or ""),
        str(classified.get("category") or run.category or "this complaint"),
    )
    verify_result = str(verified.get("result") or run.verification_result or "—")
    verify_label = _VERIFY_LABELS.get(verify_result, verify_result)
    gate_label = _GATE_ACTION_LABELS.get(gate_action, gate_action)
    urgency_label = _URGENCY_LABELS.get(
        str(urgency.get("urgency") or run.urgency or ""),
        str(urgency.get("urgency") or run.urgency or "—"),
    )
    plain_gate_reasons = ". ".join(_plain_gate_reason(r) for r in gate_reasons) if gate_reasons else ""
    confidence_pct = float(classified.get("confidence", run.confidence or 0))

    evidence_by_stage = {
        "intake": (
            "The complaint was checked for harmful or injected content before any AI read it. "
            "The customer's account number was hidden for safety."
        ),
        "classify": (
            f"The AI read the complaint and identified it as {category_label}. "
            f"It is {confidence_pct:.0%} sure about this"
            + ("." if classify_source != "keyword_fallback"
               else ", but used a simpler keyword match because the AI model was unavailable.")
        ),
        "sla": (
            f"Marked as {urgency_label}. "
            f"The bank's policy says this must be resolved within "
            f"{urgency.get('sla_working_days', '—')} working days."
        ),
        "verify": (
            f"The bank's records were checked against the claim. "
            f"The system {verify_label} by examining "
            f"{len(verified.get('evidence') or [])} pieces of evidence."
        ),
        "gate": (
            f"The system {gate_label}."
            + (f" Why: {plain_gate_reasons}." if plain_gate_reasons else "")
        ),
        "journal": (
            f"Not done — the case was sent to a human for review, so no money was moved. "
            f"A journal entry will be posted once a human approves the resolution."
            if journal_skipped else
            f"RM {float(posted.get('amount_rm') or 0):,.2f} was moved. "
            f"The debit and credit sides match, so the books are balanced."
        ),
        "communicate": (
            f"Not done — no letter is sent to the customer while the case is waiting for a human. "
            f"The customer will be contacted once a decision is made."
            if communicate_skipped else
            f"The response letter was checked for compliance and approved for sending. "
            f"The customer has been notified."
        ),
    }
    _skipped_stages = {"journal", "communicate"} if journal_skipped else set()
    stages = [
        _event_stage(
            by_type,
            stage_id=stage_id,
            label=label,
            event_type=event_type,
            evidence=evidence_by_stage[stage_id],
            skipped=stage_id in _skipped_stages,
        )
        for stage_id, label, event_type, _agent in PIPELINE_STAGES
    ]

    handoffs = build_handoffs(by_type)
    value = build_value(
        handoffs,
        elapsed_seconds=duration_ms / 1000,
        baseline_total=roster.BASELINE_MINUTES_TOTAL,
    )

    safe_journal = [
        {
            "entry_type": row.get("entry_type"),
            "debit_account": row.get("debit_account"),
            "credit_account_masked": mask_account(str(row.get("credit_account", ""))),
            "amount_rm": float(row.get("amount_rm") or 0),
            "posted_by": row.get("posted_by"),
            "posted_at": row.get("posted_at"),
        }
        for row in journal_rows
    ]
    degraded = list(run.degraded)
    completed = run.status == "COMMUNICATED" and run.posted and chain.ok
    assurance = "VERIFIED_LIVE" if completed and model_calls and not degraded else "LIVE_DEGRADED"

    return {
        "schema_version": "1.0",
        "execution": {
            "token": token,
            "case_ref": run.case_ref,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "duration_ms": duration_ms,
            "runtime": "Vercel" if os.getenv("VERCEL") else "local",
            "assurance": assurance,
            "reused": False,
            "source": "SYNTHETIC_INPUT",
            "execution_mode": "LIVE_EXECUTION",
        },
        "input": {
            "fixture": "unauthorised_transaction_v1",
            "sender": "ahmad.live@example.my",
            "subject": "Unauthorised card transaction",
            "account_no_masked": "******6890",
            "amount_rm": 2450.0,
            "merchant": "TECHWORLD KL",
            "txn_ref": txn_ref,
        },
        "result": {
            "status": run.status,
            "outcome": run.outcome,
            "verification_result": run.verification_result,
            "category": run.category,
            "urgency": run.urgency,
            "confidence": run.confidence,
            "posted": run.posted,
            "degraded": degraded,
        },
        "stages": stages,
        # The same handoffs the live feed rendered, frozen into the proof. A
        # reopened run must tell the identical story, or the fallback path would
        # quietly be a different product than the live one.
        "handoffs": handoffs,
        "value": value,
        "roster": roster.roster(ctx.router)["seats"],
        "models": model_calls,
        "tools": tool_calls,
        "journal": {
            "balanced": bool(posted.get("balanced")) and bool(safe_journal),
            "entries": safe_journal,
        },
        "chain": {
            "ok": chain.ok,
            "links": len(event_rows),
            "head_hash": event_rows[-1]["hash"] if event_rows else None,
            "first_bad_seq": chain.first_bad_seq,
            "reason": chain.reason,
        },
    }


async def publish_run(run: CaseRun) -> None:
    for event in run.events:
        await hub.publish(
            {
                "event": "case_event",
                "case_id": run.case_id,
                "case_ref": run.case_ref,
                "case_status": run.status,
                "type": event.type,
                "actor": event.actor,
                "payload": event.payload,
            }
        )


class NormalizedIntake(BaseModel):
    subject: str = "Banking complaint"
    body: str
    from_email: str = "customer@example.my"
    attachments: list[dict[str, str]] = Field(default_factory=list)


class ReviewRequest(BaseModel):
    action: Literal["APPROVE", "REJECT", "REQUEST_INFO"]
    note: str = ""
    dual_control_by: str | None = None


class ProactiveRequest(BaseModel):
    account_no: str
    txn_ref: str
    amount_rm: float = Field(gt=0)
    merchant: str
    confirmed_not_mine: bool = True


class ProactiveDecision(BaseModel):
    confirmed_not_mine: bool


class ComposePolicyRequest(BaseModel):
    category: str
    request: str = Field(min_length=8, max_length=2000)


class PolicyDecisionRequest(BaseModel):
    note: str = Field(default="", max_length=2000)
    confirm_risk: bool = False


class StaffInviteRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    full_name: str = Field(min_length=2, max_length=120)
    role: Literal["OPS", "INVESTIGATOR", "COMPLIANCE", "ADMIN"]

    @field_validator("email")
    @classmethod
    def work_email(cls, value: str) -> str:
        email = value.strip().lower()
        if email.count("@") != 1 or "." not in email.rsplit("@", 1)[1]:
            raise ValueError("Enter a valid work email address.")
        return email


class StakeholderSettingsRequest(BaseModel):
    bank_display_name: str = Field(min_length=2, max_length=120)
    complaints_email: str = Field(min_length=5, max_length=254)
    timezone: Literal["Asia/Kuala_Lumpur", "UTC"] = "Asia/Kuala_Lumpur"
    sla_warning_hours: int = Field(ge=1, le=120)
    default_workspace: Literal["/simple", "/pro"]
    wajar_enabled: bool
    automatic_resolution_enabled: bool

    @field_validator("complaints_email")
    @classmethod
    def valid_complaints_email(cls, value: str) -> str:
        email = value.strip().lower()
        if email.count("@") != 1 or "." not in email.rsplit("@", 1)[1]:
            raise ValueError("Enter a valid complaints email address.")
        return email


class WajarCommandRequest(BaseModel):
    command: str = Field(min_length=2, max_length=500)


class WajarExecuteRequest(WajarCommandRequest):
    confirm: bool = False
    #: The plan the operator actually inspected. The server re-plans and refuses to
    #: act if its own conclusion differs, so a re-read can never quietly execute a
    #: different action than the one that was shown and approved.
    plan_id: str = Field(default="", max_length=32)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "casezero-api",
        "version": app.version,
        "provider": settings.active_provider,
        "mcp_transport": settings.mcp_transport,
    }


def _public_demo_response(row: dict[str, Any], *, reused: bool = False) -> dict[str, Any]:
    proof = copy.deepcopy(row.get("proof") or {})
    if proof and reused:
        proof.setdefault("execution", {})["reused"] = True
    return {
        "state": row.get("state"),
        "token": row.get("token"),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "proof": proof or None,
    }


@app.get("/demo/live/latest")
def latest_public_live_demo(
    db: Database = Depends(service_database),
) -> dict[str, Any]:
    """Show the latest completed proof when the metered run budget is exhausted."""
    row = db.latest_public_demo_run()
    if row is None:
        raise HTTPException(404, "No completed live execution is available yet.")
    return _public_demo_response(row, reused=True)


@app.get("/demo/live/{token}")
def public_live_demo_result(
    token: str,
    db: Database = Depends(service_database),
) -> dict[str, Any]:
    if len(token) < 24 or len(token) > 96:
        raise HTTPException(404, "Live execution proof not found.")
    row = db.get_public_demo_run(token)
    if row is None:
        raise HTTPException(404, "Live execution proof not found.")
    return _public_demo_response(row)


@app.get("/demo/live/{token}/progress")
def public_live_demo_progress(
    token: str,
    db: Database = Depends(service_database),
) -> dict[str, Any]:
    """Stage-by-stage progress of an in-flight run, read from the hash chain itself.

    The browser polls this while the execution request is still open, so the
    stakeholder watches real persisted events land rather than a scripted
    animation. A stage is only "done" once its chained event exists.
    """
    if not 24 <= len(token) <= 96:
        raise HTTPException(404, "Live execution not found.")
    row = db.get_public_demo_run(token)
    if row is None:
        raise HTTPException(404, "Live execution not found.")

    case_id = row.get("case_id")
    recorded: dict[str, dict[str, Any]] = {}
    if case_id:
        for event in db.get_event_rows(str(case_id)):
            recorded.setdefault(str(event["event_type"]), event)

    stages: list[dict[str, Any]] = []
    for stage_id, label, event_type, agent in PIPELINE_STAGES:
        event = recorded.get(event_type)
        stages.append(
            {
                "id": stage_id,
                "label": label,
                "agent": agent,
                "event_type": event_type,
                "done": event is not None,
                "seq": (event or {}).get("seq"),
                "actor": (event or {}).get("actor"),
                "recorded_at": (event or {}).get("created_at"),
            }
        )

    quarantined = "QUARANTINED" in {
        str((event.get("payload") or {}).get("to", "")) for event in recorded.values()
    }

    # What each agent said to the next one, assembled from the same rows the
    # stages above were built from. No extra model call, and no line for a stage
    # whose event has not landed yet.
    handoffs = build_handoffs(recorded)
    started_at = row.get("started_at")
    latest = max(
        (str(event.get("created_at") or "") for event in recorded.values()),
        default="",
    )
    elapsed: float | None = None
    if started_at and latest:
        try:
            elapsed = (
                datetime.fromisoformat(latest.replace("Z", "+00:00"))
                - datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
            ).total_seconds()
        except ValueError:
            elapsed = None

    return {
        "state": row.get("state"),
        "token": row.get("token"),
        "case_ref": row.get("case_ref"),
        "started_at": started_at,
        "stages": stages,
        "handoffs": handoffs,
        "value": build_value(
            handoffs,
            elapsed_seconds=elapsed,
            baseline_total=roster.BASELINE_MINUTES_TOTAL,
        ),
        "events_recorded": len(recorded),
        "quarantined": quarantined,
    }


@app.get("/demo/agents")
def public_demo_agents(ctx: AgentContext = Depends(agent_context)) -> dict[str, Any]:
    """Who works a case, and which model is behind each one right now.

    Resolved from the live `ModelRouter`, never from a constant in the frontend.
    If a provider key is absent the router reports the fallback it will actually
    use, so the panel cannot advertise a brain that is not running.
    """
    return roster.roster(ctx.router)


@app.get("/demo/personas")
def public_demo_personas() -> dict[str, Any]:
    """The fictional customers a public visitor may file a complaint against."""
    return {
        "enabled": settings.public_live_demo_enabled,
        "personas": [dict(persona) for persona in ALLOWED_PERSONAS],
        "limits": {
            "max_subject": MAX_SUBJECT,
            "max_body": MAX_BODY,
            "max_attachment_mb": MAX_ATTACHMENT_BYTES // (1024 * 1024),
            "min_amount_rm": MIN_AMOUNT_RM,
            "max_amount_rm": MAX_AMOUNT_RM,
            "attachment_types": sorted(ALLOWED_ATTACHMENT_TYPES),
            "runs_per_hour": settings.public_live_demo_hourly_limit,
        },
    }


def _reserve_public_run(request: Request, ctx: AgentContext, token: str) -> dict[str, Any]:
    """Claim this device's metered slot, translating SQL limits into plain errors."""
    try:
        return ctx.db.reserve_public_demo_run(
            fingerprint_hash=_public_demo_fingerprint(request),
            token=token,
            daily_limit=settings.public_live_demo_daily_limit,
            hourly_limit=settings.public_live_demo_hourly_limit,
        )
    except Exception as exc:  # PostgREST carries the named SQL limit in its message.
        reason = str(exc)
        if "PUBLIC_DEMO_DAILY_LIMIT" in reason:
            raise HTTPException(
                429,
                "Today’s live-run budget is complete. Open the latest verified run or ask the deployment owner to raise the governed limit.",
            ) from exc
        if "PUBLIC_DEMO_HOURLY_LIMIT" in reason:
            raise HTTPException(
                429,
                "This device has used its hourly live-run allowance. Reopen your prior proof or try again later.",
            ) from exc
        raise


async def _execute_public_run(
    *,
    ctx: AgentContext,
    token: str,
    account_no: str,
    merchant: str,
    amount_rm: float,
    build_email: Any,
    input_summary: dict[str, Any],
) -> dict[str, Any]:
    """Provision one disputable transaction, run the real pipeline, persist the proof.

    `build_email(txn_ref, posted_at) -> bytes` keeps the fixture runner and the
    stakeholder composer on exactly one execution path, so neither can quietly
    become the easier, less governed route.
    """
    started_at = datetime.now(timezone.utc)
    started_clock = time.perf_counter()
    model_start = len(ctx.llm_calls)
    tool_start = len(getattr(ctx.gateway, "calls", []))
    txn_ref = f"CZLIVE-{started_at:%Y%m%d}-{secrets.token_hex(4).upper()}"

    try:
        if ctx.db.get_account(account_no) is None:
            raise RuntimeError("The sanitized demo account has not been provisioned.")
        posted_at = started_at - timedelta(minutes=3)
        ctx.db.create_demo_transaction(
            txn_ref=txn_ref,
            account_no=account_no,
            merchant=merchant,
            amount_rm=amount_rm,
            direction="DEBIT",
            channel="online",
            country="MY",
            device_id=f"public_demo_{token[:10]}",
            posted_at=posted_at.isoformat(),
            is_disputed=False,
        )
        run = await Orchestrator(ctx).process(
            build_email(txn_ref, posted_at),
            channel="MANUAL_INJECT",
            on_case_created=lambda case_id, case_ref: ctx.db.attach_public_demo_case(
                token, case_id=case_id, case_ref=case_ref
            ),
        )
        await publish_run(run)
        proof = _build_public_demo_proof(
            token=token,
            run=run,
            ctx=ctx,
            txn_ref=txn_ref,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            duration_ms=int((time.perf_counter() - started_clock) * 1000),
            model_start=model_start,
            tool_start=tool_start,
        )
        proof["input"].update(input_summary)
        completed = ctx.db.complete_public_demo_run(
            token,
            state="COMPLETED",
            proof=proof,
            case_id=run.case_id,
            case_ref=run.case_ref,
        )
        return _public_demo_response(completed)
    except HTTPException:
        raise
    except Exception as exc:
        try:
            ctx.db.complete_public_demo_run(
                token,
                state="FAILED",
                error_code=type(exc).__name__,
            )
        except Exception:
            pass
        raise HTTPException(
            502,
            "The live execution stopped and no rehearsal result was substituted. Try once more or open the latest completed proof.",
        ) from exc


def _require_public_runner(ctx: AgentContext) -> None:
    if not settings.public_live_demo_enabled:
        raise HTTPException(
            503,
            "The public live runner is disabled. Staff can still inject an RFC822 email after sign-in.",
        )
    ctx.settings.require("fernet_key")


def _claim_token(request: Request, ctx: AgentContext, requested: str) -> str:
    """Reserve `requested`, or fail loudly if this device already holds a slot."""
    reservation = _reserve_public_run(request, ctx, requested)
    token = str(reservation["token"])
    if token != requested:
        if reservation.get("state") == "COMPLETED" and reservation.get("proof"):
            raise _ReusedRun(_public_demo_response(reservation, reused=True))
        raise HTTPException(
            409,
            "A live execution from this device is still running. Reopen it in a moment.",
        )
    return token


class _ReusedRun(Exception):
    """The metered budget returned an existing proof instead of a new slot."""

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__("reused")
        self.payload = payload


@app.post("/demo/live", status_code=status.HTTP_201_CREATED)
async def run_public_live_demo(
    request: Request,
    ctx: AgentContext = Depends(agent_context),
) -> dict[str, Any]:
    """Execute one sanitized fixture through the same live production pipeline."""
    _require_public_runner(ctx)
    try:
        token = _claim_token(request, ctx, secrets.token_urlsafe(32))
    except _ReusedRun as reused:
        return reused.payload

    return await _execute_public_run(
        ctx=ctx,
        token=token,
        account_no="7142556890",
        merchant="TECHWORLD KL",
        amount_rm=2450.0,
        build_email=lambda txn_ref, posted_at: _public_demo_email(
            txn_ref=txn_ref, posted_at=posted_at
        ),
        input_summary={"authored_by": "FIXTURE"},
    )


def _composed_email(complaint: AdmittedComplaint, txn_ref: str, posted_at: datetime) -> bytes:
    """Turn an admitted submission into the RFC822 message the pipeline expects."""
    message = EmailMessage()
    message["Subject"] = complaint.subject
    message["From"] = f"{complaint.from_name} <{complaint.from_email}>"
    message["To"] = settings.bank_complaints_email
    message["Date"] = format_datetime(posted_at)
    message.set_content(
        f"{complaint.body}\n\n"
        f"Account: {complaint.account_no}\n"
        f"Disputed amount: RM{complaint.amount_rm:,.2f}\n"
        f"Merchant: {complaint.merchant}\n"
        f"Transaction reference: {txn_ref}\n"
    )
    if complaint.attachment_bytes:
        message.add_attachment(
            complaint.attachment_bytes,
            maintype="application",
            subtype="pdf",
            filename=complaint.attachment_name or "evidence.pdf",
        )
    return message.as_bytes()


@app.post("/demo/compose", status_code=status.HTTP_201_CREATED)
async def compose_public_live_demo(
    request: Request,
    ctx: AgentContext = Depends(agent_context),
) -> dict[str, Any]:
    """Execute a complaint the visitor wrote themselves, with their own PDF evidence.

    A fixed fixture proves the pipeline runs; it does not prove the pipeline reads.
    So the wording, amount, merchant and attachment are the visitor's, while
    `api.security.public_intake` keeps the channel from becoming a PII inbox: the
    complaint must name an allow-listed fictional customer, and any foreign
    account number or NRIC is refused rather than scrubbed.
    """
    _require_public_runner(ctx)

    form = await request.form()
    upload = form.get("attachment")
    attachment_bytes: bytes | None = None
    attachment_name: str | None = None
    attachment_type: str | None = None
    if upload is not None and hasattr(upload, "read"):
        attachment_bytes = await upload.read()  # type: ignore[union-attr]
        attachment_name = getattr(upload, "filename", None)
        attachment_type = getattr(upload, "content_type", None)

    client_token = str(form.get("token") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,96}", client_token):
        raise HTTPException(422, "A valid client run token is required.")

    try:
        complaint = admit_public_complaint(
            account_no=str(form.get("account_no") or ""),
            from_name=str(form.get("from_name") or ""),
            from_email=str(form.get("from_email") or ""),
            subject=str(form.get("subject") or ""),
            body=str(form.get("body") or ""),
            amount_rm=str(form.get("amount_rm") or "0"),
            merchant=str(form.get("merchant") or ""),
            attachment_name=attachment_name,
            attachment_type=attachment_type,
            attachment_bytes=attachment_bytes,
        )
    except PublicIntakeRefused as refused:
        raise HTTPException(422, str(refused)) from refused

    try:
        token = _claim_token(request, ctx, client_token)
    except _ReusedRun as reused:
        return reused.payload

    return await _execute_public_run(
        ctx=ctx,
        token=token,
        account_no=complaint.account_no,
        merchant=complaint.merchant,
        amount_rm=complaint.amount_rm,
        build_email=lambda txn_ref, posted_at: _composed_email(complaint, txn_ref, posted_at),
        input_summary={
            "authored_by": "STAKEHOLDER",
            "subject": complaint.subject,
            "sender": complaint.from_email,
            "attachment": complaint.attachment_name if complaint.has_attachment else None,
            "attachment_read_by": "vision OCR" if complaint.has_attachment else None,
        },
    )


@app.get("/auth/config")
def auth_config() -> dict[str, Any]:
    return {
        "supabase_url": settings.supabase_url,
        "supabase_anon_key": settings.supabase_anon_key,
    }


@app.get("/me")
def current_operator(user: AuthUser = Depends(current_user)) -> dict[str, Any]:
    """The signed-in operator's identity and role, so the UI can hide what they cannot use."""
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
    }


@app.get("/admin/users")
def list_staff_users(
    user: AuthUser = Depends(current_user),
    invitations: StaffInvitationService = Depends(invitation_service),
) -> dict[str, Any]:
    user.require("ADMIN")
    return {"items": invitations.list_staff(), "roles": list(ROLES)}


@app.post("/admin/users/invite", status_code=status.HTTP_201_CREATED)
def invite_staff_user(
    payload: StaffInviteRequest,
    user: AuthUser = Depends(current_user),
    invitations: StaffInvitationService = Depends(invitation_service),
) -> dict[str, Any]:
    user.require("ADMIN")
    try:
        return invitations.invite(
            StaffInvite(
                email=payload.email,
                full_name=payload.full_name,
                role=payload.role,
            )
        )
    except InvitationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def control_register_response(db: Database) -> dict[str, Any]:
    row = db.get_stakeholder_settings()
    verdict = db.verify_settings_chain()
    return {
        "settings": row,
        "chain": {
            "ok": verdict.ok,
            "links": len(db.get_settings_events()),
            "first_bad_seq": verdict.first_bad_seq,
            "reason": verdict.reason,
        },
    }


@app.get("/settings")
def stakeholder_controls(
    _: AuthUser = Depends(current_user),
    db: Database = Depends(rls_database),
) -> dict[str, Any]:
    return control_register_response(db)


@app.put("/settings")
def update_stakeholder_controls(
    payload: StakeholderSettingsRequest,
    user: AuthUser = Depends(current_user),
    db: Database = Depends(service_database),
) -> dict[str, Any]:
    user.require("ADMIN")
    before = db.get_stakeholder_settings()
    changes = {
        key: value
        for key, value in payload.model_dump().items()
        if before.get(key) != value
    }
    if changes:
        db.update_stakeholder_settings(**changes, updated_by=user.id)
        db.append_settings_event(
            "SETTINGS_UPDATED",
            f"user:{user.id}",
            {
                "changes": {
                    key: {"from": before.get(key), "to": value}
                    for key, value in changes.items()
                }
            },
        )
    return {**control_register_response(db), "changed": sorted(changes)}


@app.get("/assistant/receipts")
def assistant_receipts(
    user: AuthUser = Depends(current_user),
    db: Database = Depends(rls_database),
) -> dict[str, Any]:
    user.require("OPS", "COMPLIANCE", "ADMIN")
    rows = db.list_assistant_receipts(limit=50)
    return {"items": rows, "count": len(rows)}


@app.post("/assistant/plan")
async def wajar_plan(
    payload: WajarCommandRequest,
    user: AuthUser = Depends(current_user),
    db: Database = Depends(rls_database),
    ctx: AgentContext = Depends(agent_context),
) -> dict[str, Any]:
    """Understand the request with the model; decide authority in code.

    Reads run against `db` so RLS still applies to whatever Axiom summarises. The
    model only resolves phrasing the deterministic matcher could not.
    """
    planned = await plan_wajar_with_model(payload.command, user.role, db, ctx)
    return {"plan": planned.as_dict()}


@app.post("/assistant/execute")
async def wajar_execute(
    payload: WajarExecuteRequest,
    user: AuthUser = Depends(current_user),
    db: Database = Depends(service_database),
    invitations: StaffInvitationService = Depends(invitation_service),
    ctx: AgentContext = Depends(agent_context),
) -> dict[str, Any]:
    # Re-plan against server state. The browser never chooses the action it runs.
    planned = await plan_wajar_with_model(payload.command, user.role, db, ctx)
    if planned.action not in {"INVITE_OPERATOR", "UPDATE_SETTING"}:
        raise HTTPException(409, "This command has no confirmed write action.")
    if payload.plan_id and payload.plan_id != planned.plan_id:
        raise HTTPException(
            409,
            "Axiom re-read this request and reached a different action. "
            "Review the new docket before confirming.",
        )
    if not planned.permitted:
        raise HTTPException(403, planned.summary)
    if not payload.confirm:
        raise HTTPException(409, "Explicit confirmation is required.")

    if planned.action == "INVITE_OPERATOR":
        try:
            result = invitations.invite(
                StaffInvite(
                    email=str(planned.parameters["email"]),
                    full_name=str(planned.parameters["full_name"]),
                    role=str(planned.parameters["role"]),
                )
            )
        except InvitationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        outcome = "EXECUTED"
    else:
        key = str(planned.parameters["key"])
        value = planned.parameters["value"]
        allowed = {
            "bank_display_name",
            "complaints_email",
            "sla_warning_hours",
            "default_workspace",
            "wajar_enabled",
            "automatic_resolution_enabled",
        }
        if key not in allowed:
            raise HTTPException(422, "Axiom selected an unknown control.")
        before = db.get_stakeholder_settings()
        updated = db.update_stakeholder_settings(**{key: value}, updated_by=user.id)
        event = db.append_settings_event(
            "SETTINGS_UPDATED_BY_AXIOM",
            f"user:{user.id}",
            {"key": key, "from": before.get(key), "to": value, "plan_id": planned.plan_id},
        )
        result = {
            "key": key,
            "value": updated.get(key),
            "settings_event_seq": event.seq,
        }
        outcome = "EXECUTED"

    receipt = receipt_payload(
        payload.command,
        user.role,
        planned.action,
        planned.parameters,
        result,
    )
    db.record_assistant_receipt(
        **receipt,
        actor_id=user.id,
        actor_role=user.role,
        action=planned.action,
        parameters=planned.parameters,
        outcome=outcome,
        result=result,
    )
    return {"plan": planned.as_dict(), "result": result, "receipt": receipt}


@app.post("/intake", status_code=status.HTTP_201_CREATED)
async def intake_email(
    request: Request,
    _: AuthUser = Depends(current_user),
    ctx: AgentContext = Depends(agent_context),
) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(400, "Multipart intake requires a 'file' field.")
        raw = await upload.read()
    else:
        raw = await request.body()
    if not raw:
        raise HTTPException(400, "An RFC822 message is required.")
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(413, "Email exceeds the 20 MB intake limit.")
    run = await Orchestrator(ctx).process(raw, channel="MANUAL_INJECT")
    await publish_run(run)
    return run_summary(run)


def normalized_email(payload: NormalizedIntake, contact_email: str) -> bytes:
    message = EmailMessage()
    message["Subject"] = payload.subject
    message["From"] = payload.from_email
    message["To"] = contact_email
    message.set_content(payload.body)
    for attachment in payload.attachments:
        try:
            content = base64.b64decode(attachment["content_base64"], validate=True)
            mime = attachment.get("mime_type", "application/octet-stream")
            maintype, subtype = mime.split("/", 1)
            message.add_attachment(
                content,
                maintype=maintype,
                subtype=subtype,
                filename=attachment.get("filename", "attachment"),
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(422, "Invalid WorkBuddy attachment payload.") from exc
    return message.as_bytes()


@app.post("/intake/workbuddy", status_code=status.HTTP_201_CREATED)
async def intake_workbuddy(
    payload: NormalizedIntake,
    x_workbuddy_token: str | None = Header(default=None),
    ctx: AgentContext = Depends(agent_context),
) -> dict[str, Any]:
    expected = settings.workbuddy_intake_token
    if not expected or not x_workbuddy_token or not secrets.compare_digest(expected, x_workbuddy_token):
        raise HTTPException(401, "Invalid WorkBuddy intake token.")
    run = await Orchestrator(ctx).process(
        normalized_email(payload, ctx.settings.bank_complaints_email), channel="WORKBUDDY_EMAIL_MCP"
    )
    await publish_run(run)
    return run_summary(run)


@app.post("/intake/proactive", status_code=status.HTTP_201_CREATED)
async def intake_proactive(
    payload: ProactiveRequest,
    _: AuthUser = Depends(current_user),
    ctx: AgentContext = Depends(agent_context),
) -> dict[str, Any]:
    if not payload.confirmed_not_mine:
        return {"accepted": False, "message": "Transaction confirmed by customer."}
    message = EmailMessage()
    message["Subject"] = "Proactive dispute confirmation"
    complaints_email = public_complaints_email(ctx.db)
    message["From"] = complaints_email
    message["To"] = complaints_email
    message.set_content(
        f"The customer confirmed this transaction was not theirs. Account "
        f"{payload.account_no}; debit RM{payload.amount_rm:,.2f}; merchant "
        f"{payload.merchant}; reference {payload.txn_ref}. Treat this as an "
        "unauthorised transaction complaint."
    )
    run = await Orchestrator(ctx).process(message.as_bytes(), channel="PROACTIVE")
    await publish_run(run)
    return run_summary(run)


def public_bank_name(db: Database) -> str:
    try:
        configured = db.get_stakeholder_settings().get("bank_display_name")
    except Exception:  # pragma: no cover - only protects a pre-migration deployment
        configured = None
    return str(configured or settings.bank_name)


def public_complaints_email(db: Database) -> str:
    try:
        configured = db.get_stakeholder_settings().get("complaints_email")
    except Exception:  # pragma: no cover - only protects a pre-migration deployment
        configured = None
    return str(configured or settings.bank_complaints_email)


def public_proactive(alert: dict[str, Any], db: Database) -> dict[str, Any]:
    return {
        "token": alert["token"],
        "txn_ref": alert["txn_ref"],
        "amount_rm": alert["amount_rm"],
        "merchant": alert["merchant"],
        "occurred_at": alert.get("occurred_at"),
        "status": alert["status"],
        "expires_at": alert["expires_at"],
        "case_id": alert.get("case_id"),
        "bank_name": public_bank_name(db),
    }


@app.get("/proactive/{token}")
def proactive_alert(
    token: str,
    db: Database = Depends(service_database),
) -> dict[str, Any]:
    alert = db.get_proactive_alert(token)
    if alert is None:
        raise HTTPException(404, "Proactive alert is invalid or expired.")
    expires = datetime.fromisoformat(str(alert["expires_at"]).replace("Z", "+00:00"))
    if alert["status"] == "PENDING" and expires < datetime.now(timezone.utc):
        alert = db.update_proactive_alert(str(alert["id"]), status="EXPIRED")
    return public_proactive(alert, db)


@app.post("/proactive/{token}/respond")
async def respond_proactive(
    token: str,
    payload: ProactiveDecision,
    ctx: AgentContext = Depends(agent_context),
) -> dict[str, Any]:
    alert = ctx.db.get_proactive_alert(token)
    if alert is None:
        raise HTTPException(404, "Proactive alert is invalid or expired.")
    if alert["status"] != "PENDING":
        return {"alert": public_proactive(alert, ctx.db), "idempotent": True}
    expires = datetime.fromisoformat(str(alert["expires_at"]).replace("Z", "+00:00"))
    if expires < datetime.now(timezone.utc):
        ctx.db.update_proactive_alert(str(alert["id"]), status="EXPIRED")
        raise HTTPException(410, "Proactive alert has expired.")

    responded_at = datetime.now(timezone.utc).isoformat()
    if not payload.confirmed_not_mine:
        updated = ctx.db.update_proactive_alert(
            str(alert["id"]), status="CONFIRMED", responded_at=responded_at
        )
        return {
            "alert": public_proactive(updated, ctx.db),
            "accepted": False,
            "message": "Transaction confirmed by customer. No dispute was filed.",
        }

    message = EmailMessage()
    message["Subject"] = "Proactive dispute confirmation"
    complaints_email = public_complaints_email(ctx.db)
    message["From"] = complaints_email
    message["To"] = complaints_email
    message.set_content(
        f"The customer confirmed this transaction was not theirs. Account "
        f"{alert['account_no']}; debit RM{float(alert['amount_rm']):,.2f}; merchant "
        f"{alert['merchant']}; reference {alert['txn_ref']}. Treat this as an "
        "unauthorised transaction complaint."
    )
    run = await Orchestrator(ctx).process(message.as_bytes(), channel="PROACTIVE")
    updated = ctx.db.update_proactive_alert(
        str(alert["id"]),
        status="DISPUTED",
        case_id=run.case_id,
        responded_at=responded_at,
    )
    await publish_run(run)
    case = ctx.db.get_case(run.case_id) or {}
    return {
        "alert": public_proactive(updated, ctx.db),
        "case": {**run_summary(run), "track_token": case.get("track_token")},
    }


@app.get("/cases")
def cases(
    case_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    db: Database = Depends(rls_database),
) -> dict[str, Any]:
    rows = db.list_cases(status=case_status, limit=limit)
    return {"items": [public_case(row) for row in rows], "count": len(rows)}


@app.get("/cases/{case_ref}")
def case_detail(case_ref: str, db: Database = Depends(rls_database)) -> dict[str, Any]:
    case = db.get_case_by_ref(case_ref)
    if case is None:
        raise HTTPException(404, "Case not found or hidden by your role.")
    events = db.get_events(str(case["id"]))
    verdict = db.verify_case_chain(str(case["id"]))
    journal = db.get_journal(str(case["id"]))
    return {
        "case": public_case(case),
        "events": [
            {
                "seq": event.seq,
                "event_type": event.event_type,
                "actor": event.actor,
                "payload": event.payload,
                "prev_hash": event.prev_hash,
                "hash": event.hash,
            }
            for event in events
        ],
        "journal": journal,
        "chain": {
            "ok": verdict.ok,
            "first_bad_seq": verdict.first_bad_seq,
            "reason": verdict.reason,
        },
        "cost_rm": db.case_cost_rm(str(case["id"])),
    }


@app.get("/analytics/overview")
def analytics_overview(
    _: AuthUser = Depends(current_user),
    db: Database = Depends(rls_database),
) -> dict[str, Any]:
    return {
        "metrics": db.rpc("dashboard_metrics"),
        "category_volumes": db.rpc("category_volumes"),
        "investigator_workload": db.rpc("investigator_workload"),
        "eval_runs": db.list_eval_runs(limit=10),
    }


@app.get("/fraud/rings")
def fraud_rings(
    min_cases: int = Query(default=3, ge=2, le=20),
    _: AuthUser = Depends(current_user),
    db: Database = Depends(rls_database),
) -> dict[str, Any]:
    rows = db.rpc("detect_fraud_rings", {"min_cases": min_cases})
    safe = [
        {
            **row,
            "account_nos": [f"******{str(account)[-4:]}" for account in row.get("account_nos", [])],
        }
        for row in rows
    ]
    return {"items": safe, "count": len(safe)}


@app.get("/quarantine")
def quarantine_register(
    user: AuthUser = Depends(current_user),
    db: Database = Depends(rls_database),
) -> dict[str, Any]:
    user.require("COMPLIANCE", "ADMIN")
    rows = db.list_quarantine()
    return {"items": rows, "count": len(rows)}


@app.get("/audit/{case_ref}/verify")
def audit_verify(
    case_ref: str,
    _: AuthUser = Depends(current_user),
    db: Database = Depends(rls_database),
) -> dict[str, Any]:
    case = db.get_case_by_ref(case_ref)
    if case is None:
        raise HTTPException(404, "Case not found or hidden by your role.")
    verdict = db.verify_case_chain(str(case["id"]))
    return {
        "case_ref": case_ref,
        "ok": verdict.ok,
        "first_bad_seq": verdict.first_bad_seq,
        "reason": verdict.reason,
        "links": len(db.get_events(str(case["id"]))),
    }


@app.get("/cases/{case_ref}/fmos-pack")
def fmos_pack(
    case_ref: str,
    user: AuthUser = Depends(current_user),
    db: Database = Depends(rls_database),
) -> Response:
    user.require("COMPLIANCE", "ADMIN")
    case = db.get_case_by_ref(case_ref)
    if case is None:
        raise HTTPException(404, "Case not found or hidden by your role.")
    case_id = str(case["id"])
    payload = build_fmos_pack(
        case=case,
        events=db.get_events(case_id),
        journal=db.get_journal(case_id),
        verdict=db.verify_case_chain(case_id),
        contact_email=str(db.get_stakeholder_settings().get("complaints_email") or settings.bank_complaints_email),
    )
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="FMOS-{case_ref}.pdf"'},
    )


@app.post("/review/{case_ref}")
async def review_case(
    case_ref: str,
    payload: ReviewRequest,
    user: AuthUser = Depends(current_user),
    ctx: AgentContext = Depends(agent_context),
) -> dict[str, Any]:
    user.require("INVESTIGATOR", "COMPLIANCE", "ADMIN")
    case = ctx.db.get_case_by_ref(case_ref)
    if case is None:
        raise HTTPException(404, "Case not found.")
    try:
        result = await decide(
            case,
            payload.action,
            ctx,
            user_id=user.id,
            dual_control_by=payload.dual_control_by,
            note=payload.note,
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(409, str(exc)) from exc
    await hub.publish(
        {
            "event": "review_decision",
            "case_id": case["id"],
            "case_ref": case_ref,
            "type": payload.action,
            "actor": f"user:{user.id}",
            "payload": result,
        }
    )
    return {"case_ref": case_ref, **result}


@app.get("/events/stream")
async def event_stream(
    request: Request,
    after: int = Query(default=0, ge=0),
    _: AuthUser = Depends(current_user),
) -> EventSourceResponse:
    async def events():
        async for envelope in hub.subscribe(after=after):
            if await request.is_disconnected():
                break
            yield {
                "id": str(envelope.get("id", "")),
                "event": str(envelope.get("event", "message")),
                "data": json.dumps(envelope, separators=(",", ":"), default=str),
            }

    return EventSourceResponse(events(), ping=15)


def policy_response(row: dict[str, Any], db: Database | None = None) -> dict[str, Any]:
    safe = dict(row)
    if db is not None and row.get("id"):
        events = db.get_policy_events(str(row["id"]))
        verdict = db.verify_policy_chain(str(row["id"]))
        safe["events"] = [
            {
                "seq": event.seq,
                "event_type": event.event_type,
                "actor": event.actor,
                "payload": event.payload,
                "prev_hash": event.prev_hash,
                "hash": event.hash,
            }
            for event in events
        ]
        safe["chain"] = {
            "ok": verdict.ok,
            "first_bad_seq": verdict.first_bad_seq,
            "reason": verdict.reason,
        }
    return safe


@app.get("/policy/packs")
def policy_packs(
    category: str | None = Query(default=None),
    _: AuthUser = Depends(current_user),
    db: Database = Depends(rls_database),
) -> dict[str, Any]:
    rows = db.list_packs(category)
    return {"items": rows, "count": len(rows)}


@app.get("/policy/proposals")
def policy_proposals(
    _: AuthUser = Depends(current_user),
    db: Database = Depends(rls_database),
) -> dict[str, Any]:
    rows = db.list_policy_proposals()
    return {"items": rows, "count": len(rows)}


@app.get("/policy/proposals/{proposal_id}")
def policy_proposal(
    proposal_id: str,
    _: AuthUser = Depends(current_user),
    db: Database = Depends(rls_database),
) -> dict[str, Any]:
    row = db.get_policy_proposal(proposal_id)
    if row is None:
        raise HTTPException(404, "Policy proposal not found.")
    return policy_response(row, db)


@app.post("/policy/compose", status_code=status.HTTP_201_CREATED)
async def compose_policy(
    payload: ComposePolicyRequest,
    user: AuthUser = Depends(current_user),
    ctx: AgentContext = Depends(agent_context),
) -> dict[str, Any]:
    user.require("OPS", "COMPLIANCE", "ADMIN")
    try:
        base = ctx.pack(payload.category)
        intent = await interpret_request(payload.request, payload.category, ctx)
        corpus = load_evaluation_labels() or ctx.db.list_cases(limit=500)
        candidate = candidate_from_intent(base, intent, corpus)
    except (ComposerError, KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc

    row = ctx.db.create_policy_proposal(
        nl_request=payload.request,
        target_category=payload.category,
        base_version=base.version,
        proposed_yaml=candidate.pack.source_yaml,
        diff_json=candidate.diff,
        plain_english_diff=candidate.plain_english_diff,
        eval_impact=candidate.impact.as_dict(),
        risk_flag=candidate.risk_flag,
        author=user.id,
    )
    ctx.db.append_policy_event(
        str(row["id"]),
        "POLICY_PROPOSED",
        f"user:{user.id}",
        {
            "category": payload.category,
            "base_version": base.version,
            "proposed_version": candidate.pack.version,
            "diff": candidate.diff,
            "impact": candidate.impact.as_dict(),
            "risk_flag": candidate.risk_flag,
        },
    )
    return policy_response(row, ctx.db)


@app.post("/policy/proposals/{proposal_id}/apply")
async def apply_policy(
    proposal_id: str,
    payload: PolicyDecisionRequest,
    user: AuthUser = Depends(current_user),
    db: Database = Depends(service_database),
) -> dict[str, Any]:
    user.require("COMPLIANCE", "ADMIN")
    proposal = db.get_policy_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(404, "Policy proposal not found.")
    if proposal.get("status") != "DRAFT":
        raise HTTPException(409, "Only a DRAFT proposal can be applied.")
    if proposal.get("risk_flag") and not payload.confirm_risk:
        raise HTTPException(409, "Risk confirmation is required before apply.")

    candidate = load_yaml(str(proposal["proposed_yaml"]))
    active = db.active_pack(candidate.category)
    if active and int(active["version"]) != int(proposal["base_version"]):
        raise HTTPException(
            409,
            "The active pack changed after simulation. Re-compose against the new version.",
        )

    db.upsert_pack(
        category=candidate.category,
        version=candidate.version,
        yaml_text=candidate.source_yaml,
        is_active=False,
        change_summary=str(proposal.get("plain_english_diff") or "Policy Composer change"),
        parent_version=int(proposal["base_version"]),
        created_by=user.id,
    )
    db.activate_pack(candidate.category, candidate.version)
    decided_at = datetime.now(timezone.utc).isoformat()
    row = db.update_policy_proposal(
        proposal_id,
        status="APPLIED",
        decided_by=user.id,
        decided_at=decided_at,
    )
    db.append_policy_event(
        proposal_id,
        "POLICY_APPLIED",
        f"user:{user.id}",
        {
            "category": candidate.category,
            "version": candidate.version,
            "parent_version": proposal["base_version"],
            "risk_confirmed": payload.confirm_risk,
            "note": payload.note,
        },
    )
    await hub.publish(
        {
            "event": "policy_applied",
            "type": "POLICY_APPLIED",
            "actor": f"user:{user.id}",
            "payload": {"category": candidate.category, "version": candidate.version},
        }
    )
    return policy_response(row, db)


@app.post("/policy/proposals/{proposal_id}/reject")
def reject_policy(
    proposal_id: str,
    payload: PolicyDecisionRequest,
    user: AuthUser = Depends(current_user),
    db: Database = Depends(service_database),
) -> dict[str, Any]:
    user.require("COMPLIANCE", "ADMIN")
    proposal = db.get_policy_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(404, "Policy proposal not found.")
    if proposal.get("status") != "DRAFT":
        raise HTTPException(409, "Only a DRAFT proposal can be rejected.")
    row = db.update_policy_proposal(
        proposal_id,
        status="REJECTED",
        decided_by=user.id,
        decided_at=datetime.now(timezone.utc).isoformat(),
    )
    db.append_policy_event(
        proposal_id,
        "POLICY_REJECTED",
        f"user:{user.id}",
        {"note": payload.note},
    )
    return policy_response(row, db)


@app.get("/track/{token}")
def customer_tracker(token: str, db: Database = Depends(service_database)) -> dict[str, Any]:
    case = db.get_case_by_token(token)
    if case is None:
        raise HTTPException(404, "Tracker link is invalid or expired.")
    events = db.get_events(str(case["id"]))
    public_events = [
        {
            "event_type": event.event_type,
            "at": event.payload.get("received_at") or event.payload.get("sla_due"),
        }
        for event in events
        if event.event_type
        in {"CASE_RECEIVED", "CLASSIFIED", "VERIFICATION_COMPLETED", "JOURNAL_POSTED", "MESSAGE_SENT", "STATUS_CHANGED"}
    ]
    return {
        "case_ref": case["case_ref"],
        "status": case["status"],
        "category": case.get("category"),
        "urgency": case.get("urgency"),
        "sla_due": case.get("sla_due"),
        "outcome": case.get("outcome"),
        "amount_rm": case.get("amount_rm"),
        "timeline": public_events,
        "bank_name": public_bank_name(db),
        "contact": public_complaints_email(db),
    }
