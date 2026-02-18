"""proving-ground: Multi-agent orchestration framework with self-improvement."""

from proving_ground.agent import Agent
from proving_ground.fleet import FleetOrchestrator
from proving_ground.journal import JournalStore
from proving_ground.models import (
    AgentPersona,
    DailyJournal,
    DiagnosisResult,
    FleetStatus,
    PhaseResult,
    PhaseStatus,
    ReviewTicket,
)
from proving_ground.phases.base import Phase
from proving_ground.reviewer import NightlyReviewer
from proving_ground.storage.sql import SQLStorageBackend
from proving_ground.types import ContextProvider, StorageBackend, ToolClient

__all__ = [
    # Core
    "Agent",
    "FleetOrchestrator",
    "JournalStore",
    "NightlyReviewer",
    "Phase",
    # Models
    "AgentPersona",
    "DailyJournal",
    "DiagnosisResult",
    "FleetStatus",
    "PhaseResult",
    "PhaseStatus",
    "ReviewTicket",
    # Protocols
    "ContextProvider",
    "StorageBackend",
    "ToolClient",
    # Storage
    "SQLStorageBackend",
]
