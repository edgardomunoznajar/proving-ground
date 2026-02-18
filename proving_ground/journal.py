"""Journal persistence — save and load agent daily journals."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from proving_ground.models import DailyJournal
from proving_ground.types import StorageBackend

logger = logging.getLogger("proving_ground")

_JOURNALS_TABLE_DDL = """CREATE TABLE IF NOT EXISTS proving_ground_journals (
    id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, date DATE NOT NULL,
    journal_json TEXT, metrics_json TEXT, diagnosis_json TEXT,
    phase_status TEXT, created_at TEXT NOT NULL)"""


class JournalStore:
    """Reads and writes DailyJournal records via a StorageBackend."""

    def __init__(self, storage: StorageBackend, jsonl_dir: Path | None = None):
        self.storage = storage
        self.jsonl_dir = jsonl_dir

    def ensure_table(self) -> None:
        self.storage.execute_ddl(_JOURNALS_TABLE_DDL)

    def save(self, journal: DailyJournal) -> str:
        """Persist journal to storage and optionally append to JSONL."""
        self.storage.execute_query(
            """
            INSERT INTO proving_ground_journals
                (id, agent_id, date, journal_json, metrics_json, diagnosis_json, phase_status, created_at)
            VALUES
                (:id, :agent_id, :date, :journal_json, :metrics_json, :diagnosis_json, :phase_status, :created_at)
            ON CONFLICT (id) DO UPDATE SET
                journal_json = EXCLUDED.journal_json,
                metrics_json = EXCLUDED.metrics_json,
                diagnosis_json = EXCLUDED.diagnosis_json,
                phase_status = EXCLUDED.phase_status
            """,
            {
                "id": journal.journal_id,
                "agent_id": journal.agent_id,
                "date": journal.date,
                "journal_json": json.dumps(journal.to_dict()),
                "metrics_json": json.dumps(journal.metrics),
                "diagnosis_json": json.dumps(journal.diagnosis.to_dict() if journal.diagnosis else {}),
                "phase_status": self._summarize_phase_status(journal),
                "created_at": journal.created_at,
            },
        )

        # Best-effort JSONL append
        if self.jsonl_dir:
            try:
                self.jsonl_dir.mkdir(parents=True, exist_ok=True)
                jsonl_path = self.jsonl_dir / f"{journal.agent_id}.jsonl"
                with open(jsonl_path, "a") as f:
                    f.write(json.dumps(journal.to_dict()) + "\n")
            except (PermissionError, OSError) as e:
                logger.warning("JSONL write failed (non-fatal): %s", e)

        logger.info("Journal saved for %s on %s", journal.agent_id, journal.date)
        return journal.journal_id

    def load(self, agent_id: str, limit: int = 30) -> list[dict[str, Any]]:
        """Load recent journals for an agent."""
        rows = self.storage.execute_query(
            """
            SELECT journal_json FROM proving_ground_journals
            WHERE agent_id = :agent_id
            ORDER BY date DESC
            LIMIT :limit
            """,
            {"agent_id": agent_id, "limit": limit},
            fetch_all=True,
        )
        return [json.loads(r["journal_json"]) for r in (rows or [])]

    def load_for_date(self, date: str) -> list[dict[str, Any]]:
        """Load all agent journals for a specific date."""
        rows = self.storage.execute_query(
            """
            SELECT journal_json FROM proving_ground_journals
            WHERE date = :date
            ORDER BY agent_id
            """,
            {"date": date},
            fetch_all=True,
        )
        return [json.loads(r["journal_json"]) for r in (rows or [])]

    @staticmethod
    def _summarize_phase_status(journal: DailyJournal) -> str:
        parts = [f"{p.phase}:{p.status.value}" for p in journal.phases]
        return ",".join(parts) if parts else "no_phases"
