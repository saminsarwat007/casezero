"""The boardroom contract: agents may only say what the chain already recorded.

These tests exist because the boardroom is the most persuasive surface in the
product and therefore the easiest one to quietly turn into theatre. The rules
they hold down:

* A stage with no event produces no line.
* Every line's content traces to a recorded payload.
* The manual baseline decomposes to exactly the figure the case study states.
* The roster reports the model that will actually run, not the one we intended.
"""

from __future__ import annotations

from api.agents import roster
from api.agents.handoff import build_handoffs, build_value
from api.config import Settings
from api.llm.provider import ModelRouter


def _row(event_type: str, payload: dict, seq: int) -> dict:
    return {
        "event_type": event_type,
        "payload": payload,
        "seq": seq,
        "hash": f"hash-{seq:04d}",
        "created_at": "2026-08-11T10:00:00+00:00",
    }


def _full_case() -> dict[str, dict]:
    return {
        "INTAKE_EXTRACTED": _row(
            "INTAKE_EXTRACTED",
            {
                "account_no_masked": "******6890",
                "amount_rm": 2450.0,
                "merchant": "TECHWORLD KL",
                "language": "en",
                "documents": [{"filename": "statement.pdf", "method": "vision"}],
            },
            2,
        ),
        "CLASSIFIED": _row(
            "CLASSIFIED",
            {
                "category": "unauthorized_transaction",
                "confidence": 0.93,
                "reasoning": "Customer states the card never left their possession.",
                "source": "model",
            },
            3,
        ),
        "URGENCY_ASSIGNED": _row(
            "URGENCY_ASSIGNED",
            {
                "urgency": "High",
                "sla_working_days": 5,
                "sla_due": "2026-08-18T00:00:00+00:00",
                "because": "Amount is at or above RM5,000.",
                "citations": ["unauthorized_transaction.sla.High.working_days = 5"],
            },
            4,
        ),
        "VERIFICATION_COMPLETED": _row(
            "VERIFICATION_COMPLETED",
            {
                "result": "PASS",
                "reasons": ["Transaction reference found and the amount matches."],
                "evidence": [{"check": "account_exists"}, {"check": "amount_matches"}],
                "tool_calls": [{"tool": "verify_claim"}],
            },
            5,
        ),
        "GATE_DECISION": _row(
            "GATE_DECISION",
            {
                "action": "POST",
                "requires_dual_control": False,
                "reasons": ["Verification returned PASS."],
                "citations": ["unauthorized_transaction.resolution.auto_approve_max_rm = 3000"],
                "inputs": {"verification_result": "PASS", "amount_rm": 2450.0},
            },
            6,
        ),
        "JOURNAL_POSTED": _row(
            "JOURNAL_POSTED",
            {
                "entry_type": "REVERSAL",
                "amount_rm": 2450.0,
                "debit_account": "GL-1450-FRAUD-SUSPENSE",
                "credit_account_masked": "******6890",
                "balanced": True,
                "authorised_by": "ticket",
            },
            7,
        ),
        "DRAFT_LINTED": _row(
            "DRAFT_LINTED",
            {"summary": "6/6 passed", "repaired": False, "findings": [{"rule_id": "BNM_ACK"}]},
            8,
        ),
        "MESSAGE_SENT": _row(
            "MESSAGE_SENT", {"outcome": "RESOLVED_IN_FULL", "chars": 1400}, 9
        ),
    }


# ─── The baseline must decompose ────────────────────────────────────────────


def test_stage_baselines_sum_to_the_case_study_figure() -> None:
    """90 minutes is the number we quote on stage; it has to add up."""
    total = sum(minutes for _from, _to, minutes in roster.STAGE_ROLES.values())
    assert total == roster.BASELINE_MINUTES_TOTAL == 90


def test_every_pipeline_stage_has_a_speaker_and_a_baseline() -> None:
    for stage_id, _label, _event, _agent in roster.PIPELINE_STAGES:
        assert stage_id in roster.STAGE_ROLES, f"{stage_id} has no seat assigned"
        speaker, _listener, minutes = roster.STAGE_ROLES[stage_id]
        assert speaker in roster.SEATS_BY_ID
        assert minutes > 0


# ─── Agents may only speak from the chain ───────────────────────────────────


def test_a_stage_without_an_event_says_nothing() -> None:
    """The single rule that keeps the boardroom honest."""
    handoffs = build_handoffs({})
    assert handoffs, "stages should still be listed"
    for entry in handoffs:
        assert entry["spoken"] is False
        assert entry["says"] == ""
        assert entry["facts"] == []


def test_partial_run_only_speaks_for_landed_events() -> None:
    recorded = _full_case()
    for missing in ("JOURNAL_POSTED", "MESSAGE_SENT", "DRAFT_LINTED"):
        recorded.pop(missing)

    spoken = {h["stage"]: h["spoken"] for h in build_handoffs(recorded)}
    assert spoken["intake"] is True
    assert spoken["gate"] is True
    assert spoken["journal"] is False
    assert spoken["communicate"] is False


