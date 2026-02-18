"""Test FleetOrchestrator with stub agents."""

from proving_ground.agent import Agent
from proving_ground.fleet import FleetOrchestrator
from proving_ground.journal import JournalStore
from proving_ground.models import AgentPersona, PhaseResult, PhaseStatus
from proving_ground.phases.base import Phase


class InstantPhase(Phase):
    @property
    def name(self) -> str:
        return "instant"

    def execute(self, context, prior_results):
        return PhaseResult(
            phase="instant",
            status=PhaseStatus.COMPLETED,
            started_at="2025-01-01T00:00:00",
            finished_at="2025-01-01T00:00:01",
            duration_seconds=1.0,
            data={"context_keys": list(context.keys())},
            tokens_used=10,
        )


class InMemoryStorage:
    def __init__(self):
        self.queries = []

    def execute_query(self, query, params=None, *, fetch_one=False, fetch_all=False):
        self.queries.append((query, params))
        if fetch_all:
            return []
        return None

    def execute_ddl(self, ddl):
        pass


def _make_agent(codename: str) -> Agent:
    storage = InMemoryStorage()
    journal_store = JournalStore(storage)
    persona = AgentPersona(codename=codename, mandate=f"{codename} mandate")
    return Agent(persona=persona, phases=[InstantPhase()], journal_store=journal_store)


def test_single_wave():
    agents = [_make_agent("Alpha"), _make_agent("Beta")]
    fleet = FleetOrchestrator(waves=[agents], max_workers=2)
    result = fleet.run(date="2025-01-01")

    assert result["status"] == "completed"
    assert result["total_agents"] == 2
    assert result["agents_completed"] == 2
    assert result["agents_failed"] == 0
    assert "Alpha" in result["agents"]
    assert "Beta" in result["agents"]


def test_two_waves_with_context_bridging():
    wave1 = [_make_agent("Research1")]
    wave2 = [_make_agent("Specialist1")]

    bridged_context = {}

    def custom_builder(journals):
        nonlocal bridged_context
        bridged_context = {"fleet_summary": f"{len(journals)} agents completed"}
        return bridged_context

    fleet = FleetOrchestrator(waves=[wave1, wave2], context_builder=custom_builder, max_workers=1)
    result = fleet.run(date="2025-01-01")

    assert result["status"] == "completed"
    assert result["total_agents"] == 2
    assert "fleet_summary" in bridged_context


def test_empty_waves():
    fleet = FleetOrchestrator(waves=[[]], max_workers=1)
    result = fleet.run(date="2025-01-01")
    assert result["status"] == "completed"
    assert result["total_agents"] == 0
