"""Test JournalStore with SQLite."""

from sqlalchemy import create_engine

from proving_ground.journal import JournalStore
from proving_ground.models import DailyJournal, DiagnosisResult, PhaseResult, PhaseStatus
from proving_ground.storage.sql import SQLStorageBackend


def _make_store() -> JournalStore:
    engine = create_engine("sqlite:///:memory:")
    storage = SQLStorageBackend(engine)
    store = JournalStore(storage)
    store.ensure_table()
    return store


def test_save_and_load():
    store = _make_store()
    journal = DailyJournal(agent_id="pg_test", date="2025-01-01")
    journal.phases.append(
        PhaseResult(
            phase="research",
            status=PhaseStatus.COMPLETED,
            started_at="2025-01-01T00:00:00",
            finished_at="2025-01-01T00:01:00",
            duration_seconds=60.0,
            tokens_used=100,
        )
    )
    journal.diagnosis = DiagnosisResult(bugs_suspected=["bug1"])

    store.save(journal)

    loaded = store.load("pg_test", limit=10)
    assert len(loaded) == 1
    assert loaded[0]["agent_id"] == "pg_test"
    assert loaded[0]["phases"][0]["phase"] == "research"
    assert loaded[0]["diagnosis"]["bugs_suspected"] == ["bug1"]


def test_load_for_date():
    store = _make_store()

    for agent in ["pg_alpha", "pg_beta"]:
        j = DailyJournal(agent_id=agent, date="2025-01-15")
        store.save(j)

    j_other = DailyJournal(agent_id="pg_gamma", date="2025-01-16")
    store.save(j_other)

    results = store.load_for_date("2025-01-15")
    assert len(results) == 2
    agent_ids = {r["agent_id"] for r in results}
    assert agent_ids == {"pg_alpha", "pg_beta"}


def test_load_empty():
    store = _make_store()
    loaded = store.load("nonexistent")
    assert loaded == []
