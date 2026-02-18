"""Tests for the EventBus and Event model."""

import threading

from proving_ground.events import Event, EventBus, EventType


def test_event_to_dict():
    e = Event(event_type=EventType.AGENT_START, agent_id="pg_alpha", message="started")
    d = e.to_dict()
    assert d["event_type"] == "agent_start"
    assert d["agent_id"] == "pg_alpha"
    assert d["message"] == "started"
    assert "timestamp" in d
    assert "event_id" in d


def test_event_defaults():
    e = Event(event_type=EventType.FLEET_START)
    assert e.agent_id == ""
    assert e.phase == ""
    assert e.wave == 0
    assert e.data == {}
    assert len(e.event_id) == 12


def test_subscribe_and_emit():
    bus = EventBus()
    received = []
    bus.subscribe(lambda e: received.append(e))

    event = Event(event_type=EventType.FLEET_START, message="go")
    bus.emit(event)

    assert len(received) == 1
    assert received[0] is event


def test_multiple_subscribers():
    bus = EventBus()
    results_a, results_b = [], []
    bus.subscribe(lambda e: results_a.append(e))
    bus.subscribe(lambda e: results_b.append(e))

    bus.emit(Event(event_type=EventType.WAVE_START))

    assert len(results_a) == 1
    assert len(results_b) == 1


def test_unsubscribe():
    bus = EventBus()
    received = []

    def handler(e: Event) -> None:
        received.append(e)

    bus.subscribe(handler)
    bus.emit(Event(event_type=EventType.FLEET_START))
    assert len(received) == 1

    bus.unsubscribe(handler)
    bus.emit(Event(event_type=EventType.FLEET_DONE))
    assert len(received) == 1  # no new events


def test_subscriber_error_does_not_break_others():
    bus = EventBus()
    received = []

    def bad_handler(e: Event) -> None:
        raise ValueError("boom")

    bus.subscribe(bad_handler)
    bus.subscribe(lambda e: received.append(e))

    bus.emit(Event(event_type=EventType.AGENT_START))
    assert len(received) == 1  # second subscriber still called


def test_history():
    bus = EventBus()
    for i in range(3):
        bus.emit(Event(event_type=EventType.PHASE_START, message=str(i)))

    history = bus.history
    assert len(history) == 3
    assert history[0].message == "0"
    assert history[2].message == "2"


def test_history_capped():
    bus = EventBus()
    bus._max_history = 5
    for i in range(10):
        bus.emit(Event(event_type=EventType.PHASE_DONE, message=str(i)))

    assert len(bus.history) == 5
    assert bus.history[0].message == "5"


def test_thread_safety():
    bus = EventBus()
    received = []
    lock = threading.Lock()

    def handler(e: Event) -> None:
        with lock:
            received.append(e)

    bus.subscribe(handler)

    threads = []
    for i in range(20):
        t = threading.Thread(target=bus.emit, args=(Event(event_type=EventType.AGENT_DONE, message=str(i)),))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert len(received) == 20
