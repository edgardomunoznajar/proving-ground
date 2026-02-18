"""Test dashboard API routes with in-memory SQLite."""

import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from proving_ground.dashboard.app import create_app
from proving_ground.journal import JournalStore
from proving_ground.models import DailyJournal, DiagnosisResult, PhaseResult, PhaseStatus
from proving_ground.storage.sql import SQLStorageBackend


def _make_storage() -> SQLStorageBackend:
    # StaticPool + check_same_thread=False: ensures the same in-memory DB
    # is shared across the main thread and FastAPI's worker threads.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return SQLStorageBackend(engine)


def _make_client(fleet_runner=None) -> tuple[TestClient, SQLStorageBackend, JournalStore]:
    storage = _make_storage()
    app = create_app(storage, fleet_runner=fleet_runner)
    journal_store = JournalStore(storage)
    journal_store.ensure_table()
    return TestClient(app), storage, journal_store


def _seed_journals(journal_store: JournalStore) -> None:
    """Insert sample journals across two dates and three agents."""
    for agent in ["pg_alpha", "pg_beta"]:
        j = DailyJournal(agent_id=agent, date="2025-01-15")
        j.phases.append(
            PhaseResult(
                phase="research",
                status=PhaseStatus.COMPLETED,
                started_at="2025-01-15T00:00:00",
                finished_at="2025-01-15T00:01:00",
                duration_seconds=60.0,
                tokens_used=500,
                tools_called=["search", "read"],
            )
        )
        j.metrics = {"total_tokens": 500, "total_duration_seconds": 60.0}
        j.diagnosis = DiagnosisResult(
            bugs_suspected=["possible null return"],
            improvements=["add retry logic"],
            confidence_score=0.8,
        )
        journal_store.save(j)

    j2 = DailyJournal(agent_id="pg_gamma", date="2025-01-16")
    j2.phases.append(
        PhaseResult(
            phase="execute",
            status=PhaseStatus.FAILED,
            started_at="2025-01-16T00:00:00",
            finished_at="2025-01-16T00:00:30",
            duration_seconds=30.0,
            tokens_used=200,
            error="timeout",
        )
    )
    j2.metrics = {"total_tokens": 200, "total_duration_seconds": 30.0}
    journal_store.save(j2)


def _seed_review(storage: SQLStorageBackend) -> None:
    """Insert a sample review."""
    storage.execute_ddl(
        """CREATE TABLE IF NOT EXISTS proving_ground_reviews (
            id TEXT PRIMARY KEY, review_date DATE NOT NULL, review_type TEXT NOT NULL,
            bugs_json TEXT, improvements_json TEXT, case_studies_json TEXT,
            health_assessment TEXT, created_at TEXT NOT NULL)"""
    )
    storage.execute_query(
        """
        INSERT INTO proving_ground_reviews
            (id, review_date, review_type, bugs_json, improvements_json,
             case_studies_json, health_assessment, created_at)
        VALUES (:id, :date, :type, :bugs, :improvements, :cases, :health, :created_at)
        """,
        {
            "id": "rev-001",
            "date": "2025-01-15",
            "type": "cycle",
            "bugs": json.dumps([{"title": "null return bug", "severity": "warning"}]),
            "improvements": json.dumps([{"title": "add retry", "severity": "info"}]),
            "cases": json.dumps([]),
            "health": json.dumps(
                {
                    "fleet_health": "healthy",
                    "summary": "Fleet performed well overall.",
                    "patterns": {},
                    "recommended_actions": [],
                }
            ),
            "created_at": "2025-01-15T23:00:00",
        },
    )


# ------------------------------------------------------------------
# Runs
# ------------------------------------------------------------------


def test_list_runs_empty():
    client, _, _ = _make_client()
    resp = client.get("/api/runs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_runs():
    client, _, journal_store = _make_client()
    _seed_journals(journal_store)

    resp = client.get("/api/runs")
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 2

    # Most recent first
    assert runs[0]["date"] == "2025-01-16"
    assert runs[0]["agent_count"] == 1
    assert runs[1]["date"] == "2025-01-15"
    assert runs[1]["agent_count"] == 2


def test_get_run():
    client, _, journal_store = _make_client()
    _seed_journals(journal_store)

    resp = client.get("/api/runs/2025-01-15")
    assert resp.status_code == 200
    data = resp.json()
    assert data["date"] == "2025-01-15"
    assert data["agent_count"] == 2
    assert len(data["journals"]) == 2


def test_get_run_not_found():
    client, _, _ = _make_client()
    resp = client.get("/api/runs/2099-01-01")
    assert resp.status_code == 404


# ------------------------------------------------------------------
# Agents
# ------------------------------------------------------------------


def test_list_agents():
    client, _, journal_store = _make_client()
    _seed_journals(journal_store)

    resp = client.get("/api/agents")
    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) == 3
    agent_ids = {a["agent_id"] for a in agents}
    assert agent_ids == {"pg_alpha", "pg_beta", "pg_gamma"}


