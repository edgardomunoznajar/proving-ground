"""Tests for the CLI monitor state and log parsing."""

import json

from proving_ground.events import Event, EventType
from proving_ground.monitor import MonitorState, parse_event_line


def _make_event(event_type: EventType, **kwargs) -> Event:
    return Event(event_type=event_type, **kwargs)


def test_monitor_state_fleet_lifecycle():
    state = MonitorState()
    assert not state.fleet_running

    state.handle_event(_make_event(EventType.FLEET_START, message="go"))
    assert state.fleet_running
    assert state.completed == 0

    state.handle_event(_make_event(EventType.WAVE_START, wave=1))
    assert state.current_wave == 1

    state.handle_event(_make_event(EventType.AGENT_START, agent_id="pg_alpha"))
    assert "pg_alpha" in state.agents
    assert state.agents["pg_alpha"]["status"] == "running"

    state.handle_event(_make_event(EventType.PHASE_START, agent_id="pg_alpha", phase="work"))
    assert state.agents["pg_alpha"]["phase"] == "work"

    state.handle_event(_make_event(EventType.PHASE_DONE, agent_id="pg_alpha", phase="work", status="completed"))
    assert "completed" in state.agents["pg_alpha"]["phase"]

    state.handle_event(_make_event(EventType.AGENT_DONE, agent_id="pg_alpha"))
    assert state.completed == 1
    assert state.agents["pg_alpha"]["status"] == "done"

    state.handle_event(_make_event(EventType.FLEET_DONE))
    assert not state.fleet_running


def test_monitor_state_agent_failed():
    state = MonitorState()
    state.handle_event(_make_event(EventType.AGENT_START, agent_id="pg_beta"))
    state.handle_event(_make_event(EventType.AGENT_FAILED, agent_id="pg_beta"))

    assert state.failed == 1
    assert state.agents["pg_beta"]["status"] == "failed"


def test_monitor_state_fleet_start_resets():
    state = MonitorState()
    state.handle_event(_make_event(EventType.AGENT_START, agent_id="pg_old"))
    state.completed = 5

    state.handle_event(_make_event(EventType.FLEET_START))
    assert len(state.agents) == 0
    assert state.completed == 0


def test_monitor_state_event_history_capped():
    state = MonitorState()
    state.max_events = 5
    for i in range(10):
        state.handle_event(_make_event(EventType.PHASE_START, message=str(i)))
    assert len(state.events) == 5
    assert state.events[0]["message"] == "5"


def test_parse_event_line_valid():
    event_data = {
        "event_type": "agent_start",
        "timestamp": "2025-01-01T12:00:00",
        "event_id": "abc123",
        "agent_id": "pg_alpha",
        "phase": "",
        "wave": 1,
        "status": "",
        "message": "Starting",
        "data": {},
    }
    line = f"2025-01-01 12:00:00 INFO {json.dumps(event_data)}"
    event = parse_event_line(line)

    assert event is not None
    assert event.event_type == EventType.AGENT_START
    assert event.agent_id == "pg_alpha"
    assert event.message == "Starting"


def test_parse_event_line_bare_json():
    event_data = {"event_type": "fleet_start", "timestamp": "2025-01-01T00:00:00"}
    event = parse_event_line(json.dumps(event_data))
    assert event is not None
    assert event.event_type == EventType.FLEET_START


def test_parse_event_line_invalid():
    assert parse_event_line("not a json line") is None
    assert parse_event_line('{"event_type": "unknown_type"}') is None
    assert parse_event_line("") is None


def test_parse_event_line_malformed_json():
    assert parse_event_line('{"event_type": "agent_start", broken}') is None
