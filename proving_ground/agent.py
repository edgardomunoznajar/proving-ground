"""Generic Agent — executes injected phases sequentially, builds a journal."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from proving_ground.journal import JournalStore
from proving_ground.models import AgentPersona, DailyJournal, DiagnosisResult, PhaseResult, PhaseStatus
from proving_ground.phases.base import Phase

logger = logging.getLogger("proving_ground")


class Agent:
    """A single agent that runs a sequence of injected phases.

    No switch statement, no domain knowledge — phases are provided at construction.
    """

    def __init__(
        self,
        persona: AgentPersona,
        phases: list[Phase],
        journal_store: JournalStore,
    ):
        self.persona = persona
        self.phases = phases
        self.journal_store = journal_store

    @property
    def agent_id(self) -> str:
        return f"pg_{self.persona.codename.lower()}"

    def run(self, date: str | None = None, context: dict[str, Any] | None = None) -> DailyJournal:
        """Execute all phases and persist the resulting journal.

        Args:
            date: Override date (default: today UTC).
            context: Shared context dict passed to every phase.

        Returns:
            The completed DailyJournal.
        """
        date = date or datetime.utcnow().strftime("%Y-%m-%d")
        ctx = dict(context or {})
        ctx.setdefault("date", date)
        ctx.setdefault("persona", self.persona)

        logger.info("%s: starting cycle for %s (%d phases)", self.agent_id, date, len(self.phases))

        journal = DailyJournal(agent_id=self.agent_id, date=date)
        prior_results: list[PhaseResult] = []

        for phase in self.phases:
            logger.info("%s: === %s ===", self.agent_id, phase.name)
            try:
                result = phase.execute(ctx, prior_results)
            except Exception as e:
                logger.error("%s: %s FAILED: %s", self.agent_id, phase.name, e, exc_info=True)
                result = PhaseResult(
                    phase=phase.name,
                    status=PhaseStatus.FAILED,
                    started_at=datetime.utcnow().isoformat(),
                    finished_at=datetime.utcnow().isoformat(),
                    duration_seconds=0.0,
                    error=str(e),
                )
            journal.phases.append(result)
            prior_results.append(result)

            # Let phases attach diagnosis data
            if result.data.get("diagnosis") and not journal.diagnosis:
                diag_data = result.data["diagnosis"]
                if isinstance(diag_data, dict):
                    journal.diagnosis = DiagnosisResult(
                        bugs_suspected=diag_data.get("bugs_suspected", []),
                        improvements=diag_data.get("improvements", []),
                        confidence_score=float(diag_data.get("confidence_score", 0.0)),
                        risk_assessment=diag_data.get("risk_assessment", ""),
                        next_day_plan=diag_data.get("next_day_plan", ""),
                    )

        journal.metrics = self._compute_metrics(journal)
        self.journal_store.save(journal)
        logger.info("%s: cycle complete. Journal %s", self.agent_id, journal.journal_id)
        return journal

    @staticmethod
    def _compute_metrics(journal: DailyJournal) -> dict[str, Any]:
        """Aggregate metrics from all phases."""
        total_tokens = sum(p.tokens_used for p in journal.phases)
        total_duration = sum(p.duration_seconds for p in journal.phases)
        all_tools: list[str] = []
        for p in journal.phases:
            all_tools.extend(p.tools_called)
        failed = [p for p in journal.phases if p.status == PhaseStatus.FAILED]

        return {
            "total_tokens": total_tokens,
            "total_duration_seconds": round(total_duration, 2),
            "tools_called_count": len(all_tools),
            "unique_tools": list(set(all_tools)),
            "phases_completed": len([p for p in journal.phases if p.status == PhaseStatus.COMPLETED]),
            "phases_failed": len(failed),
            "failed_phases": [p.phase for p in failed],
        }
