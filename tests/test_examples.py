"""Tests for the example use-case agents."""

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from proving_ground.storage.sql import SQLStorageBackend

from examples.mcp_debug_agent import (
    DiscoverToolsPhase,
    ExerciseToolsPhase,
    FlakyToolClient,
    build_fleet as build_mcp_fleet,
)
from examples.self_improve_agent import (
    ActuatePhase,
    DiagnosePhase,
    HarvestPhase,
    WorkPhase,
    build_fleet as build_si_fleet,
    fake_llm_call,
)


def _make_storage() -> SQLStorageBackend:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return SQLStorageBackend(engine)


# ------------------------------------------------------------------
# Self-improvement agent
# ------------------------------------------------------------------


class TestSelfImprovePhases:
    def test_work_phase_records_tools_and_errors(self):
        phase = WorkPhase(
            tools=["search"],
            errors=[{"tool": "search", "error": "timeout"}],
        )
        result = phase.execute({}, [])
        assert result.status.value == "completed"
        assert result.tools_called == ["search"]
        assert len(result.data["tool_errors"]) == 1
        assert result.data["tool_errors"][0]["tool"] == "search"

    def test_diagnose_phase_sets_diagnosis(self):
        phase = DiagnosePhase(bugs=["bug1"], improvements=["imp1"])
        result = phase.execute({}, [])
        diag = result.data["diagnosis"]
        assert diag["bugs_suspected"] == ["bug1"]
        assert diag["improvements"] == ["imp1"]
        assert diag["confidence_score"] == 0.8

    def test_harvest_phase_returns_items(self):
        storage = _make_storage()
        from proving_ground.journal import JournalStore
        JournalStore(storage).ensure_table()

        phase = HarvestPhase(storage, last_n_runs=5)
        result = phase.execute({}, [])
        # No journals yet, so items_found == 0
        assert result.status.value == "completed"
        assert result.data["items_found"] == 0

    def test_actuate_phase_with_no_items(self):
        phase = ActuatePhase(fake_llm_call, max_fixes=3)
        # No prior harvest results → nothing to actuate
        result = phase.execute({}, [])
        assert result.status.value == "completed"
        assert result.data["fixes"] == []

    def test_actuate_phase_with_items(self):
        from proving_ground.models import PhaseResult, PhaseStatus

        harvest_result = PhaseResult(
            phase="harvest",
            status=PhaseStatus.COMPLETED,
            started_at="t0",
            finished_at="t1",
            duration_seconds=0.01,
            data={
                "items_found": 1,
                "items": [{
                    "category": "bug",
                    "message": "search tool times out",
                    "frequency": 2,
                    "agents": ["pg_alpha"],
                    "runs": ["2025-01-01"],
                    "tool_name": "search",
                }],
            },
        )
        phase = ActuatePhase(fake_llm_call, max_fixes=3)
        result = phase.execute({}, [harvest_result])
        assert len(result.data["fixes"]) == 1
        assert result.data["fixes"][0]["status"] == "proposed"


class TestSelfImproveFleet:
    def test_full_fleet_run(self):
        storage = _make_storage()
        fleet = build_si_fleet(storage)
        result = fleet.run(date="2025-01-01")

        assert result["status"] == "completed"
        assert result["total_agents"] == 3
        assert result["agents_completed"] == 3
        assert result["agents_failed"] == 0
        assert "Alpha" in result["agents"]
        assert "Beta" in result["agents"]
        assert "Improver" in result["agents"]


# ------------------------------------------------------------------
# MCP debug agent
# ------------------------------------------------------------------


class TestMcpDebugPhases:
    def test_discover_tools_finds_all(self):
        client = FlakyToolClient()
        phase = DiscoverToolsPhase(client)
        result = phase.execute({}, [])

        assert result.status.value == "completed"
        assert result.data["tools_found"] == 3
        assert "get_weather" in result.data["tool_names"]

    def test_discover_tools_handles_failure(self):
        class BrokenClient:
            def list_tools(self):
                raise ConnectionError("server down")
            def call_tool(self, name, arguments):
                pass

        phase = DiscoverToolsPhase(BrokenClient())
        result = phase.execute({}, [])
        assert result.status.value == "failed"
        assert "list_tools failed" in result.error

    def test_exercise_tools_detects_issues(self):
        client = FlakyToolClient()
        test_cases = [
            {"tool": "get_weather", "args": {"city": "NYC"}, "expected_keys": ["temperature", "conditions"]},
            {"tool": "run_query", "args": {"sql": "SELECT 1"}, "expected_keys": ["rows", "columns"]},
            {"tool": "send_email", "args": {"to": "a@b.c", "body": "hi"}, "expected_keys": ["status", "message_id"]},
        ]
        phase = ExerciseToolsPhase(client, test_cases=test_cases)
        result = phase.execute({}, [])

        assert result.status.value == "completed"
        # get_weather passes, run_query has schema mismatch, send_email raises
        assert result.data["passed"] == 1
        assert result.data["failed"] == 2
        assert len(result.data["tool_errors"]) == 2

        diag = result.data["diagnosis"]
        assert len(diag["bugs_suspected"]) == 2
        assert diag["confidence_score"] < 1.0


class TestMcpDebugFleet:
    def test_full_fleet_run(self):
        storage = _make_storage()
        fleet = build_mcp_fleet(storage)
        result = fleet.run(date="2025-01-01")

        assert result["status"] == "completed"
        assert result["total_agents"] == 2
        assert result["agents_completed"] == 2
        assert "Discoverer" in result["agents"]
        assert "Exerciser" in result["agents"]
