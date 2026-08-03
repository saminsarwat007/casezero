"""The six agents, the firewall they sit behind, and the orchestrator above them.

Reading order, which is also execution order:

    firewall      deterministic screen, ahead of every model call
    intake        parse, screen, extract, encrypt
    classifier    model proposes a category; the rule pack assigns urgency
    verifier      MCP against core banking; PASS / FAIL / MANUAL_REVIEW
    resolver      kernel gate → signed ticket → double-entry posting
    communicator  draft → compliance lint → authorize_send
    supervisor    working-day SLA forecast, read-only on money
    orchestrator  status transitions and the hash chain

`base.AgentContext` carries the capabilities an agent is allowed to use. Nothing
here reaches for a global, which is why the whole pipeline runs offline in tests.
"""

from api.agents.base import AgentContext, Event, build_context

__all__ = ["AgentContext", "Event", "build_context"]
