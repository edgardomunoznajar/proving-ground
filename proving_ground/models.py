"""Data models for the proving-ground agent framework."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PhaseStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class FleetStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class AgentPersona:
    """Defines an agent's identity, mandate, and constraints."""

    codename: str
    mandate: str
    description: str = ""
    max_steps: int = 14
    phase_sequence: list[str] | None = None
    tool_allowlist: list[str] | None = None
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> AgentPersona:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return {
            "codename": self.codename,
            "mandate": self.mandate,
            "description": self.description,
            "max_steps": self.max_steps,
            "phase_sequence": self.phase_sequence,
            "tool_allowlist": self.tool_allowlist,
            "config": self.config,
        }


@dataclass
class PhaseResult:
    """Output from a single phase execution."""

    phase: str
    status: PhaseStatus
    started_at: str
    finished_at: str
    duration_seconds: float
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    tools_called: list[str] = field(default_factory=list)
    tokens_used: int = 0
    llm_provider: str = ""

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "data": self.data,
            "error": self.error,
            "tools_called": self.tools_called,
            "tokens_used": self.tokens_used,
            "llm_provider": self.llm_provider,
        }


@dataclass
class DiagnosisResult:
    """Self-diagnosis output from an agent after journaling."""

    bugs_suspected: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    confidence_score: float = 0.0
    risk_assessment: str = ""
    next_day_plan: str = ""

    def to_dict(self) -> dict:
        return {
            "bugs_suspected": self.bugs_suspected,
            "improvements": self.improvements,
            "confidence_score": self.confidence_score,
            "risk_assessment": self.risk_assessment,
            "next_day_plan": self.next_day_plan,
        }


@dataclass
class DailyJournal:
    """Structured journal entry for a single agent-day."""

    journal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    date: str = ""
    phases: list[PhaseResult] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    diagnosis: DiagnosisResult | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "journal_id": self.journal_id,
            "agent_id": self.agent_id,
            "date": self.date,
            "phases": [p.to_dict() for p in self.phases],
            "metrics": self.metrics,
            "diagnosis": self.diagnosis.to_dict() if self.diagnosis else None,
            "created_at": self.created_at,
        }


@dataclass
class ReviewTicket:
    """Output from nightly review."""

    ticket_id: str = field(default_factory=lambda: f"PG-{uuid.uuid4().hex[:6].upper()}")
    review_date: str = ""
    ticket_type: str = ""
    severity: str = "info"
    agent_id: str = ""
    title: str = ""
    description: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "review_date": self.review_date,
            "ticket_type": self.ticket_type,
            "severity": self.severity,
            "agent_id": self.agent_id,
            "title": self.title,
            "description": self.description,
            "evidence": self.evidence,
        }
