"""The gateway agents call tools through.

Two transports behind one interface:

* **stdio** — spawns `mcp_servers/*.py` and speaks the real Model Context Protocol.
  Tools are *discovered*, not hardcoded, which is the difference between using MCP
  and claiming to.
* **inproc** — calls the same functions directly. Used by tests, and available as a
  fallback so a subprocess that fails to spawn during a live demo degrades to a
  working pipeline instead of a dead one.

Which transport served a call is recorded on the result and surfaced in the UI, so
the claim on stage is checkable rather than asserted.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from api.config import Settings, get_settings

log = logging.getLogger("casezero.mcp")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: server name -> module that runs it over stdio
SERVERS: dict[str, str] = {
    "core-banking": "mcp_servers.core_banking_server",
    "crm": "mcp_servers.crm_server",
}


class ToolCallError(RuntimeError):
    """A tool refused, or could not be reached."""


@dataclass
class ToolCall:
    """One tool invocation, with enough detail for the Agent Theater to replay it."""

    server: str
    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    transport: str
    latency_ms: int
    error: str | None = None

    def as_event(self) -> dict[str, Any]:
        return {
            "server": self.server,
            "tool": self.tool,
            "arguments": self.arguments,
            "transport": self.transport,
            "latency_ms": self.latency_ms,
            "ok": self.error is None,
            "error": self.error,
        }


class ToolGateway:
    """Base interface. `call` returns the tool's JSON payload."""

    transport = "base"

    async def call(self, server: str, tool: str, **arguments: Any) -> dict[str, Any]:
        raise NotImplementedError

    async def list_tools(self) -> dict[str, list[str]]:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


# ─── In-process ─────────────────────────────────────────────────────────────


class InProcessGateway(ToolGateway):
    """Direct function calls. No subprocess, no protocol, same code path underneath."""

    transport = "inproc"

    def __init__(self, db: Any = None) -> None:
        self._db = db

    @property
    def db(self) -> Any:
        if self._db is None:
            from api.db.client import get_db

            self._db = get_db()
        return self._db

    async def call(self, server: str, tool: str, **arguments: Any) -> dict[str, Any]:
        from api.mcp_tools import core_banking, crm

        module = {"core-banking": core_banking, "crm": crm}.get(server)
        if module is None:
            raise ToolCallError(f"Unknown MCP server {server!r}.")

        function = getattr(module, tool, None)
        if function is None or tool.startswith("_"):
            raise ToolCallError(f"{server} exposes no tool named {tool!r}.")

        try:
            return await asyncio.to_thread(function, self.db, **arguments)
        except (core_banking.ToolError, crm.ToolError) as exc:
            raise ToolCallError(str(exc)) from exc

    async def list_tools(self) -> dict[str, list[str]]:
        from api.mcp_tools import core_banking, crm

        def public(module: Any) -> list[str]:
            return [
                name
                for name, value in vars(module).items()
                if callable(value)
                and not name.startswith("_")
                and getattr(value, "__module__", "") == module.__name__
                and name not in ("ToolError",)
            ]

        return {"core-banking": public(core_banking), "crm": public(crm)}


# ─── Real MCP over stdio ────────────────────────────────────────────────────


class StdioGateway(ToolGateway):
    """Speaks the protocol. Sessions are opened once and reused."""

    transport = "stdio"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._stack = AsyncExitStack()
        self._sessions: dict[str, Any] = {}
        self._tools: dict[str, list[str]] = {}
        self._lock = asyncio.Lock()

    async def _session(self, server: str) -> Any:
        if server in self._sessions:
            return self._sessions[server]

        module = SERVERS.get(server)
        if module is None:
            raise ToolCallError(f"Unknown MCP server {server!r}.")

        async with self._lock:
            if server in self._sessions:  # another task won the race
                return self._sessions[server]

            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", module],
                cwd=str(REPO_ROOT),
                env=None,
            )
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            listing = await session.list_tools()
            self._tools[server] = [t.name for t in listing.tools]
            log.info(
                "MCP %s connected over stdio, %d tools: %s",
                server,
                len(self._tools[server]),
                ", ".join(self._tools[server]),
            )

            self._sessions[server] = session
            return session

    async def call(self, server: str, tool: str, **arguments: Any) -> dict[str, Any]:
        session = await self._session(server)

        known = self._tools.get(server, [])
        if known and tool not in known:
            raise ToolCallError(
                f"{server} does not expose {tool!r}. Discovered tools: {', '.join(known)}"
            )

        response = await session.call_tool(tool, _clean(arguments))
        payload = _unwrap(response)

        if getattr(response, "isError", False):
            raise ToolCallError(
                payload.get("error") or payload.get("text") or f"{server}.{tool} failed."
            )
        return payload

    async def list_tools(self) -> dict[str, list[str]]:
        for server in SERVERS:
            await self._session(server)
        return dict(self._tools)

    async def aclose(self) -> None:
        await self._stack.aclose()
        self._sessions.clear()


