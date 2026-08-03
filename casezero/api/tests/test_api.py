"""The HTTP boundary: auth, RFC822 intake, RLS-shaped reads and human review."""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from api.main import agent_context, app
from api.db.invitations import invitation_service
from api.web.auth import AuthUser, current_user, rls_database, service_database


@pytest.fixture
def api_client(agent_ctx, fake_db):
    user = AuthUser(
        id="11111111-1111-1111-1111-111111111111",
        email="investigator@example.my",
        full_name="Faizal Rahman",
        role="INVESTIGATOR",
    )
    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[service_database] = lambda: fake_db
    app.dependency_overrides[rls_database] = lambda: fake_db
    app.dependency_overrides[agent_context] = lambda: agent_ctx
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def compliance_api_client(agent_ctx, fake_db):
    user = AuthUser(
        id="22222222-2222-2222-2222-222222222222",
        email="compliance@example.my",
        full_name="Mei Ling Tan",
        role="COMPLIANCE",
    )
    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[service_database] = lambda: fake_db
    app.dependency_overrides[rls_database] = lambda: fake_db
    app.dependency_overrides[agent_context] = lambda: agent_ctx
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_api_client(agent_ctx, fake_db):
    user = AuthUser(
        id="33333333-3333-3333-3333-333333333333",
        email="admin@casezero.my",
        full_name="Ravi Kumaran",
        role="ADMIN",
    )
    invited = []

    class Invitations:
        def list_staff(self):
            return [{"email": "admin@casezero.my", "full_name": "Ravi Kumaran", "role": "ADMIN"}]

        def invite(self, invite):
            invited.append(invite)
            return {"email": invite.email, "full_name": invite.full_name, "role": invite.role, "invitation": "SENT"}

    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[service_database] = lambda: fake_db
    app.dependency_overrides[rls_database] = lambda: fake_db
    app.dependency_overrides[agent_context] = lambda: agent_ctx
    app.dependency_overrides[invitation_service] = Invitations
    with TestClient(app) as client:
        client.invited = invited
        yield client
    app.dependency_overrides.clear()


def test_health_is_public_and_names_the_runtime() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "casezero-api"
    assert response.json()["mcp_transport"] in {"stdio", "inproc"}


def test_vercel_service_prefix_reaches_the_same_health_route() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["service"] == "casezero-api"


def test_case_reads_require_a_bearer_token() -> None:
    with TestClient(app) as client:
        response = client.get("/cases")
    assert response.status_code == 401


def test_admin_can_invite_a_staff_email(admin_api_client) -> None:
    listed = admin_api_client.get("/admin/users")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["role"] == "ADMIN"

    response = admin_api_client.post(
        "/admin/users/invite",
        json={"email": "new.ops@bank.my", "full_name": "New Operator", "role": "OPS"},
    )
    assert response.status_code == 201
    assert response.json()["invitation"] == "SENT"
    assert admin_api_client.invited[0].email == "new.ops@bank.my"


def test_non_admin_cannot_list_staff(api_client) -> None:
    response = api_client.get("/admin/users")
    assert response.status_code == 403


