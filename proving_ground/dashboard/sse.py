"""Server-Sent Events endpoint for real-time event streaming."""

from __future__ import annotations

import asyncio
import json
import queue
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from proving_ground.events import Event, EventBus

router = APIRouter()

# Placeholder — replaced by wire_event_bus() at app startup
_event_bus: EventBus | None = None


def wire_event_bus(bus: EventBus) -> None:
    """Set the module-level event bus used by the SSE endpoint."""
    global _event_bus
    _event_bus = bus


async def _event_generator(bus: EventBus) -> AsyncGenerator[str, None]:
    """Bridge sync EventBus to async SSE generator via a thread-safe queue."""
    q: queue.Queue[Event] = queue.Queue(maxsize=256)

    def on_event(event: Event) -> None:
        try:
            q.put_nowait(event)
        except queue.Full:
            pass  # drop events if client is too slow

    bus.subscribe(on_event)
    try:
        while True:
            try:
                event = q.get_nowait()
                data = json.dumps(event.to_dict(), default=str)
                yield f"data: {data}\n\n"
            except queue.Empty:
                # Send keepalive comment every 1s to detect disconnects
                yield ": keepalive\n\n"
                await asyncio.sleep(1)
    finally:
        bus.unsubscribe(on_event)


@router.get("/events")
async def events_stream() -> StreamingResponse:
    """Stream fleet events as Server-Sent Events."""
    if _event_bus is None:
        return StreamingResponse(
            iter(["data: {\"error\": \"No event bus configured\"}\n\n"]),
            media_type="text/event-stream",
        )
    return StreamingResponse(
        _event_generator(_event_bus),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
