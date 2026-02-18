"""Cycle reviewer — aggregates journals and generates review tickets."""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from proving_ground.journal import JournalStore
from proving_ground.types import StorageBackend

logger = logging.getLogger("proving_ground")

_REVIEWS_TABLE_DDL = """CREATE TABLE IF NOT EXISTS proving_ground_reviews (
    id TEXT PRIMARY KEY, review_date DATE NOT NULL, review_type TEXT NOT NULL,
    bugs_json TEXT, improvements_json TEXT, case_studies_json TEXT,
    health_assessment TEXT, created_at TEXT NOT NULL)"""


def _summarize_journal(journal: dict) -> dict:
    """Compact summary for context-limited review."""
    summary = {
        "agent_id": journal.get("agent_id", "unknown"),
        "date": journal.get("date", "unknown"),
        "metrics": journal.get("metrics", {}),
        "diagnosis": journal.get("diagnosis"),
    }
    phases = journal.get("phases", [])
    summary["phases"] = [
        {
            "phase": p.get("phase"),
            "status": p.get("status"),
            "duration_seconds": p.get("duration_seconds"),
            "tokens_used": p.get("tokens_used", 0),
            "error": p.get("error"),
        }
        for p in phases
    ]
    return summary


def _parse_review(content: str) -> dict:
    """Extract review JSON from LLM response."""
    content = content.strip()
    if content.startswith("```"):
        first_newline = content.find("\n")
        last_fence = content.rfind("```")
        if first_newline >= 0 and last_fence > first_newline:
            content = content[first_newline + 1 : last_fence].strip()

    idx_start = content.find("{")
    idx_end = content.rfind("}")
    if idx_start >= 0 and idx_end > idx_start:
        try:
            return json.loads(content[idx_start : idx_end + 1])  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            logger.warning("Review: Failed to parse review JSON")
    return {"fleet_health": "unknown", "summary": content[:500], "tickets": []}


class CycleReviewer:
    """Aggregates agent journals and generates review tickets via LLM."""

    def __init__(
        self,
        journal_store: JournalStore,
        storage: StorageBackend,
        llm_call: Callable[[str, str], dict[str, Any]],
        prompt_template: str | Path | None = None,
        fallback_prompt: str = (
            "You are the Cycle Reviewer for an autonomous agent fleet. "
            "Review the agent journals and respond with structured JSON analysis "
            "including fleet_health, summary, tickets, patterns, and recommended_actions."
        ),
    ):
        self.journal_store = journal_store
        self.storage = storage
        self.llm_call = llm_call
        self.prompt_template = prompt_template
        self.fallback_prompt = fallback_prompt

    def ensure_table(self) -> None:
        self.storage.execute_ddl(_REVIEWS_TABLE_DDL)

    def run(self, date: str | None = None, max_journal_chars: int = 80000) -> dict[str, Any]:
        """Run review for all agents on a given date."""
        date = date or datetime.utcnow().strftime("%Y-%m-%d")
        t0 = time.monotonic()

        self.ensure_table()

        journals = self.journal_store.load_for_date(date)
        if not journals:
            logger.info("Review: No journals for %s — skipping", date)
            return {"status": "no_journals", "date": date}

        logger.info("Review: Found %d journals for %s", len(journals), date)

        full_json = json.dumps(journals, default=str)
        if len(full_json) > max_journal_chars:
            journals_for_review = [_summarize_journal(j) for j in journals]
        else:
            journals_for_review = journals

        prompt = self._load_prompt()
        user_message = f"Journals for {date}:\n{json.dumps(journals_for_review, indent=2, default=str)}"

        result = self.llm_call(prompt, user_message)
        content = result.get("content", "")
        review_data = _parse_review(content)
        duration = time.monotonic() - t0

        tickets = review_data.get("tickets", [])
        fleet_health = review_data.get("fleet_health", "unknown")
        summary = review_data.get("summary", content[:500])

        review_id = str(uuid.uuid4())
        self.storage.execute_query(
            """
            INSERT INTO proving_ground_reviews
                (id, review_date, review_type, bugs_json, improvements_json,
                 case_studies_json, health_assessment, created_at)
            VALUES (:id, :date, :type, :bugs, :improvements, :cases, :health, :created_at)
            ON CONFLICT (id) DO UPDATE SET
                bugs_json = EXCLUDED.bugs_json,
                improvements_json = EXCLUDED.improvements_json,
                case_studies_json = EXCLUDED.case_studies_json,
                health_assessment = EXCLUDED.health_assessment
            """,
            {
                "id": review_id,
                "date": date,
                "type": "cycle",
                "bugs": json.dumps([t for t in tickets if t.get("ticket_type") == "bug"]),
                "improvements": json.dumps([t for t in tickets if t.get("ticket_type") == "improvement"]),
                "cases": json.dumps([t for t in tickets if t.get("ticket_type") == "success_case"]),
                "health": json.dumps(
                    {
                        "fleet_health": fleet_health,
                        "summary": summary,
                        "patterns": review_data.get("patterns", {}),
                        "math_errors": review_data.get("math_errors", []),
                        "recommended_actions": review_data.get("recommended_actions", []),
                    }
                ),
                "created_at": datetime.utcnow().isoformat(),
            },
        )

        logger.info("Review: Complete — health=%s, %d tickets, %.1fs", fleet_health, len(tickets), duration)

        return {
            "status": "completed",
            "date": date,
            "review_id": review_id,
            "fleet_health": fleet_health,
            "summary": summary,
            "tickets_created": len(tickets),
            "tokens_used": result.get("tokens_used", 0),
            "duration_seconds": round(duration, 2),
        }

    def _load_prompt(self) -> str:
        if self.prompt_template is None:
            return self.fallback_prompt
        path = Path(self.prompt_template) if isinstance(self.prompt_template, str) else self.prompt_template
        if path.exists():
            return path.read_text()
        logger.warning("Review: Prompt not found at %s, using fallback", path)
        return self.fallback_prompt
