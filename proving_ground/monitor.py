"""Rich-based CLI fleet monitor.

Works in two modes:
  1. In-process: subscribe to an EventBus directly.
  2. Standalone: tail a log file and parse events via regex.

Entry point: ``pg-monitor`` or ``python -m proving_ground.monitor``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from proving_ground.events import Event, EventBus, EventType

# Regex for parsing JSON event lines from log files
_EVENT_LINE_RE = re.compile(r"\{.*\"event_type\".*\}")


@dataclass
class MonitorState:
    """Tracks fleet status for display."""

    fleet_running: bool = False
    current_wave: int = 0
    agents: dict[str, dict[str, str]] = field(default_factory=dict)  # agent_id -> {phase, status}
    completed: int = 0
    failed: int = 0
    events: list[dict[str, str]] = field(default_factory=list)
    max_events: int = 50

    def handle_event(self, event: Event) -> None:
        """Update state from an event."""
        et = event.event_type

        if et == EventType.FLEET_START:
            self.fleet_running = True
            self.agents.clear()
            self.completed = 0
            self.failed = 0
        elif et == EventType.FLEET_DONE:
            self.fleet_running = False
        elif et == EventType.WAVE_START:
            self.current_wave = event.wave
        elif et == EventType.AGENT_START:
            self.agents[event.agent_id] = {"phase": "-", "status": "running"}
        elif et == EventType.PHASE_START:
            if event.agent_id in self.agents:
                self.agents[event.agent_id]["phase"] = event.phase
        elif et == EventType.PHASE_DONE:
            if event.agent_id in self.agents:
                self.agents[event.agent_id]["phase"] = f"{event.phase} ({event.status})"
        elif et == EventType.AGENT_DONE:
            self.completed += 1
            if event.agent_id in self.agents:
                self.agents[event.agent_id]["status"] = "done"
        elif et == EventType.AGENT_FAILED:
            self.failed += 1
            if event.agent_id in self.agents:
                self.agents[event.agent_id]["status"] = "failed"

        # Append to recent events
        ts = event.timestamp.split("T")[1][:8] if "T" in event.timestamp else event.timestamp
        self.events.append({"time": ts, "type": event.event_type.value, "message": event.message})
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]


def parse_event_line(line: str) -> Event | None:
    """Try to parse a JSON event from a log line."""
    match = _EVENT_LINE_RE.search(line)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        return Event(
            event_type=EventType(data["event_type"]),
            timestamp=data.get("timestamp", ""),
            event_id=data.get("event_id", ""),
            agent_id=data.get("agent_id", ""),
            phase=data.get("phase", ""),
            wave=data.get("wave", 0),
            status=data.get("status", ""),
            message=data.get("message", ""),
            data=data.get("data", {}),
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def _build_table(state: MonitorState) -> "Table":
    """Build a Rich Table showing agent progress."""
    from rich.table import Table

    table = Table(title="Agent Progress", expand=True)
    table.add_column("Agent", style="cyan")
    table.add_column("Phase")
    table.add_column("Status")

    for agent_id, info in sorted(state.agents.items()):
        status = info["status"]
        style = "green" if status == "done" else "red" if status == "failed" else "yellow"
        table.add_row(agent_id, info["phase"], f"[{style}]{status}[/{style}]")

    return table


def _build_layout(state: MonitorState) -> "Group":
    """Build the full Rich display."""
    from rich.console import Group
    from rich.panel import Panel
    from rich.text import Text

    # Header
    status_text = "[green]RUNNING[/green]" if state.fleet_running else "[dim]IDLE[/dim]"
    header = Text.from_markup(
        f"Fleet: {status_text}  |  Wave: {state.current_wave}  |  "
        f"Completed: [green]{state.completed}[/green]  |  Failed: [red]{state.failed}[/red]"
    )

    # Agent table
    table = _build_table(state)

    # Recent events
    event_lines = []
    for ev in state.events[-20:]:
        event_lines.append(f"[dim]{ev['time']}[/dim] [bold]{ev['type']}[/bold] {ev['message']}")
    events_text = Text.from_markup("\n".join(event_lines)) if event_lines else Text("No events yet.", style="dim")
    events_panel = Panel(events_text, title="Recent Events", border_style="dim")

    return Group(header, table, events_panel)


def run_monitor_eventbus(event_bus: EventBus) -> None:
    """Run the Rich Live monitor subscribed to an EventBus (in-process mode)."""
    from rich.live import Live

    state = MonitorState()

    def on_event(event: Event) -> None:
        state.handle_event(event)

    event_bus.subscribe(on_event)
    try:
        with Live(_build_layout(state), refresh_per_second=4) as live:
            while True:
                live.update(_build_layout(state))
                time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        event_bus.unsubscribe(on_event)


def run_monitor_logfile(stream: TextIO) -> None:
    """Run the Rich Live monitor by tailing a file/stream for JSON events."""
    from rich.live import Live

    state = MonitorState()

    with Live(_build_layout(state), refresh_per_second=4) as live:
        try:
            while True:
                line = stream.readline()
                if line:
                    event = parse_event_line(line)
                    if event:
                        state.handle_event(event)
                        live.update(_build_layout(state))
                else:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            pass


def main() -> None:
    """CLI entry point for pg-monitor."""
    parser = argparse.ArgumentParser(description="Proving Ground fleet monitor")
    parser.add_argument("--log", "-l", type=str, default=None, help="Path to log file to tail (default: stdin)")
    args = parser.parse_args()

    if args.log:
        path = Path(args.log)
        if not path.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            sys.exit(1)
        with open(path) as f:
            # Seek to end for tail behavior
            f.seek(0, 2)
            run_monitor_logfile(f)
    else:
        print("Reading events from stdin (pipe JSON event lines)...")
        run_monitor_logfile(sys.stdin)


if __name__ == "__main__":
    main()