def test_handoff_content_comes_from_the_recorded_payload() -> None:
    handoffs = {h["stage"]: h for h in build_handoffs(_full_case())}

    assert "TECHWORLD KL" in handoffs["intake"]["says"]
    assert "RM2,450.00" in handoffs["intake"]["says"]

    assert "unauthorised transaction" in handoffs["classify"]["says"]
    assert "93%" in handoffs["classify"]["says"]

    assert "5 working days" in handoffs["sla"]["says"]
    assert "2026-08-18" in handoffs["sla"]["says"]

    assert "confirms the claim" in handoffs["verify"]["says"]
    assert "RM2,450.00" in handoffs["journal"]["says"]
    assert "Books balance" in handoffs["journal"]["says"]


def test_each_handoff_carries_its_chain_coordinates() -> None:
    """A bubble the viewer cannot trace back to a hash is decoration."""
    for entry in build_handoffs(_full_case()):
        if entry["spoken"]:
            assert entry["seq"] is not None
            assert entry["hash"]


def test_model_reasoning_is_attributed_not_stated_as_fact() -> None:
    classify = next(h for h in build_handoffs(_full_case()) if h["stage"] == "classify")
    labels = {fact["label"] for fact in classify["facts"]}
    assert "Model's reasoning" in labels
    # The model's prose must not leak into the spoken line as system truth.
    assert "never left their possession" not in classify["says"]


def test_keyword_fallback_is_disclosed_in_the_line() -> None:
    recorded = _full_case()
    recorded["CLASSIFIED"]["payload"]["source"] = "keyword_fallback"
    classify = next(h for h in build_handoffs(recorded) if h["stage"] == "classify")
    assert "keyword match" in classify["says"]


def test_verifier_line_states_it_uses_no_model() -> None:
    """The strongest claim in the product; it must survive a payload change."""
    verify = next(h for h in build_handoffs(_full_case()) if h["stage"] == "verify")
    values = " ".join(fact["value"] for fact in verify["facts"])
    assert "does not reason" in values


# ─── The refusal path ───────────────────────────────────────────────────────


def test_quarantine_gives_intake_a_refusal_line() -> None:
    recorded = {
        "STATUS_CHANGED": _row(
            "STATUS_CHANGED",
            {"from": "RECEIVED", "to": "QUARANTINED", "reason": "Injection blocked."},
            2,
        )
    }
    handoffs = {h["stage"]: h for h in build_handoffs(recorded)}
    intake = handoffs["intake"]
    assert intake["spoken"] is True
    assert intake.get("refused") is True
    assert "before any model read this" in intake["says"]
    # Everything downstream stays silent: nothing else ran.
    assert handoffs["classify"]["spoken"] is False
    assert handoffs["journal"]["spoken"] is False


# ─── Value arithmetic ───────────────────────────────────────────────────────


def test_value_only_claims_savings_for_stages_that_ran() -> None:
    recorded = _full_case()
    for missing in ("JOURNAL_POSTED", "MESSAGE_SENT"):
        recorded.pop(missing)
    handoffs = build_handoffs(recorded)

    value = build_value(handoffs, elapsed_seconds=30, baseline_total=90)
    # journal (12) and communicate (8) never ran, so 90 - 20 = 70.
    assert value["baseline_minutes_realised"] == 70
    assert value["stages_spoken"] == 5


def test_value_measures_elapsed_and_never_reports_negative_savings() -> None:
    handoffs = build_handoffs(_full_case())
    full = build_value(handoffs, elapsed_seconds=27, baseline_total=90)
    assert full["baseline_minutes_realised"] == 90
    assert full["minutes_saved"] == 89.5  # 90 - 0.45, rounded to one decimal
    assert full["elapsed_seconds"] == 27.0

    # A pathologically slow run must not invent a negative saving.
    slow = build_value(handoffs, elapsed_seconds=60 * 60 * 3, baseline_total=90)
    assert slow["minutes_saved"] == 0.0


# ─── The roster must report reality ─────────────────────────────────────────


def test_roster_reports_the_model_that_will_actually_run() -> None:
    router = ModelRouter(Settings(gemini_api_key="g-key", groq_api_key="q-key"))
    seats = {seat["id"]: seat for seat in roster.roster(router)["seats"]}

    assert seats["classifier"]["provider"] == "gemini"
    assert seats["communicator"]["provider"] == "groq"
    assert seats["classifier"]["fallback_from"] is None


def test_roster_discloses_a_fallback_instead_of_claiming_diversity() -> None:
    """No Groq key means one brain, and the panel has to say so."""
    router = ModelRouter(Settings(gemini_api_key="g-key", groq_api_key=None))
    seats = {seat["id"]: seat for seat in roster.roster(router)["seats"]}

    assert seats["communicator"]["provider"] == "gemini"
    assert seats["communicator"]["fallback_from"] == "groq"


def test_seats_touching_money_have_no_model() -> None:
    """Verifier and Resolver must never acquire a brain by accident."""
    seats = {seat.id: seat for seat in roster.SEATS}
    assert seats["verifier"].brain is None
    assert seats["resolver"].brain is None
    assert seats["kernel"].brain is None
    assert "verifier" not in ModelRouter.ROUTES
    assert "resolver" not in ModelRouter.ROUTES


def test_roster_survives_a_router_that_raises() -> None:
    class Broken:
        def describe(self, agent: str) -> dict:
            raise RuntimeError("provider registry unavailable")

    seats = roster.roster(Broken())["seats"]
    assert len(seats) == len(roster.SEATS)
    assert all(seat["provider"] is None for seat in seats)
