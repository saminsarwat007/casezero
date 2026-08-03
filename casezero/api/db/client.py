"""Data access over PostgREST.

Two clients, deliberately separated:

* **service role** — the kernel and agents. The only writer in the system.
* **user JWT** — dashboard reads, where RLS decides what is visible. An
  investigator's query is filtered by Postgres, not by our UI.

`append_event` is the important function here: it is the single chokepoint through
which every state change passes, and it is what makes the audit chain continuous
rather than a best-effort log.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Sequence

from supabase import Client, create_client

from api.config import Settings, get_settings
from api.kernel.chain import ChainEvent, ChainVerdict, build_event, verify_chain

GENESIS = "0" * 64


@lru_cache
def service_client() -> Client:
    """Privileged client. Bypasses RLS — only the kernel and agents may use it."""
    settings = get_settings()
    settings.require("supabase_url", "supabase_service_role_key")
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def user_client(access_token: str, settings: Settings | None = None) -> Client:
    """Client acting as a signed-in user, so every read is filtered by RLS."""
    cfg = settings or get_settings()
    cfg.require("supabase_url", "supabase_anon_key")
    client = create_client(cfg.supabase_url, cfg.supabase_anon_key)
    client.postgrest.auth(access_token)
    return client


def anon_client(settings: Settings | None = None) -> Client:
    cfg = settings or get_settings()
    cfg.require("supabase_url", "supabase_anon_key")
    return create_client(cfg.supabase_url, cfg.supabase_anon_key)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Thin, explicit repository. No ORM — PostgREST is the transport."""

    def __init__(self, client: Client | None = None) -> None:
        self.sb = client or service_client()

    # ─── Cases ──────────────────────────────────────────────────────────────

    def next_case_ref(self) -> str:
        """MYB-2026-000123. Sequential and human-quotable on a phone call."""
        year = datetime.now(timezone.utc).year
        prefix = f"MYB-{year}-"
        rows = (
            self.sb.table("cases")
            .select("case_ref")
            .like("case_ref", f"{prefix}%")
            .order("case_ref", desc=True)
            .limit(1)
            .execute()
            .data
        )
        nxt = int(rows[0]["case_ref"].removeprefix(prefix)) + 1 if rows else 1
        return f"{prefix}{nxt:06d}"

    def create_case(self, **fields: Any) -> dict[str, Any]:
        fields.setdefault("case_ref", self.next_case_ref())
        return self.sb.table("cases").insert(fields).execute().data[0]

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        rows = self.sb.table("cases").select("*").eq("id", case_id).limit(1).execute().data
        return rows[0] if rows else None

    def get_case_by_ref(self, case_ref: str) -> dict[str, Any] | None:
        rows = self.sb.table("cases").select("*").eq("case_ref", case_ref).limit(1).execute().data
        return rows[0] if rows else None

    def get_case_by_token(self, track_token: str) -> dict[str, Any] | None:
        """Customer PWA lookup — a magic link carries no session."""
        rows = (
            self.sb.table("cases").select("*").eq("track_token", track_token).limit(1).execute().data
        )
        return rows[0] if rows else None

    def update_case(self, case_id: str, **fields: Any) -> dict[str, Any]:
        return self.sb.table("cases").update(fields).eq("id", case_id).execute().data[0]

    def list_cases(
        self,
        *,
        status: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        query = self.sb.table("cases").select("*").order("created_at", desc=True).limit(limit)
        if status:
            query = query.eq("status", status)
        return query.execute().data

    # ─── The audit chain ────────────────────────────────────────────────────

    def _last_event(self, case_id: str) -> dict[str, Any] | None:
        rows = (
            self.sb.table("case_events")
            .select("seq, hash")
            .eq("case_id", case_id)
            .order("seq", desc=True)
            .limit(1)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def append_event(
        self,
        case_id: str,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
    ) -> ChainEvent:
        """Append one link to a case's chain.

        Every state change in CaseZero goes through here. The unique (case_id, seq)
        constraint means a concurrent double-append fails loudly instead of forking
        the chain, and the database's own rules forbid updating or deleting what
        this writes.
        """
        last = self._last_event(case_id)
        seq = (last["seq"] + 1) if last else 1
        prev_hash = last["hash"] if last else GENESIS

        event = build_event(seq, event_type, actor, payload, prev_hash)
        self.sb.table("case_events").insert(
            {
                "case_id": case_id,
                "seq": event.seq,
                "event_type": event.event_type,
                "actor": event.actor,
                "payload": event.payload,
                "prev_hash": event.prev_hash,
                "hash": event.hash,
            }
        ).execute()
        return event

    def get_events(self, case_id: str) -> list[ChainEvent]:
        rows = (
            self.sb.table("case_events")
            .select("seq, event_type, actor, payload, prev_hash, hash")
            .eq("case_id", case_id)
            .order("seq")
            .execute()
            .data
        )
        return [
            ChainEvent(
                seq=r["seq"],
                event_type=r["event_type"],
                actor=r["actor"],
                payload=r["payload"],
                prev_hash=r["prev_hash"],
                hash=r["hash"],
            )
            for r in rows
        ]

    def verify_case_chain(self, case_id: str) -> ChainVerdict:
        """Recompute a case's chain and report the first broken link, if any."""
        return verify_chain(self.get_events(case_id))

    # ─── Ledger ─────────────────────────────────────────────────────────────

    def post_journal(
        self,
        *,
        case_id: str,
        entry_type: str,
        debit_account: str,
        credit_account: str,
        amount_rm: float,
        narrative: str,
        posted_by: str,
        dual_control_by: str | None = None,
    ) -> dict[str, Any]:
        """Insert a double-entry pair.

        Authorisation is *not* decided here — kernel/gates.py has already refused
        anything unverified or over threshold. This function only writes.
        """
        return (
            self.sb.table("journal_entries")
            .insert(
                {
                    "case_id": case_id,
                    "entry_type": entry_type,
                    "debit_account": debit_account,
                    "credit_account": credit_account,
                    "amount_rm": amount_rm,
                    "narrative": narrative,
                    "posted_by": posted_by,
                    "dual_control_by": dual_control_by,
                }
            )
            .execute()
            .data[0]
        )

    def get_journal(self, case_id: str) -> list[dict[str, Any]]:
        return (
            self.sb.table("journal_entries")
            .select("*")
            .eq("case_id", case_id)
            .order("posted_at")
            .execute()
            .data
        )

    # ─── Mock core banking (also what the MCP servers read) ─────────────────

    def get_account(self, account_no: str) -> dict[str, Any] | None:
        rows = (
            self.sb.table("accounts").select("*").eq("account_no", account_no).limit(1).execute().data
        )
        return rows[0] if rows else None

    def get_transaction(self, txn_ref: str) -> dict[str, Any] | None:
        rows = (
            self.sb.table("transactions").select("*").eq("txn_ref", txn_ref).limit(1).execute().data
        )
        return rows[0] if rows else None

    def get_transactions(
        self,
        account_no: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return (
            self.sb.table("transactions")
            .select("*")
            .eq("account_no", account_no)
            .order("posted_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        rows = (
            self.sb.table("customers").select("*").eq("id", customer_id).limit(1).execute().data
        )
        return rows[0] if rows else None

    def mark_disputed(self, txn_ref: str) -> None:
        self.sb.table("transactions").update({"is_disputed": True}).eq("txn_ref", txn_ref).execute()

    # ─── Rule packs ─────────────────────────────────────────────────────────

    def active_pack(self, category: str) -> dict[str, Any] | None:
        rows = (
            self.sb.table("rule_packs")
            .select("*")
            .eq("category", category)
            .eq("is_active", True)
            .limit(1)
            .execute()
            .data
        )
        return rows[0] if rows else None

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
        return (
            self.sb.table("rule_packs")
            .upsert(
                {
                    "category": category,
                    "version": version,
                    "yaml": yaml_text,
                    "is_active": is_active,
                    "change_summary": change_summary,
                    "parent_version": parent_version,
                    "created_by": created_by,
                },
                on_conflict="category,version",
            )
            .execute()
            .data[0]
        )

    def activate_pack(self, category: str, version: int) -> None:
        """Atomically swap the active version through a Postgres function."""
        self.sb.rpc(
            "activate_rule_pack",
            {"p_category": category, "p_version": version},
        ).execute()

    def list_packs(self, category: str | None = None) -> list[dict[str, Any]]:
        query = self.sb.table("rule_packs").select("*").order("category").order(
            "version", desc=True
        )
        if category:
            query = query.eq("category", category)
        return query.execute().data

    # ─── Policy Composer governance ───────────────────────────────────────

    def create_policy_proposal(self, **fields: Any) -> dict[str, Any]:
        return self.sb.table("policy_proposals").insert(fields).execute().data[0]

    def get_policy_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        rows = (
            self.sb.table("policy_proposals")
            .select("*")
            .eq("id", proposal_id)
            .limit(1)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def list_policy_proposals(self, limit: int = 100) -> list[dict[str, Any]]:
        return (
            self.sb.table("policy_proposals")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )

    def update_policy_proposal(self, proposal_id: str, **fields: Any) -> dict[str, Any]:
        return (
            self.sb.table("policy_proposals")
            .update(fields)
            .eq("id", proposal_id)
            .execute()
            .data[0]
        )

    def append_policy_event(
        self,
        proposal_id: str,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
    ) -> ChainEvent:
        rows = (
            self.sb.table("policy_events")
            .select("seq,hash")
            .eq("proposal_id", proposal_id)
            .order("seq", desc=True)
            .limit(1)
            .execute()
            .data
        )
        seq = int(rows[0]["seq"]) + 1 if rows else 1
        prev_hash = str(rows[0]["hash"]) if rows else GENESIS
        event = build_event(seq, event_type, actor, payload, prev_hash)
        self.sb.table("policy_events").insert(
            {
                "proposal_id": proposal_id,
                "seq": event.seq,
                "event_type": event.event_type,
                "actor": event.actor,
                "payload": event.payload,
                "prev_hash": event.prev_hash,
                "hash": event.hash,
            }
        ).execute()
        return event

    def get_policy_events(self, proposal_id: str) -> list[ChainEvent]:
        rows = (
            self.sb.table("policy_events")
            .select("seq,event_type,actor,payload,prev_hash,hash")
            .eq("proposal_id", proposal_id)
            .order("seq")
            .execute()
            .data
        )
        return [
            ChainEvent(
                seq=row["seq"],
                event_type=row["event_type"],
                actor=row["actor"],
                payload=row["payload"],
                prev_hash=row["prev_hash"],
                hash=row["hash"],
            )
            for row in rows
        ]

    def verify_policy_chain(self, proposal_id: str) -> ChainVerdict:
        return verify_chain(self.get_policy_events(proposal_id))

    # ─── Telemetry ──────────────────────────────────────────────────────────

    def log_llm_call(self, result: Any, case_id: str | None = None) -> None:
        """Record a model call so cost-per-case is measured, never estimated."""
        self.sb.table("llm_calls").insert(
            {
                "case_id": case_id,
                "agent": result.agent,
                "provider": result.provider,
                "model": result.model,
                "tokens_in": result.tokens_in,
                "tokens_out": result.tokens_out,
                "latency_ms": result.latency_ms,
                "cost_rm": round(result.cost_rm, 8),
                "ok": True,
            }
        ).execute()

    def case_cost_rm(self, case_id: str) -> float:
        rows = self.sb.table("llm_calls").select("cost_rm").eq("case_id", case_id).execute().data
        return sum(float(r["cost_rm"]) for r in rows)

    # ─── Evaluation + analytics ───────────────────────────────────────────

    def record_eval_run(self, **fields: Any) -> dict[str, Any]:
        return self.sb.table("eval_runs").insert(fields).execute().data[0]

    def list_eval_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        return (
            self.sb.table("eval_runs")
            .select("*")
            .order("run_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )

    # ─── Stakeholder controls + Wajar receipts ────────────────────────────

    def get_stakeholder_settings(self) -> dict[str, Any]:
        rows = (
            self.sb.table("stakeholder_settings")
            .select("*")
            .eq("id", "primary")
            .limit(1)
            .execute()
            .data
        )
        if not rows:
            raise RuntimeError("The stakeholder control register is not initialised.")
        return rows[0]

    def update_stakeholder_settings(self, **fields: Any) -> dict[str, Any]:
        return (
            self.sb.table("stakeholder_settings")
            .update({**fields, "updated_at": _now()})
            .eq("id", "primary")
            .execute()
            .data[0]
        )

    def append_settings_event(
        self,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
    ) -> ChainEvent:
        rows = (
            self.sb.table("settings_events")
            .select("seq,hash")
            .order("seq", desc=True)
            .limit(1)
            .execute()
            .data
        )
        seq = int(rows[0]["seq"]) + 1 if rows else 1
        prev_hash = str(rows[0]["hash"]) if rows else GENESIS
        event = build_event(seq, event_type, actor, payload, prev_hash)
        self.sb.table("settings_events").insert(
            {
                "seq": event.seq,
                "event_type": event.event_type,
                "actor": event.actor,
                "payload": event.payload,
                "prev_hash": event.prev_hash,
                "hash": event.hash,
            }
        ).execute()
        return event

    def get_settings_events(self) -> list[ChainEvent]:
        rows = (
            self.sb.table("settings_events")
            .select("seq,event_type,actor,payload,prev_hash,hash")
            .order("seq")
            .execute()
            .data
        )
        return [
            ChainEvent(
                seq=row["seq"],
                event_type=row["event_type"],
                actor=row["actor"],
                payload=row["payload"],
                prev_hash=row["prev_hash"],
                hash=row["hash"],
            )
            for row in rows
        ]

    def verify_settings_chain(self) -> ChainVerdict:
        return verify_chain(self.get_settings_events())

    def record_assistant_receipt(self, **fields: Any) -> dict[str, Any]:
        return self.sb.table("assistant_receipts").insert(fields).execute().data[0]

    def list_assistant_receipts(self, limit: int = 50) -> list[dict[str, Any]]:
        return (
            self.sb.table("assistant_receipts")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )

    def rpc(self, name: str, params: dict[str, Any] | None = None) -> Any:
        return self.sb.rpc(name, params or {}).execute().data

    # ─── Proactive disputes ────────────────────────────────────────────────

    def create_proactive_alert(self, **fields: Any) -> dict[str, Any]:
        return self.sb.table("proactive_alerts").insert(fields).execute().data[0]

    def get_proactive_alert(self, token: str) -> dict[str, Any] | None:
        rows = (
            self.sb.table("proactive_alerts")
            .select("*")
            .eq("token", token)
            .limit(1)
            .execute()
            .data
        )
        return rows[0] if rows else None

    def update_proactive_alert(self, alert_id: str, **fields: Any) -> dict[str, Any]:
        return (
            self.sb.table("proactive_alerts")
            .update(fields)
            .eq("id", alert_id)
            .execute()
            .data[0]
        )

    # ─── Security ───────────────────────────────────────────────────────────

    def quarantine_case(
        self,
        *,
        case_id: str | None,
        reason: str,
        detector: str,
        raw_excerpt: str,
    ) -> dict[str, Any]:
        """Preserve the hostile input rather than dropping it.

        A blocked injection that leaves no artefact is indistinguishable from an
        injection that was never noticed.
        """
        return (
            self.sb.table("quarantine")
            .insert(
                {
                    "case_id": case_id,
                    "reason": reason,
                    "detector": detector,
                    "raw_excerpt": raw_excerpt[:4000],
                }
            )
            .execute()
            .data[0]
        )

    def list_quarantine(self, limit: int = 100) -> list[dict[str, Any]]:
        return (
            self.sb.table("quarantine")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )


@lru_cache
def get_db() -> Database:
    return Database()
