"""Small in-process Server-Sent Events hub for Agent Theater.

Durable state belongs in ``case_events``. This hub carries only the ephemeral
stage animation, so reconnecting clients receive a short replay and then live
events without pretending an in-memory queue is the audit log.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any


class EventHub:
    def __init__(self, history_size: int = 100) -> None:
        self._history: deque[dict[str, Any]] = deque(maxlen=history_size)
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._sequence = 0

    async def publish(self, event: dict[str, Any]) -> dict[str, Any]:
        self._sequence += 1
        envelope = {
            "id": self._sequence,
            "at": datetime.now(timezone.utc).isoformat(),
            **event,
        }
        self._history.append(envelope)
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(envelope)
            except asyncio.QueueFull:
                # A slow browser loses animation frames, never durable events.
                pass
        return envelope

    async def subscribe(self, after: int = 0) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        for event in self._history:
            if int(event["id"]) > after:
                queue.put_nowait(event)
        self._subscribers.add(queue)
        try:
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield {
                        "event": "heartbeat",
                        "at": datetime.now(timezone.utc).isoformat(),
                    }
        finally:
            self._subscribers.discard(queue)


hub = EventHub()
