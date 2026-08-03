"""Shared fixtures for the kernel test suite.

The tests run against the *shipped* rule pack rather than a hand-written fixture.
That is deliberate: a suite that passes against a toy pack proves the code works,
while a suite that passes against `rule_packs/unauthorized_transaction.yaml` proves
the policy we actually demo is well-formed. When a pack is edited, these break.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import pytest
import yaml

from api.agents.base import AgentContext
from api.kernel.chain import ChainEvent, ChainVerdict
from api.kernel.chain import append as append_link
from api.kernel.chain import verify_chain
from api.kernel.rules import RULE_PACKS_DIR, RulePack, load_all, load_yaml
from api.llm.provider import LLMError, LLMResult
from api.mcp_tools.gateway import InProcessGateway

UNAUTHORIZED_YAML = RULE_PACKS_DIR / "unauthorized_transaction.yaml"
EML_CORPUS_DIR = Path(__file__).parent / "fixtures" / "eml"


def _set_path(data: dict[str, Any], dotted: str, value: Any) -> None:
    node: Any = data
    segments = dotted.split(".")
    for segment in segments[:-1]:
        node = node.setdefault(segment, {})
    node[segments[-1]] = value


def _del_path(data: dict[str, Any], dotted: str) -> None:
    node: Any = data
    segments = dotted.split(".")
    for segment in segments[:-1]:
        node = node.get(segment)
        if not isinstance(node, dict):
            return
    node.pop(segments[-1], None)


@pytest.fixture(scope="session")
def shipped_yaml() -> str:
    return UNAUTHORIZED_YAML.read_text()


@pytest.fixture
def pack(shipped_yaml: str) -> RulePack:
    """The real unauthorized_transaction pack, parsed and validated."""
    return load_yaml(shipped_yaml)


@pytest.fixture
def make_raw(shipped_yaml: str) -> Callable[..., dict[str, Any]]:
    """Produce a variant of the shipped pack as a raw dict, for validation tests."""

    base = yaml.safe_load(shipped_yaml)

    def _make(
        changes: Mapping[str, Any] | None = None,
        drop: Iterable[str] = (),
    ) -> dict[str, Any]:
        data = copy.deepcopy(base)
        for dotted, value in (changes or {}).items():
            _set_path(data, dotted, value)
        for dotted in drop:
            _del_path(data, dotted)
        return data

    return _make


@pytest.fixture
def make_pack(make_raw: Callable[..., dict[str, Any]]) -> Callable[..., RulePack]:
    """Produce a validated variant of the shipped pack.

    Used where a test needs a policy the demo pack does not exercise — for example
    an auto-approval ceiling below the dual-control threshold.
    """

    def _make(
        changes: Mapping[str, Any] | None = None,
        drop: Iterable[str] = (),
    ) -> RulePack:
        return load_yaml(yaml.safe_dump(make_raw(changes, drop), sort_keys=False))

    return _make


# ─── An in-memory bank ──────────────────────────────────────────────────────


class FakeBank:
    """Implements the slice of `db.Database` the MCP tools depend on.

    Small enough to read in one sitting, which is the point: when a tool test
    fails, the failure is about the tool rather than about Supabase.
    """

    CASE_ID = "c0000000-0000-0000-0000-000000000001"
    CUSTOMER_ID = "a0000000-0000-0000-0000-000000000001"
    ACCOUNT_NO = "7142556890"

    def __init__(self) -> None:
        self.customers = {
            self.CUSTOMER_ID: {
                "id": self.CUSTOMER_ID,
                "name": "Nurul Aisyah binti Rahman",
                "nric_last4": "5521",
                "email": "nurul@example.my",
                "segment": "retail",
                "risk_flags": [],
                "joined_at": "2019-04-12T00:00:00+00:00",
            }
        }
        self.accounts = {
            self.ACCOUNT_NO: {
                "account_no": self.ACCOUNT_NO,
                "customer_id": self.CUSTOMER_ID,
                "product_type": "savings",
                "balance_rm": 8412.55,
                "status": "ACTIVE",
                "opened_at": "2019-04-12T00:00:00+00:00",
            }
        }
        self.transactions = {
            "TXN-88213": {
                "txn_ref": "TXN-88213",
                "account_no": self.ACCOUNT_NO,
                "merchant": "TECHWORLD KL",
                "amount_rm": 2450.00,
                "direction": "DEBIT",
                "channel": "online",
                "country": "MY",
                "posted_at": "2026-03-14T11:02:00+00:00",
                "is_disputed": False,
            }
        }
        self.journal: list[dict[str, Any]] = []
        self.cases: list[dict[str, Any]] = []

    # Ledger backend
    def get_account(self, account_no: str):
        return self.accounts.get(account_no)

    def get_transaction(self, txn_ref: str):
        return self.transactions.get(txn_ref)

    def get_transactions(self, account_no: str, *, limit: int = 50):
        rows = [t for t in self.transactions.values() if t["account_no"] == account_no]
        return sorted(rows, key=lambda t: t["posted_at"], reverse=True)[:limit]

    def get_journal(self, case_id: str):
        return [e for e in self.journal if e["case_id"] == case_id]

    def post_journal(self, **fields: Any):
        entry = {"id": f"j{len(self.journal) + 1}", **fields}
        self.journal.append(entry)
        return entry

    def mark_disputed(self, txn_ref: str) -> None:
        if txn_ref in self.transactions:
            self.transactions[txn_ref]["is_disputed"] = True

    # CRM backend
    def get_customer(self, customer_id: str):
        return self.customers.get(customer_id)

    def list_cases(self, *, status: str | None = None, limit: int = 200):
        rows = [c for c in self.cases if status is None or c.get("status") == status]
        return rows[:limit]


@pytest.fixture
def bank() -> FakeBank:
    return FakeBank()


# ─── A whole bank, including the audit chain ────────────────────────────────


class FakeDatabase(FakeBank):
    """`db.Database` in memory, with a *real* hash chain.

    The chain is not simulated: `append_event` calls the same `build_event` the
    production client calls, so a test that asserts `verify_chain` holds is
    asserting something about the shipped hashing code, not about a stub.
    """

    def __init__(self) -> None:
        super().__init__()
        self.events: dict[str, list[ChainEvent]] = {}
        self.policy_events: dict[str, list[ChainEvent]] = {}
        self.rule_pack_rows: list[dict[str, Any]] = []
        self.policy_proposals: list[dict[str, Any]] = []
        self.proactive_alerts: list[dict[str, Any]] = []
        self.quarantined: list[dict[str, Any]] = []
        self.llm_calls: list[dict[str, Any]] = []
        self.settings = {
            "id": "primary",
            "bank_display_name": "MYBank Berhad",
            "complaints_email": "complaints@mybank.com.my",
            "timezone": "Asia/Kuala_Lumpur",
            "sla_warning_hours": 24,
            "default_workspace": "/simple",
            "wajar_enabled": True,
            "automatic_resolution_enabled": True,
            "updated_by": None,
            "updated_at": "2026-08-03T00:00:00+00:00",
        }
        self.settings_events: list[ChainEvent] = []
        self.assistant_receipts: list[dict[str, Any]] = []
        self._case_seq = 0

    # ─── Cases ──────────────────────────────────────────────────────────────

    def next_case_ref(self) -> str:
        self._case_seq += 1
        return f"MYB-2026-{self._case_seq:06d}"

    def create_case(self, **fields: Any) -> dict[str, Any]:
        fields.setdefault("case_ref", self.next_case_ref())
        case = {
            "id": f"c0000000-0000-0000-0000-{len(self.cases) + 1:012d}",
            "status": "RECEIVED",
            "outcome": "PENDING",
            "created_at": "2026-08-03T00:00:00+00:00",
            **fields,
        }
        self.cases.append(case)
        return case

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        return next((c for c in self.cases if c["id"] == case_id), None)

    def get_case_by_ref(self, case_ref: str) -> dict[str, Any] | None:
        return next((c for c in self.cases if c.get("case_ref") == case_ref), None)

    def get_case_by_token(self, track_token: str) -> dict[str, Any] | None:
        return next((c for c in self.cases if c.get("track_token") == track_token), None)

    def update_case(self, case_id: str, **fields: Any) -> dict[str, Any]:
        case = self.get_case(case_id)
        if case is None:
            raise KeyError(f"No such case {case_id}")
        case.update(fields)
        return case

    # ─── The chain ──────────────────────────────────────────────────────────

    def append_event(
        self, case_id: str, event_type: str, actor: str, payload: dict[str, Any]
    ) -> ChainEvent:
        events = self.events.setdefault(case_id, [])
        event = append_link(events, event_type, actor, payload)
        events.append(event)
        return event

    def get_events(self, case_id: str) -> list[ChainEvent]:
        return list(self.events.get(case_id, []))

    def verify_case_chain(self, case_id: str) -> ChainVerdict:
        return verify_chain(self.get_events(case_id))

    # ─── Security + telemetry ───────────────────────────────────────────────

    def quarantine_case(
        self, *, case_id: str | None, reason: str, detector: str, raw_excerpt: str
    ) -> dict[str, Any]:
        row = {
            "case_id": case_id,
            "reason": reason,
            "detector": detector,
            "raw_excerpt": raw_excerpt[:4000],
        }
        self.quarantined.append(row)
        return row

    def log_llm_call(self, result: Any, case_id: str | None = None) -> None:
        self.llm_calls.append(
            {"case_id": case_id, "agent": result.agent, "cost_rm": result.cost_rm}
        )

    def case_cost_rm(self, case_id: str) -> float:
        return sum(
            float(row["cost_rm"])
            for row in self.llm_calls
            if row.get("case_id") == case_id
        )

    # ─── Rule packs + governed proposals ──────────────────────────────────

    def active_pack(self, category: str) -> dict[str, Any] | None:
        return next(
            (
                row
                for row in self.rule_pack_rows
                if row["category"] == category and row.get("is_active")
            ),
            None,
        )

    def upsert_pack(
        self,
        *,
        category: str,
        version: int,
        yaml_text: str,
        is_active: bool = False,
        change_summary: str | None = None,
        parent_version: int | None = None,
        created_by: str = "system",
    ) -> dict[str, Any]:
        row = next(
            (
                item
                for item in self.rule_pack_rows
                if item["category"] == category and item["version"] == version
            ),
            None,
        )
        values = {
            "id": row["id"] if row else f"rp-{category}-{version}",
            "category": category,
            "version": version,
            "yaml": yaml_text,
            "is_active": is_active,
            "change_summary": change_summary,
            "parent_version": parent_version,
            "created_by": created_by,
        }
        if row:
            row.update(values)
            return row
        self.rule_pack_rows.append(values)
        return values

    def activate_pack(self, category: str, version: int) -> None:
        found = False
        for row in self.rule_pack_rows:
            if row["category"] == category:
                row["is_active"] = row["version"] == version
                found = found or row["version"] == version
        if not found:
            raise KeyError(f"No pack {category} v{version}")

    def list_packs(self, category: str | None = None) -> list[dict[str, Any]]:
        return [
            row for row in self.rule_pack_rows if category is None or row["category"] == category
        ]

    def create_policy_proposal(self, **fields: Any) -> dict[str, Any]:
        row = {
            "id": f"pp-{len(self.policy_proposals) + 1}",
            "status": "DRAFT",
            **fields,
        }
        self.policy_proposals.append(row)
        return row

    def get_policy_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        return next((row for row in self.policy_proposals if row["id"] == proposal_id), None)

    def list_policy_proposals(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.policy_proposals[:limit]

    def update_policy_proposal(self, proposal_id: str, **fields: Any) -> dict[str, Any]:
        row = self.get_policy_proposal(proposal_id)
        if row is None:
            raise KeyError(proposal_id)
        row.update(fields)
        return row

    def append_policy_event(
        self,
        proposal_id: str,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
    ) -> ChainEvent:
        events = self.policy_events.setdefault(proposal_id, [])
        event = append_link(events, event_type, actor, payload)
        events.append(event)
        return event

    def get_policy_events(self, proposal_id: str) -> list[ChainEvent]:
        return list(self.policy_events.get(proposal_id, []))

    def verify_policy_chain(self, proposal_id: str) -> ChainVerdict:
        return verify_chain(self.get_policy_events(proposal_id))

    def record_eval_run(self, **fields: Any) -> dict[str, Any]:
        return {"id": "eval-1", **fields}

    def list_eval_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        return []

    # ─── Stakeholder controls + Wajar receipts ────────────────────────────

    def get_stakeholder_settings(self) -> dict[str, Any]:
        return dict(self.settings)

    def update_stakeholder_settings(self, **fields: Any) -> dict[str, Any]:
        self.settings.update(fields)
        return dict(self.settings)

    def append_settings_event(
        self, event_type: str, actor: str, payload: dict[str, Any]
    ) -> ChainEvent:
        event = append_link(self.settings_events, event_type, actor, payload)
        self.settings_events.append(event)
        return event

    def get_settings_events(self) -> list[ChainEvent]:
        return list(self.settings_events)

    def verify_settings_chain(self) -> ChainVerdict:
        return verify_chain(self.settings_events)

    def record_assistant_receipt(self, **fields: Any) -> dict[str, Any]:
        row = {"created_at": "2026-08-03T00:00:00+00:00", **fields}
        self.assistant_receipts.append(row)
        return row

    def list_assistant_receipts(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(reversed(self.assistant_receipts))[:limit]

    def rpc(self, name: str, params: dict[str, Any] | None = None) -> Any:
        if name == "dashboard_metrics":
            total = len(self.cases)
            resolved = sum(
                case.get("status") in {"FINANCIALLY_RESOLVED", "COMMUNICATED", "CLOSED"}
                for case in self.cases
            )
            return {
                "total_cases": total,
                "resolved": resolved,
                "automation_rate": resolved / total if total else 0,
                "cost_per_case_rm": 0,
            }
        if name in {"category_volumes", "investigator_workload", "detect_fraud_rings"}:
            return []
        raise KeyError(name)

    def list_quarantine(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.quarantined[:limit]

    def create_proactive_alert(self, **fields: Any) -> dict[str, Any]:
        row = {"id": f"pa-{len(self.proactive_alerts) + 1}", "status": "PENDING", **fields}
        self.proactive_alerts.append(row)
        return row

    def get_proactive_alert(self, token: str) -> dict[str, Any] | None:
        return next((row for row in self.proactive_alerts if row["token"] == token), None)

    def update_proactive_alert(self, alert_id: str, **fields: Any) -> dict[str, Any]:
        row = next(item for item in self.proactive_alerts if item["id"] == alert_id)
        row.update(fields)
        return row


@pytest.fixture
def fake_db() -> FakeDatabase:
    return FakeDatabase()


@pytest.fixture(scope="session")
def eml_corpus() -> dict[str, bytes]:
    """Checked-in RFC822 messages, keyed by filename stem.

    Reading real ``.eml`` bytes catches parser regressions that an
    ``EmailMessage`` constructed inside the same test process can conceal.
    """
    messages = {path.stem: path.read_bytes() for path in sorted(EML_CORPUS_DIR.glob("*.eml"))}
    if not messages:
        raise RuntimeError(f"No .eml fixtures found in {EML_CORPUS_DIR}")
    return messages


# ─── A model that says exactly what the test wants it to say ────────────────


class ScriptedProvider:
    """Stands in for Gemini. Records every prompt it was given.

    Recording matters as much as responding: several tests assert on what was
    *not* in the prompt — no account number, no NRIC — which is how the PII
    boundary is proven rather than described.
    """

    name = "scripted"

    def __init__(self, script: dict[str, Any] | None = None) -> None:
        self.script = script or {}
        self.prompts: list[tuple[str, str]] = []  # (agent, prompt)
        self.systems: list[str] = []

    @property
    def supports_vision(self) -> bool:
        return True

    def prompt_for(self, agent: str) -> str:
        return next((p for a, p in self.prompts if a == agent), "")

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        schema: Any = None,
        images: Any = None,
        temperature: float = 0.1,
        model: str | None = None,
        agent: str = "unknown",
        **_: Any,
    ) -> LLMResult:
        self.prompts.append((agent, prompt))
        if system:
            self.systems.append(system)

        entry = self.script.get(agent)
        if entry is None:
            raise LLMError(f"ScriptedProvider has no script for agent {agent!r}")
        if callable(entry):
            entry = entry(prompt)
        if isinstance(entry, Exception):
            raise entry

        return LLMResult(
            text=json.dumps(entry),
            provider=self.name,
            model=model or "scripted-1",
            agent=agent,
            tokens_in=len(prompt) // 4,
            tokens_out=64,
            latency_ms=1,
            cost_rm=0.000123,
            data=entry,
        )


class ScriptedRouter:
    """Routes every agent to the same scripted provider."""

    def __init__(self, provider: ScriptedProvider) -> None:
        self.provider = provider

    def for_agent(self, agent: str) -> tuple[ScriptedProvider, str]:
        return self.provider, "scripted-1"


# ─── The complaint the demo is built around ─────────────────────────────────

AHMAD_BODY = """Dear Sir/Madam,