def test_get_agent_journals():
    client, _, journal_store = _make_client()
    _seed_journals(journal_store)

    resp = client.get("/api/agents/pg_alpha/journals")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == "pg_alpha"
    assert data["count"] == 1
    assert data["journals"][0]["agent_id"] == "pg_alpha"


def test_get_agent_journals_not_found():
    client, _, _ = _make_client()
    resp = client.get("/api/agents/nonexistent/journals")
    assert resp.status_code == 404


# ------------------------------------------------------------------
# Reviews
# ------------------------------------------------------------------


def test_list_reviews():
    client, storage, journal_store = _make_client()
    _seed_review(storage)

    resp = client.get("/api/reviews")
    assert resp.status_code == 200
    reviews = resp.json()
    assert len(reviews) == 1
    assert reviews[0]["date"] == "2025-01-15"
    assert reviews[0]["fleet_health"] == "healthy"


def test_get_review():
    client, storage, journal_store = _make_client()
    _seed_review(storage)

    resp = client.get("/api/reviews/2025-01-15")
    assert resp.status_code == 200
    data = resp.json()
    assert data["date"] == "2025-01-15"
    assert len(data["bugs"]) == 1
    assert data["health"]["fleet_health"] == "healthy"


def test_get_review_not_found():
    client, _, _ = _make_client()
    resp = client.get("/api/reviews/2099-01-01")
    assert resp.status_code == 404


# ------------------------------------------------------------------
# Improvements
# ------------------------------------------------------------------


def test_list_improvements_empty():
    client, _, _ = _make_client()
    resp = client.get("/api/improvements")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["items"] == []


def test_list_improvements():
    client, _, journal_store = _make_client()
    _seed_journals(journal_store)

    resp = client.get("/api/improvements")
    assert resp.status_code == 200
    data = resp.json()
    # Seeded journals have diagnosis with bugs_suspected and improvements
    assert data["count"] > 0
    categories = {item["category"] for item in data["items"]}
    assert "bug" in categories or "suggestion" in categories


# ------------------------------------------------------------------
# Fleet run trigger
# ------------------------------------------------------------------


def test_start_run_no_runner():
    """POST /api/runs returns 501 when no fleet_runner is configured."""
    client, _, _ = _make_client()
    resp = client.post("/api/runs")
    assert resp.status_code == 501


def test_start_run_success():
    """POST /api/runs triggers the fleet_runner callback and returns results."""

    def fake_runner(date: str) -> dict:
        return {"status": "completed", "total_agents": 2, "agents_completed": 2}

    client, _, _ = _make_client(fleet_runner=fake_runner)
    resp = client.post("/api/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["result"]["total_agents"] == 2


def test_start_run_with_date():
    """POST /api/runs respects the date query parameter."""
    captured = {}

    def fake_runner(date: str) -> dict:
        captured["date"] = date
        return {"status": "completed"}

    client, _, _ = _make_client(fleet_runner=fake_runner)
    resp = client.post("/api/runs?date=2025-03-01")
    assert resp.status_code == 200
    assert captured["date"] == "2025-03-01"


def test_start_run_failure():
    """POST /api/runs returns error details when the runner raises."""

    def failing_runner(date: str) -> dict:
        raise RuntimeError("MCP connection refused")

    client, _, _ = _make_client(fleet_runner=failing_runner)
    resp = client.post("/api/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert "MCP connection refused" in data["error"]


def test_run_status():
    """GET /api/runs/status/current reports whether a run is in progress."""
    client, _, _ = _make_client()
    resp = client.get("/api/runs/status/current")
    assert resp.status_code == 200
    assert resp.json()["running"] is False


# ------------------------------------------------------------------
# HTML frontend
# ------------------------------------------------------------------


def test_index_html():
    """GET / returns the HTML dashboard page."""
    client, _, _ = _make_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Proving Ground" in resp.text