def _clean(arguments: dict[str, Any]) -> dict[str, Any]:
    """Drop Nones: an omitted optional argument is not the same as a null one."""
    return {k: v for k, v in arguments.items() if v is not None}


def _unwrap(response: Any) -> dict[str, Any]:
    """Turn an MCP tool response into a plain dict.

    The SDK returns structured content when the tool declares a return type and
    falls back to text content otherwise, so both shapes are handled.
    """
    structured = getattr(response, "structuredContent", None)
    if isinstance(structured, dict):
        # FastMCP wraps non-dict returns under "result".
        return structured.get("result", structured) if set(structured) == {"result"} else structured

    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text is None:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}
        return parsed if isinstance(parsed, dict) else {"result": parsed}

    return {}


# ─── Resolution ─────────────────────────────────────────────────────────────


@dataclass
class ResilientGateway(ToolGateway):
    """Preferred transport, with a fallback that keeps a live demo alive.

    A fallback is recorded loudly rather than silently: `degraded` is surfaced in
    the UI so nobody claims the protocol path was used when it was not.
    """

    primary: ToolGateway
    fallback: ToolGateway | None = None
    degraded: bool = False
    calls: list[ToolCall] = field(default_factory=list)

    @property
    def transport(self) -> str:  # type: ignore[override]
        return self.fallback.transport if self.degraded and self.fallback else self.primary.transport

    async def call(self, server: str, tool: str, **arguments: Any) -> dict[str, Any]:
        target = self.fallback if (self.degraded and self.fallback) else self.primary
        started = asyncio.get_event_loop().time()
        try:
            result = await target.call(server, tool, **arguments)
        except ToolCallError:
            # A tool refusal is a real answer; do not switch transports over it.
            raise
        except Exception as exc:  # noqa: BLE001 - transport failure, not tool failure
            if self.fallback is None or target is self.fallback:
                raise ToolCallError(f"{server}.{tool} unreachable: {exc}") from exc
            log.warning("MCP stdio transport failed (%s); falling back in-process.", exc)
            self.degraded = True
            result = await self.fallback.call(server, tool, **arguments)

        latency_ms = int((asyncio.get_event_loop().time() - started) * 1000)
        self.calls.append(
            ToolCall(
                server=server,
                tool=tool,
                arguments=_clean(arguments),
                result=result,
                transport=self.transport,
                latency_ms=latency_ms,
            )
        )
        return result

    async def list_tools(self) -> dict[str, list[str]]:
        try:
            return await self.primary.list_tools()
        except Exception:  # noqa: BLE001
            if self.fallback is None:
                raise
            self.degraded = True
            return await self.fallback.list_tools()

    async def aclose(self) -> None:
        await self.primary.aclose()
        if self.fallback:
            await self.fallback.aclose()


_gateway: ResilientGateway | None = None


def build_gateway(settings: Settings | None = None) -> ResilientGateway:
    cfg = settings or get_settings()
    if cfg.mcp_transport.lower() == "inproc":
        return ResilientGateway(primary=InProcessGateway(), fallback=None)
    return ResilientGateway(
        primary=StdioGateway(cfg),
        fallback=InProcessGateway() if cfg.mcp_allow_fallback else None,
    )


def get_gateway() -> ResilientGateway:
    """Process-wide gateway. Sessions are expensive to open, so they are shared."""
    global _gateway
    if _gateway is None:
        _gateway = build_gateway()
    return _gateway


async def close_gateway() -> None:
    global _gateway
    if _gateway is not None:
        await _gateway.aclose()
        _gateway = None
