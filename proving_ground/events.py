"""Thread-safe event bus for real-time monitoring."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable


class EventType(str, Enum):
    FLEET_START = "fleet_start"
    FLEET_DONE = "fleet_done"
    WAVE_START = "wave_start"
    WAVE_DONE = "wave_done"
    AGENT_START = "agent_start"
    AGENT_DONE = "agent_done"
    AGENT_FAILED = "agent_failed"
    PHASE_START = "phase_start"
    PHASE_DONE = "phase_done"


@dataclass
class Event:
    """Structured event emitted by fleet/agent operations."""

    event_type: EventType
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    agent_id: str = ""
    phase: str = ""
    wave: int = 0
    status: str = ""
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "agent_id": self.agent_id,
            "phase": self.phase,
            "wave": self.wave,
            "status": self.status,
            "message": self.message,
            "data": self.data,
        }


# Subscriber callback type
EventCallback = Callable[[Event], None]


class EventBus:
    """Thread-safe publish/subscribe event bus.

    Fully opt-in: pass ``event_bus=None`` to skip event emission.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[EventCallback] = []
        self._history: list[Event] = []
        self._max_history: int = 500

    def subscribe(self, callback: EventCallback) -> None:
        """Register a subscriber callback."""
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: EventCallback) -> None:
        """Remove a subscriber callback."""
        with self._lock:
            self._subscribers = [s for s in self._subscribers if s is not callback]

    def emit(self, event: Event) -> None:
        """Publish an event to all subscribers."""
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(event)
            except Exception:
                pass  # Don't let subscriber errors break the emitter

    @property
    def history(self) -> list[Event]:
        """Return a copy of the event history."""
        with self._lock:
            return list(self._history)
