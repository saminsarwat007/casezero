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
import json
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any, Literal

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sse_starlette.sse import EventSourceResponse

from api.agents.base import AgentContext, build_context
from api.agents.orchestrator import CaseRun, Orchestrator
from api.agents.wajar import plan as plan_wajar
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


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "casezero-api",
        "version": app.version,
        "provider": settings.active_provider,
        "mcp_transport": settings.mcp_transport,
    }


@app.get("/auth/config")
def auth_config() -> dict[str, Any]:
    return {
        "supabase_url": settings.supabase_url,
        "supabase_anon_key": settings.supabase_anon_key,
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
def wajar_plan(
    payload: WajarCommandRequest,
    user: AuthUser = Depends(current_user),
    db: Database = Depends(rls_database),
) -> dict[str, Any]:
    return {"plan": plan_wajar(payload.command, user.role, db).as_dict()}


@app.post("/assistant/execute")
def wajar_execute(
    payload: WajarExecuteRequest,
    user: AuthUser = Depends(current_user),
    db: Database = Depends(service_database),
    invitations: StaffInvitationService = Depends(invitation_service),
) -> dict[str, Any]:
    # Re-plan against server state. The browser never chooses the action it runs.
    planned = plan_wajar(payload.command, user.role, db)
    if planned.action not in {"INVITE_OPERATOR", "UPDATE_SETTING"}:
        raise HTTPException(409, "This command has no confirmed write action.")
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
            raise HTTPException(422, "Wajar selected an unknown control.")
        before = db.get_stakeholder_settings()
        updated = db.update_stakeholder_settings(**{key: value}, updated_by=user.id)
        event = db.append_settings_event(
            "SETTINGS_UPDATED_BY_WAJAR",
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
    message["From"] = "proactive.monitor@mybank.com.my"
    message["To"] = ctx.settings.bank_complaints_email
    message.set_content(
        f"The customer confirmed this transaction was not theirs. Account "
        f"{payload.account_no}; debit RM{payload.amount_rm:,.2f}; merchant "
        f"{payload.merchant}; reference {payload.txn_ref}. Treat this as an "
        "unauthorised transaction complaint."
    )
    run = await Orchestrator(ctx).process(message.as_bytes(), channel="PROACTIVE")
    await publish_run(run)
    return run_summary(run)


def public_proactive(alert: dict[str, Any]) -> dict[str, Any]:
    return {
        "token": alert["token"],
        "txn_ref": alert["txn_ref"],
        "amount_rm": alert["amount_rm"],
        "merchant": alert["merchant"],
        "occurred_at": alert.get("occurred_at"),
        "status": alert["status"],
        "expires_at": alert["expires_at"],
        "case_id": alert.get("case_id"),
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
    return public_proactive(alert)


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
        return {"alert": public_proactive(alert), "idempotent": True}
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
            "alert": public_proactive(updated),
            "accepted": False,
            "message": "Transaction confirmed by customer. No dispute was filed.",
        }

    message = EmailMessage()
    message["Subject"] = "Proactive dispute confirmation"
    message["From"] = "proactive.monitor@mybank.com.my"
    message["To"] = ctx.settings.bank_complaints_email
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
        "alert": public_proactive(updated),
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
        "contact": str(db.get_stakeholder_settings().get("complaints_email") or settings.bank_complaints_email),
    }
