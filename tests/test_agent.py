"""Test generic Agent with stub phases."""

from proving_ground.agent import Agent
from proving_ground.journal import JournalStore
from proving_ground.models import AgentPersona, PhaseResult, PhaseStatus
from proving_ground.phases.base import Phase


class StubPhase(Phase):
    def __init__(self, name: str, output_data: dict | None = None):
        self._name = name
        self._output_data = output_data or {}

    @property
    def name(self) -> str:
        return self._name

    def execute(self, context, prior_results):
        return PhaseResult(
            phase=self._name,
            status=PhaseStatus.COMPLETED,
            started_at="2025-01-01T00:00:00",
            finished_at="2025-01-01T00:01:00",
            duration_seconds=60.0,
            data=self._output_data,
            tokens_used=50,
        )


class FailingPhase(Phase):
    @property
    def name(self) -> str:
        return "failing"

    def execute(self, context, prior_results):
        raise RuntimeError("Phase exploded")


class InMemoryStorage:
    """Minimal in-memory StorageBackend for testing."""

    def __init__(self):
        self.queries = []

    def execute_query(self, query, params=None, *, fetch_one=False, fetch_all=False):
        self.queries.append((query, params))
        if fetch_all:
            return []
        if fetch_one:
            return None
        return None

    def execute_ddl(self, ddl):
        self.queries.append((ddl, None))


def test_agent_runs_injected_phases():
    storage = InMemoryStorage()
    journal_store = JournalStore(storage)
    persona = AgentPersona(codename="TestBot", mandate="Test")

    phases = [
        StubPhase("research", {"candidates": [{"symbol": "AAPL"}]}),
        StubPhase("portfolio", {"portfolio": {"selected": []}}),
        StubPhase("journal"),
    ]

    agent = Agent(persona=persona, phases=phases, journal_store=journal_store)
    journal = agent.run(date="2025-01-01")

    assert journal.agent_id == "pg_testbot"
    assert journal.date == "2025-01-01"
    assert len(journal.phases) == 3
    assert all(p.status == PhaseStatus.COMPLETED for p in journal.phases)
    assert journal.metrics["total_tokens"] == 150
    assert journal.metrics["phases_completed"] == 3


def test_agent_handles_phase_failure():
    storage = InMemoryStorage()
    journal_store = JournalStore(storage)
    persona = AgentPersona(codename="CrashBot", mandate="Crash")

    phases = [StubPhase("research"), FailingPhase(), StubPhase("journal")]

    agent = Agent(persona=persona, phases=phases, journal_store=journal_store)
    journal = agent.run(date="2025-01-01")

    assert len(journal.phases) == 3
    assert journal.phases[0].status == PhaseStatus.COMPLETED
    assert journal.phases[1].status == PhaseStatus.FAILED
    assert "Phase exploded" in journal.phases[1].error
    assert journal.phases[2].status == PhaseStatus.COMPLETED
    assert journal.metrics["phases_failed"] == 1


def test_agent_extracts_diagnosis():
    storage = InMemoryStorage()
    journal_store = JournalStore(storage)
    persona = AgentPersona(codename="DiagBot", mandate="Diagnose")

    diag_phase = StubPhase(
        "journal",
        {
            "diagnosis": {
                "bugs_suspected": ["bug1"],
                "improvements": ["improve1"],
                "confidence_score": 0.85,
            }
        },
    )
    agent = Agent(persona=persona, phases=[diag_phase], journal_store=journal_store)
    journal = agent.run(date="2025-01-01")

    assert journal.diagnosis is not None
    assert journal.diagnosis.bugs_suspected == ["bug1"]
    assert journal.diagnosis.confidence_score == 0.85