def test_admin_updates_hash_chained_stakeholder_controls(admin_api_client, fake_db) -> None:
    response = admin_api_client.put(
        "/settings",
        json={
            "bank_display_name": "MYBank Berhad",
            "complaints_email": "care@mybank.example",
            "timezone": "Asia/Kuala_Lumpur",
            "sla_warning_hours": 12,
            "default_workspace": "/pro",
            "wajar_enabled": True,
            "automatic_resolution_enabled": False,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["settings"]["sla_warning_hours"] == 12
    assert response.json()["chain"] == {
        "ok": True,
        "links": 1,
        "first_bad_seq": None,
        "reason": None,
    }
    assert "automatic_resolution_enabled" in response.json()["changed"]
    assert fake_db.settings_events[0].event_type == "SETTINGS_UPDATED"


def test_wajar_replans_and_executes_admin_setting_with_receipt(
    admin_api_client, fake_db
) -> None:
    planned = admin_api_client.post(
        "/assistant/plan", json={"command": "Set SLA warning to 18 hours"}
    )
    assert planned.status_code == 200
    assert planned.json()["plan"]["confirmation_required"] is True

    refused = admin_api_client.post(
        "/assistant/execute",
        json={"command": "Set SLA warning to 18 hours", "confirm": False},
    )
    assert refused.status_code == 409

    executed = admin_api_client.post(
        "/assistant/execute",
        json={"command": "Set SLA warning to 18 hours", "confirm": True},
    )
    assert executed.status_code == 200, executed.text
    assert executed.json()["result"]["value"] == 18
    assert executed.json()["receipt"]["receipt_id"].startswith("WJR-")
    assert fake_db.assistant_receipts[0]["action"] == "UPDATE_SETTING"


def test_wajar_admin_can_send_a_confirmed_operator_invitation(admin_api_client) -> None:
    command = "Invite Amina Rahman at amina@mybank.example as COMPLIANCE"
    response = admin_api_client.post(
        "/assistant/execute", json={"command": command, "confirm": True}
    )

    assert response.status_code == 200, response.text
    assert response.json()["result"]["invitation"] == "SENT"
    assert admin_api_client.invited[-1].role == "COMPLIANCE"


def test_investigator_cannot_execute_admin_wajar_action(api_client) -> None:
    response = api_client.post(
        "/assistant/execute",
        json={"command": "Set SLA warning to 18 hours", "confirm": True},
    )
    assert response.status_code == 403


def test_one_rfc822_email_resolves_through_the_http_api(api_client, eml_corpus) -> None:
    response = api_client.post(
        "/intake",
        content=eml_corpus["happy_path"],
        headers={"Content-Type": "message/rfc822"},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "COMMUNICATED"
    assert data["verification_result"] == "PASS"
    assert data["posted"] is True


def test_control_register_can_pause_autonomous_financial_resolution(
    api_client, eml_corpus, fake_db
) -> None:
    fake_db.settings["automatic_resolution_enabled"] = False
    response = api_client.post("/intake", content=eml_corpus["happy_path"])

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "REVIEW_PENDING"
    assert response.json()["posted"] is False
    gate = next(
        event for event in response.json()["timeline"] if event["type"] == "GATE_DECISION"
    )
    assert gate["payload"]["action"] == "MANUAL_REVIEW"
    assert "stakeholder_settings.automatic_resolution_enabled = false" in gate["payload"]["citations"]


def test_case_list_never_returns_ciphertext(api_client, eml_corpus) -> None:
    api_client.post("/intake", content=eml_corpus["happy_path"])
    response = api_client.get("/cases")
    assert response.status_code == 200
    case = response.json()["items"][0]
    assert "account_no_enc" not in case
    assert "nric_enc" not in case
    assert case["account_no_masked"] == "******6890"


def test_case_detail_includes_verified_chain_journal_and_cost(api_client, eml_corpus) -> None:
    created = api_client.post("/intake", content=eml_corpus["happy_path"]).json()
    response = api_client.get(f"/cases/{created['case_ref']}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["chain"]["ok"] is True
    assert len(detail["journal"]) == 1
    assert detail["cost_rm"] > 0
    assert any(event["event_type"] == "JOURNAL_POSTED" for event in detail["events"])


def test_workbuddy_rejects_a_missing_shared_secret(api_client) -> None:
    response = api_client.post(
        "/intake/workbuddy",
        json={"subject": "Dispute", "body": "A charge is wrong."},
    )
    assert response.status_code == 401


def test_human_approval_resumes_a_low_confidence_pass_case(
    api_client, eml_corpus, scripted_llm, fake_db
) -> None:
    scripted_llm.script["classifier"] = {
        **scripted_llm.script["classifier"],
        "confidence": 0.51,
    }
    pending = api_client.post("/intake", content=eml_corpus["happy_path"]).json()
    assert pending["status"] == "REVIEW_PENDING"
    assert pending["verification_result"] == "PASS"

    response = api_client.post(
        f"/review/{pending['case_ref']}",
        json={"action": "APPROVE", "note": "Evidence checked."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "COMMUNICATED"
    assert response.json()["posted"] is True
    assert fake_db.get_case_by_ref(pending["case_ref"])["outcome"] == "RESOLVED_IN_FULL"


def test_request_info_keeps_the_case_in_the_queue(api_client, eml_corpus, scripted_llm) -> None:
    scripted_llm.script["classifier"] = {
        **scripted_llm.script["classifier"],
        "confidence": 0.51,
    }
    pending = api_client.post("/intake", content=eml_corpus["happy_path"]).json()
    response = api_client.post(
        f"/review/{pending['case_ref']}",
        json={"action": "REQUEST_INFO", "note": "Please attach the receipt."},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "REVIEW_PENDING"
    assert "Please attach the receipt" in response.json()["letter"]


def test_policy_composer_simulates_then_compliance_applies(
    compliance_api_client, scripted_llm, fake_db, agent_ctx
) -> None:
    base = agent_ctx.pack("billing_error")
    fake_db.upsert_pack(
        category=base.category,
        version=base.version,
        yaml_text=base.source_yaml,
        is_active=True,
    )
    scripted_llm.script["composer"] = {
        "target_category": "billing_error",
        "summary": "Raise the automatic billing-error ceiling and notify the branch.",
        "edits": [
            {
                "path": "resolution.auto_approve_max_rm",
                "value": 2500,
                "reason": "Operator requested the higher review-free band.",
            },
            {
                "path": "workflow.notify_roles",
                "value": ["BRANCH_MANAGER"],
                "reason": "Keep the branch informed.",
            },
        ],
    }

    composed = compliance_api_client.post(
        "/policy/compose",
        json={
            "category": "billing_error",
            "request": "Auto-resolve billing errors under RM2,500 and notify the branch manager.",
        },
    )
    assert composed.status_code == 201, composed.text
    proposal = composed.json()
    assert proposal["status"] == "DRAFT"
    assert proposal["chain"]["ok"] is True
    assert "auto_approve_max_rm" in proposal["plain_english_diff"]

    applied = compliance_api_client.post(
        f"/policy/proposals/{proposal['id']}/apply",
        json={"note": "Simulation reviewed."},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "APPLIED"
    assert applied.json()["chain"]["ok"] is True
    assert fake_db.active_pack("billing_error")["version"] == base.version + 1


def test_investigator_cannot_compose_policy(api_client) -> None:
    response = api_client.post(
        "/policy/compose",
        json={"category": "billing_error", "request": "Raise the threshold to RM500."},
    )
    assert response.status_code == 403


def test_analytics_and_audit_surface_measured_state(api_client, eml_corpus) -> None:
    created = api_client.post("/intake", content=eml_corpus["happy_path"]).json()
    overview = api_client.get("/analytics/overview")
    assert overview.status_code == 200
    assert overview.json()["metrics"]["total_cases"] == 1
    assert overview.json()["metrics"]["resolved"] == 1

    audit = api_client.get(f"/audit/{created['case_ref']}/verify")
    assert audit.status_code == 200
    assert audit.json()["ok"] is True
    assert audit.json()["links"] >= 10


def test_customer_proactive_confirmation_files_the_dispute(
    api_client, fake_db
) -> None:
    fake_db.create_proactive_alert(
        token="synthetic-proactive-token",
        account_no="7142556890",
        txn_ref="TXN-88213",
        amount_rm=2450,
        merchant="TECHWORLD KL",
        occurred_at="2026-08-03T03:02:00+00:00",
        expires_at="2026-08-06T00:00:00+00:00",
    )
    visible = api_client.get("/proactive/synthetic-proactive-token")
    assert visible.status_code == 200
    assert "account_no" not in visible.json()

    response = api_client.post(
        "/proactive/synthetic-proactive-token/respond",
        json={"confirmed_not_mine": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["alert"]["status"] == "DISPUTED"
    assert response.json()["case"]["status"] == "COMMUNICATED"
