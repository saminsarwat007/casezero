"""What every agent shares: a context, an event vocabulary, and a metered model call.

Each agent is a function `(input, context) -> result`, where the result carries the
events it wants written. No agent writes to `cases` itself. The orchestrator applies
the events, which is what keeps the hash chain continuous — a state change that
skipped the chain would be invisible to `verify_chain`, and an audit trail with
holes in it is not an audit trail.

The context also holds the *capabilities* an agent has: a tool gateway, a model
router, a database. Passing them in rather than importing singletons is what lets
the whole pipeline run offline in pytest against a fake bank and a scripted model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Sequence

from api.config import Settings, get_settings
from api.kernel.rules import RULE_PACKS_DIR, RulePack, load_all, load_yaml
from api.llm.provider import ImagePart, LLMError, LLMResult
from api.security.crypto import redact_pii

#: Actor strings written into `case_events.actor`. The distinction between an
#: agent and the kernel is the whole argument of this project, so it is recorded
#: on every row rather than inferred later.
KERNEL = "kernel"


def agent_actor(name: str) -> str:
    return f"agent:{name}"


@dataclass(frozen=True)
class Event:
    """One link an agent proposes for the case's chain."""

    type: str
    payload: dict[str, Any]
    actor: str = KERNEL


@dataclass
class AgentContext:
    """Everything an agent may touch, and nothing else.

    `db`, `gateway` and `router` are injected rather than resolved from module
    globals so a test can hand over a fake bank, an in-process gateway and a
    scripted model without patching anything.
    """

    db: Any = None
    gateway: Any = None
    router: Any = None
    settings: Settings = field(default_factory=get_settings)
    packs: dict[str, RulePack] = field(default_factory=dict)
    holidays: set[date] | None = None
    #: Frozen clock, so an SLA assertion in a test does not depend on the day it runs.
    now: datetime | None = None
    #: Per-run model telemetry. The cost-per-case panel reads this.
    llm_calls: list[LLMResult] = field(default_factory=list)
    #: Set when a model was unavailable and an agent fell back to a deterministic
    #: path. Degradation is surfaced, never silently absorbed.
    degraded: list[str] = field(default_factory=list)
    #: Index of the first model call made by the active orchestrator run. The
    #: context can be reused for a batch without one case inheriting another's
    #: cost.
    _run_start: int = field(default=0, init=False, repr=False)
    #: Bound after intake creates the case. Calls made during intake are queued
    #: in ``llm_calls`` and flushed with this ID as soon as it exists.
    _case_id: str | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.packs:
            self.packs = load_all(RULE_PACKS_DIR)

    # ─── Clock ──────────────────────────────────────────────────────────────

    def clock(self) -> datetime:
        return self.now or datetime.now(timezone.utc)

    def begin_run(self) -> None:
        """Start a fresh case while retaining process-level call history."""
        self._run_start = len(self.llm_calls)
        self._case_id = None
        self.degraded.clear()

    def bind_case(self, case_id: str) -> None:
        """Attach intake telemetry to the case created immediately afterward.

        Intake must run before the first case write so PII can be encrypted, but
        that means its model call happens before a case ID exists. Binding here
        closes that ordering gap without ever writing plaintext customer data.
        """
        self._case_id = case_id
        for result in self.llm_calls[self._run_start :]:
            self._persist_llm_call(result)

    # ─── Policy ─────────────────────────────────────────────────────────────

    def pack(self, category: str) -> RulePack:
        """The active rule pack for a category.

        Raises rather than defaulting: a case whose policy cannot be found must
        stop, because every downstream gate reads its thresholds from here.
        """
        found = self.packs.get(category)
        active_pack = getattr(self.db, "active_pack", None)
        if active_pack is not None:
            row = active_pack(category)
            if row and row.get("yaml"):
                live = load_yaml(str(row["yaml"]))
                if found is None or live.version >= found.version:
                    self.packs[category] = live
                    found = live
        if found is None:
            raise KeyError(
                f"No rule pack loaded for category {category!r}. "
                f"Loaded: {', '.join(sorted(self.packs)) or '(none)'}"
            )
        return found

    # ─── Tools ──────────────────────────────────────────────────────────────

    async def call_tool(self, server: str, tool: str, **arguments: Any) -> dict[str, Any]:
        if self.gateway is None:
            raise RuntimeError(
                f"{server}.{tool} was called but no MCP gateway is attached to the "
                f"agent context."
            )
        return await self.gateway.call(server, tool, **arguments)

    # ─── Models ─────────────────────────────────────────────────────────────

    async def complete(
        self,
        agent: str,
        prompt: str,
        *,
        system: str | None = None,
        schema: Any = None,
        images: Sequence[ImagePart] | None = None,
        temperature: float = 0.1,
        redact: bool = True,
        **kwargs: Any,
    ) -> LLMResult:
        """Run a model call for `agent`, with PII stripped and cost recorded.

        `redact` defaults to on and every caller leaves it on: NRICs and account
        numbers are removed from the prompt before it leaves the process. The
        model never needs them — it is reading a complaint, not paying it — and
        the masking happens here so no individual agent can forget.
        """
        if self.router is None:
            raise LLMError(f"{agent}: no model router is attached to the agent context.")

        provider, model = self.router.for_agent(agent)
        result = await provider.complete(
            redact_pii(prompt) if redact else prompt,
            system=system,
            schema=schema,
            images=images,
            temperature=temperature,
            model=model,
            agent=agent,
            **kwargs,
        )
        self.llm_calls.append(result)
        if self._case_id is not None:
            self._persist_llm_call(result)
        return result

    @property
    def cost_rm(self) -> float:
        return round(sum(call.cost_rm for call in self.llm_calls[self._run_start :]), 6)

    def _persist_llm_call(self, result: LLMResult) -> None:
        """Write measured telemetry without turning observability into an outage."""
        logger = getattr(self.db, "log_llm_call", None)
        if logger is None:
            return
        try:
            logger(result, case_id=self._case_id)
        except Exception as exc:  # noqa: BLE001 - telemetry must not strand a case
            self.note_degraded(
                f"model telemetry unavailable for {result.agent}: {exc}"
            )

    def note_degraded(self, reason: str) -> None:
        """Record that a capability was unavailable.

        Surfaced on the case rather than swallowed, because a pipeline that
        quietly runs without its classifier still produces a case — and that case
        would look identical to a good one.
        """
        if reason not in self.degraded:
            self.degraded.append(reason)


def build_context(**overrides: Any) -> AgentContext:
    """A context wired to the real database, MCP gateway and model router."""
    from api.db.client import get_db
    from api.llm.provider import get_router
    from api.mcp_tools.gateway import get_gateway

    defaults: dict[str, Any] = {
        "db": get_db(),
        "gateway": get_gateway(),
        "router": get_router(),
    }
    defaults.update(overrides)
    return AgentContext(**defaults)
