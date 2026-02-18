"""Example: Self-Improvement Agent.

Demonstrates the full harvest-actuate loop:

  Wave 1 — Worker agents run phases and produce journals with diagnosis data
            (bugs_suspected, improvements, tool_errors).
  Wave 2 — A self-improvement agent harvests issues from those journals,
            ranks them, and calls an LLM actuator to propose fixes.

Usage:
    python -m examples.self_improve_agent

Replace `fake_llm_call` with a real LiteLLM / OpenAI call to get actual fixes.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from proving_ground import (
    Agent,
    AgentPersona,
    FleetOrchestrator,
    JournalStore,
    Phase,
    PhaseResult,
    PhaseStatus,
    SQLStorageBackend,
)
from proving_ground.self_improve.actuator import FixResult, build_fix_prompt
from proving_ground.self_improve.harvester import harvest_and_rank

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

# ---------------------------------------------------------------------------
# Phases for Wave 1 workers
# ---------------------------------------------------------------------------


class WorkPhase(Phase):
    """Simulates a worker doing real work and encountering issues."""

    def __init__(self, tools: list[str], errors: list[dict] | None = None):
        self._tools = tools
        self._errors = errors or []

    @property
    def name(self) -> str:
        return "work"

    def execute(self, context: dict[str, Any], prior_results: list[PhaseResult]) -> PhaseResult:
        t0 = time.monotonic()
        started = datetime.now(timezone.utc).isoformat()

        # Simulate calling tools, some of which may error
        tool_errors = []
        for err in self._errors:
            tool_errors.append({"tool": err["tool"], "error": err["error"]})

        finished = datetime.now(timezone.utc).isoformat()
        return PhaseResult(
            phase=self.name,
            status=PhaseStatus.COMPLETED,
            started_at=started,
            finished_at=finished,
            duration_seconds=round(time.monotonic() - t0, 3),
            tools_called=self._tools,
            tokens_used=200,
            data={"tool_errors": tool_errors},
        )


class DiagnosePhase(Phase):
    """Agent self-diagnosis — writes bugs_suspected / improvements."""

    def __init__(self, bugs: list[str] | None = None, improvements: list[str] | None = None):
        self._bugs = bugs or []
        self._improvements = improvements or []

    @property
    def name(self) -> str:
        return "diagnose"

    def execute(self, context: dict[str, Any], prior_results: list[PhaseResult]) -> PhaseResult:
        started = datetime.now(timezone.utc).isoformat()
        return PhaseResult(
            phase=self.name,
            status=PhaseStatus.COMPLETED,
            started_at=started,
            finished_at=datetime.now(timezone.utc).isoformat(),
            duration_seconds=0.01,
            tokens_used=100,
            data={
                "diagnosis": {
                    "bugs_suspected": self._bugs,
                    "improvements": self._improvements,
                    "confidence_score": 0.8,
                    "risk_assessment": "",
                    "next_day_plan": "Continue monitoring",
                }
            },
        )


# ---------------------------------------------------------------------------
# Phases for Wave 2 self-improvement agent
# ---------------------------------------------------------------------------


class HarvestPhase(Phase):
    """Harvest improvement items from stored journals."""

    def __init__(self, storage: Any, last_n_runs: int = 5, top_n: int = 10):
        self._storage = storage
        self._last_n_runs = last_n_runs
        self._top_n = top_n

    @property
    def name(self) -> str:
        return "harvest"

    def execute(self, context: dict[str, Any], prior_results: list[PhaseResult]) -> PhaseResult:
        started = datetime.now(timezone.utc).isoformat()
        items = harvest_and_rank(self._storage, last_n_runs=self._last_n_runs, top_n=self._top_n)
        return PhaseResult(
            phase=self.name,
            status=PhaseStatus.COMPLETED,
            started_at=started,
            finished_at=datetime.now(timezone.utc).isoformat(),
            duration_seconds=0.01,
            tokens_used=0,
            data={
                "items_found": len(items),
                "items": [item.to_dict() for item in items],
            },
        )


class ActuatePhase(Phase):
    """Call the LLM to propose fixes for harvested items."""

    def __init__(self, llm_call: Any, project_root: Path | None = None, max_fixes: int = 3):
        self._llm_call = llm_call
        self._project_root = project_root or Path(".")
        self._max_fixes = max_fixes

    @property
    def name(self) -> str:
        return "actuate"

    def execute(self, context: dict[str, Any], prior_results: list[PhaseResult]) -> PhaseResult:
        started = datetime.now(timezone.utc).isoformat()

        # Get harvested items from the prior harvest phase
        items_data = []
        for pr in prior_results:
            if pr.phase == "harvest" and pr.data.get("items"):
                items_data = pr.data["items"]
                break

        if not items_data:
            return PhaseResult(
                phase=self.name,
                status=PhaseStatus.COMPLETED,
                started_at=started,
                finished_at=datetime.now(timezone.utc).isoformat(),
                duration_seconds=0.01,
                data={"fixes": [], "diagnosis": {
                    "bugs_suspected": [],
                    "improvements": ["No improvement items found to actuate"],
                    "confidence_score": 1.0,
                }},
            )

        fixes: list[dict] = []
        for item_dict in items_data[: self._max_fixes]:
            from proving_ground.self_improve.harvester import ImprovementItem

            item = ImprovementItem(**{k: v for k, v in item_dict.items() if k != "runs"})
            item.runs = item_dict.get("runs", [])

            prompt = build_fix_prompt(item, {}, "You are a senior developer.")
            try:
                response = self._llm_call(prompt)
                fixes.append(FixResult(
                    item=item, status="proposed", diff_summary=response[:200],
                ).to_dict())
            except Exception as e:
                fixes.append(FixResult(item=item, status="failed", error=str(e)).to_dict())

        return PhaseResult(
            phase=self.name,
            status=PhaseStatus.COMPLETED,
            started_at=started,
            finished_at=datetime.now(timezone.utc).isoformat(),
            duration_seconds=0.01,
            tokens_used=len(fixes) * 500,
            data={
                "fixes": fixes,
                "diagnosis": {
                    "bugs_suspected": [],
                    "improvements": [f"Proposed {len(fixes)} fixes for fleet issues"],
                    "confidence_score": 0.9,
                },
            },
        )


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def fake_llm_call(messages: list[dict]) -> str:
    """Stub LLM — returns a plausible fix JSON. Replace with real LLM call."""
    return json.dumps({
        "analysis": "The tool returns None when the connection times out.",
        "file_path": None,
        "fix_description": "Add a retry with backoff on timeout",
        "original_code": "",
        "fixed_code": "",
    })


def build_fleet(storage: SQLStorageBackend) -> FleetOrchestrator:
    """Build a 2-wave fleet: workers then self-improvement."""
    journal_store = JournalStore(storage)
    journal_store.ensure_table()

    # Wave 1: two worker agents that encounter issues
    alpha = Agent(
        persona=AgentPersona(codename="Alpha", mandate="Run tasks and report issues"),
        phases=[
            WorkPhase(
                tools=["search", "read_file"],
                errors=[{"tool": "search", "error": "Connection timeout after 30s"}],
            ),
            DiagnosePhase(
                bugs=["search tool times out under load"],
                improvements=["add retry logic to search tool"],
            ),
        ],
        journal_store=journal_store,
    )
    beta = Agent(
        persona=AgentPersona(codename="Beta", mandate="Run tasks and report issues"),
        phases=[
            WorkPhase(
                tools=["search", "write_file"],
                errors=[{"tool": "search", "error": "Connection timeout after 30s"}],
            ),
            DiagnosePhase(
                bugs=["search tool times out under load"],
                improvements=["search timeout should be configurable"],
            ),
        ],
        journal_store=journal_store,
    )

    # Wave 2: self-improvement agent harvests + actuates
    improver = Agent(
        persona=AgentPersona(codename="Improver", mandate="Harvest fleet issues and propose fixes"),
        phases=[
            HarvestPhase(storage, last_n_runs=5, top_n=10),
            ActuatePhase(fake_llm_call, max_fixes=3),
        ],
        journal_store=journal_store,
    )

    return FleetOrchestrator(waves=[[alpha, beta], [improver]], max_workers=2)


def main() -> dict[str, Any]:
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///proving_ground_example.db")
    storage = SQLStorageBackend(engine)

    fleet = build_fleet(storage)
    result = fleet.run()

    print(f"\nFleet run: {result['status']}")
    print(f"  Agents: {result['agents_completed']}/{result['total_agents']}")
    print(f"  Tokens: {result['total_tokens']}")

    improver_result = result["agents"].get("Improver", {})
    print(f"\nImprover status: {improver_result.get('status')}")
    return result


if __name__ == "__main__":
    main()
