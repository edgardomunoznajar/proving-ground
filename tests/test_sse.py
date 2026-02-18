"""Tests for the SSE endpoint."""

import json

import pytest
from httpx import ASGITransport, AsyncClient

from proving_ground.dashboard.sse import _event_generator, router, wire_event_bus
from proving_ground.events import Event, EventBus, EventType


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.mark.asyncio
async def test_event_generator_yields_events(event_bus):
    """Events emitted on the bus appear in the async generator."""
    gen = _event_generator(event_bus)

    # First call returns keepalive (no events yet), which triggers subscription
    chunk = await gen.__anext__()
    assert chunk.strip().startswith(":")  # keepalive

    # Now emit after subscription is active
    event_bus.emit(Event(event_type=EventType.FLEET_START, message="go"))

    chunk = await gen.__anext__()
    assert chunk.startswith("data: ")
    payload = json.loads(chunk.removeprefix("data: ").strip())
    assert payload["event_type"] == "fleet_start"
    assert payload["message"] == "go"

    await gen.aclose()


@pytest.mark.asyncio
async def test_event_generator_keepalive(event_bus):
    """Without events, generator emits keepalive comments."""
    gen = _event_generator(event_bus)

    chunk = await gen.__anext__()
    assert chunk.strip().startswith(":")  # SSE comment (keepalive)

    await gen.aclose()


@pytest.mark.asyncio
async def test_event_generator_multiple_events(event_bus):
    """Multiple events are yielded in order."""
    gen = _event_generator(event_bus)

    # Skip initial keepalive
    await gen.__anext__()

    event_bus.emit(Event(event_type=EventType.AGENT_START, agent_id="pg_a"))
    event_bus.emit(Event(event_type=EventType.AGENT_DONE, agent_id="pg_a"))

    chunk1 = await gen.__anext__()
    chunk2 = await gen.__anext__()

    p1 = json.loads(chunk1.removeprefix("data: ").strip())
    p2 = json.loads(chunk2.removeprefix("data: ").strip())
    assert p1["event_type"] == "agent_start"
    assert p2["event_type"] == "agent_done"

    await gen.aclose()


@pytest.mark.asyncio
async def test_sse_endpoint_no_bus():
    """Without an event bus, the endpoint returns an error message."""
    from fastapi import FastAPI

    wire_event_bus(None)  # type: ignore[arg-type]

    app = FastAPI()
    app.include_router(router, prefix="/api")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/events")
        assert resp.status_code == 200
        assert "error" in resp.text


@pytest.mark.asyncio
async def test_event_generator_unsubscribes_on_close(event_bus):
    """Generator cleanup removes the subscriber from the event bus."""
    gen = _event_generator(event_bus)

    # Trigger subscription by pulling one keepalive
    await gen.__anext__()

    # Bus should have 1 subscriber
    assert len(event_bus._subscribers) == 1

    await gen.aclose()

    # Subscriber should be cleaned up
    assert len(event_bus._subscribers) == 0
