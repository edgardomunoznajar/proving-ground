"""Fleet orchestrator — runs agents in waves with pluggable context bridging."""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from proving_ground.agent import Agent
from proving_ground.events import Event, EventBus, EventType
from proving_ground.models import DailyJournal

logger = logging.getLogger("proving_ground")

# Type alias for the context builder callback
ContextBuilder = Callable[[dict[str, DailyJournal]], dict[str, Any]]


def _default_context_builder(journals: dict[str, DailyJournal]) -> dict[str, Any]:
    """Default context builder: dump journal summaries as JSON."""
    summary = {}
    for codename, journal in journals.items():
        summary[codename] = {
            "journal_id": journal.journal_id,
            "phases": [p.phase for p in journal.phases],
            "metrics": journal.metrics,
        }
    return {"fleet_journals": json.dumps(summary, default=str)}


class FleetOrchestrator:
    """Run agents in waves, bridging context between waves.

    Wave 1 agents run in parallel. Their journals are passed to a
    context_builder callback, whose output is injected into Wave 2's context.
    """

    def __init__(
        self,
        waves: list[list[Agent]],
        context_builder: ContextBuilder | None = None,
        max_workers: int = 4,
        event_bus: EventBus | None = None,
    ):
        self.waves = waves
        self.context_builder = context_builder or _default_context_builder
        self.max_workers = max_workers
        self.event_bus = event_bus

        # Propagate event_bus to all agents
        if event_bus is not None:
            for wave in self.waves:
                for agent in wave:
                    agent.event_bus = event_bus

    def _emit(self, event_type: EventType, **kwargs: Any) -> None:
        """Emit an event if an event bus is configured."""
        if self.event_bus is not None:
            self.event_bus.emit(Event(event_type=event_type, **kwargs))

    def run(
        self,
        date: str | None = None,
        base_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute all waves sequentially, agents within each wave in parallel.

        Returns:
            Fleet cycle result dict with per-agent results and aggregate metrics.
        """
        from datetime import datetime

        date = date or datetime.utcnow().strftime("%Y-%m-%d")
        t0 = time.monotonic()
        total_agents = sum(len(w) for w in self.waves)
        self._emit(EventType.FLEET_START, message=f"Fleet starting: {total_agents} agents in {len(self.waves)} waves", data={"date": date, "total_agents": total_agents, "wave_count": len(self.waves)})

        all_results: dict[str, dict[str, Any]] = {}
        all_failed: list[str] = []
        wave_context: dict[str, Any] = dict(base_context or {})

        for wave_idx, wave_agents in enumerate(self.waves):
            wave_label = f"Wave {wave_idx + 1}"
            logger.info("Fleet: %s — %d agents", wave_label, len(wave_agents))
            self._emit(EventType.WAVE_START, wave=wave_idx + 1, message=f"{wave_label}: {len(wave_agents)} agents", data={"agent_count": len(wave_agents)})

            wave_journals: dict[str, DailyJournal] = {}
            wave_results, wave_failed, wave_journals = self._run_wave(
                wave_agents,
                date,
                wave_context,
                wave_label,
            )
            all_results.update(wave_results)
            all_failed.extend(wave_failed)
            self._emit(EventType.WAVE_DONE, wave=wave_idx + 1, message=f"{wave_label} complete: {len(wave_failed)} failed", data={"completed": len(wave_agents) - len(wave_failed), "failed": len(wave_failed)})

            # Build context for next wave
            if wave_journals and wave_idx < len(self.waves) - 1:
                bridged = self.context_builder(wave_journals)
                wave_context.update(bridged)
                logger.info("Fleet: context bridged for next wave (%d keys)", len(bridged))

        duration = time.monotonic() - t0

        total_tokens = sum(r.get("metrics", {}).get("total_tokens", 0) for r in all_results.values())
        aggregate = {
            "total_agents": sum(len(w) for w in self.waves),
            "agents_completed": sum(len(w) for w in self.waves) - len(all_failed),
            "agents_failed": len(all_failed),
            "failed_agents": all_failed,
            "total_tokens": total_tokens,
            "total_duration_seconds": round(duration, 2),
        }

        logger.info(
            "Fleet: cycle complete — %d/%d agents succeeded, %d tokens, %.1fs",
            aggregate["agents_completed"],
            aggregate["total_agents"],
            total_tokens,
            duration,
        )
        self._emit(EventType.FLEET_DONE, status="completed", message=f"Fleet complete: {aggregate['agents_completed']}/{aggregate['total_agents']} succeeded", data=aggregate)

        return {
            "status": "completed",
            "date": date,
            "agents": all_results,
            **aggregate,
        }

    def _run_wave(
        self,
        agents: list[Agent],
        date: str,
        context: dict[str, Any],
        label: str,
    ) -> tuple[dict[str, dict[str, Any]], list[str], dict[str, DailyJournal]]:
        """Run a wave of agents in the thread pool."""
        results: dict[str, dict[str, Any]] = {}
        failed: list[str] = []
        journals: dict[str, DailyJournal] = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(agent.run, date=date, context=context): agent for agent in agents}

            for future in as_completed(futures):
                agent = futures[future]
                codename = agent.persona.codename
                try:
                    journal = future.result()
                    journals[codename] = journal
                    results[codename] = {
                        "status": "completed",
                        "journal_id": journal.journal_id,
                        "metrics": journal.metrics,
                    }
                    logger.info("Fleet/%s: %s completed — journal %s", label, codename, journal.journal_id)
                except Exception as e:
                    failed.append(codename)
                    results[codename] = {"status": "failed", "error": str(e)}
                    logger.error("Fleet/%s: %s FAILED: %s", label, codename, e, exc_info=True)

        return results, failed, journals
