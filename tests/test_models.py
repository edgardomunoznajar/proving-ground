"""Test model dataclasses."""

from proving_ground.models import (
    AgentPersona,
    DailyJournal,
    DiagnosisResult,
    PhaseResult,
    PhaseStatus,
    ReviewTicket,
)


def test_persona_from_dict():
    data = {
        "codename": "TestAgent",
        "mandate": "Test mandate",
        "extra_field": "should be ignored",
    }
    p = AgentPersona.from_dict(data)
    assert p.codename == "TestAgent"
    assert p.mandate == "Test mandate"


def test_persona_round_trip():
    p = AgentPersona(codename="Alpha", mandate="Find alpha")
    d = p.to_dict()
    p2 = AgentPersona.from_dict(d)
    assert p2.codename == p.codename
    assert p2.mandate == p.mandate


def test_phase_result_to_dict():
    r = PhaseResult(
        phase="research",
        status=PhaseStatus.COMPLETED,
        started_at="2025-01-01T00:00:00",
        finished_at="2025-01-01T00:01:00",
        duration_seconds=60.0,
        tokens_used=100,
    )
    d = r.to_dict()
    assert d["phase"] == "research"
    assert d["status"] == "completed"
    assert d["tokens_used"] == 100


def test_daily_journal_to_dict():
    j = DailyJournal(agent_id="pg_test", date="2025-01-01")
    j.diagnosis = DiagnosisResult(bugs_suspected=["bug1"], confidence_score=0.9)
    d = j.to_dict()
    assert d["agent_id"] == "pg_test"
    assert d["diagnosis"]["bugs_suspected"] == ["bug1"]
    assert d["diagnosis"]["confidence_score"] == 0.9


def test_review_ticket_to_dict():
    t = ReviewTicket(title="Test ticket", severity="warning")
    d = t.to_dict()
    assert d["title"] == "Test ticket"
    assert d["severity"] == "warning"
    assert d["ticket_id"].startswith("PG-")