I am writing to dispute a transaction on my savings account 7142556890.

On 14 March a debit of RM2,450.00 was taken by TECHWORLD KL, reference
TXN-88213. I did not make this purchase and I have never shopped with that
merchant. My card has been in my possession the whole time.

My account balance is now RM8,412.55 and I need this amount returned.

My NRIC is 880412-14-5521 if you need to verify my identity.

Thank you,
Ahmad bin Ismail
"""


def build_eml(
    *,
    subject: str = "Unauthorised transaction on my account",
    body: str = AHMAD_BODY,
    from_email: str = "ahmad.ismail@example.my",
    date: str = "Wed, 29 Jul 2026 09:15:00 +0800",
    html: str | None = None,
    attachments: Iterable[tuple[str, str, bytes]] = (),
) -> bytes:
    """Build an RFC822 message the way an inbox would deliver one."""
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"Ahmad bin Ismail <{from_email}>"
    message["To"] = "complaints@mybank.com.my"
    message["Date"] = date
    message.set_content(body)
    if html is not None:
        message.add_alternative(html, subtype="html")
    for filename, mime_type, content in attachments:
        maintype, _, subtype = mime_type.partition("/")
        message.add_attachment(
            content, maintype=maintype, subtype=subtype, filename=filename
        )
    return message.as_bytes()


def html_only_eml(html: str, *, subject: str = "Dispute") -> bytes:
    """An HTML-only message — the shape a hidden-instruction attack arrives in."""
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = "customer@example.my"
    message["To"] = "complaints@mybank.com.my"
    message["Date"] = "Wed, 29 Jul 2026 09:15:00 +0800"
    message.set_content(html, subtype="html")
    return message.as_bytes()


# ─── Scripts ────────────────────────────────────────────────────────────────

CASE_REF = re.compile(r"MYB-\d{4}-\d{6}")


def _draft(prompt: str) -> dict[str, Any]:
    """The two explanatory paragraphs a model is asked for.

    Notably it writes no case reference, no date and no contact address — those
    are the kernel's, and the assembled letter must carry them anyway.
    """
    reference = CASE_REF.search(prompt)
    return {
        "subject": f"Your complaint {reference.group(0) if reference else ''}",
        "plain_summary": "We looked into the payment you told us about and agree "
                         "it was not one you made. The money is going back to your "
                         "account.",
        "formal_paragraph": "Our investigation matched the disputed debit against "
                            "the transaction record on your account and found no "
                            "evidence of authorisation by you.",
        "plain_summary_ms": "Kami telah menyiasat pembayaran yang anda laporkan dan "
                            "bersetuju ia bukan transaksi anda.",
        "formal_paragraph_ms": "Siasatan kami memadankan debit yang dipertikaikan "
                               "dengan rekod transaksi akaun anda.",
    }


HAPPY_SCRIPT: dict[str, Any] = {
    "intake": {
        "summary": "Customer disputes a RM2,450.00 debit to TECHWORLD KL that they "
                   "say they did not authorise.",
        "amount_rm": 2450.0,
        "txn_refs": ["TXN-88213"],
        "merchant": "TECHWORLD KL",
        "language": "en",
        "contains_instructions": False,
    },
    "classifier": {
        "category": "unauthorized_transaction",
        "confidence": 0.94,
        "reasoning": "The customer states a card debit they did not authorise and "
                     "quotes the transaction reference.",
        "amount_rm": 2450.0,
        "txn_ref": "TXN-88213",
        "merchant": "TECHWORLD KL",
    },
    "communicator": _draft,
}


@pytest.fixture
def scripted_llm() -> ScriptedProvider:
    return ScriptedProvider(dict(HAPPY_SCRIPT))


@pytest.fixture
def agent_ctx(fake_db: FakeDatabase, scripted_llm: ScriptedProvider) -> AgentContext:
    """A fully wired pipeline that touches no network.

    Real rule packs, the real in-process MCP tools, the real kernel — only the
    bank and the model are stand-ins.
    """
    return AgentContext(
        db=fake_db,
        gateway=InProcessGateway(fake_db),
        router=ScriptedRouter(scripted_llm),
        packs=load_all(RULE_PACKS_DIR),
        now=datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc),
    )
