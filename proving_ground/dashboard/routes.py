"""API routes over journals, reviews, improvements, and fleet execution."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query

from proving_ground.journal import JournalStore
from proving_ground.self_improve.harvester import harvest_and_rank
from proving_ground.types import StorageBackend

FleetRunner = Callable[[str], dict[str, Any]]


def build_router(
    storage: StorageBackend,
    journal_store: JournalStore,
    fleet_runner: FleetRunner | None = None,
) -> APIRouter:
    router = APIRouter()

    # Track in-flight run so we don't launch two at once
    _run_lock = threading.Lock()
    _active_run: dict[str, Any] = {"running": False}

    # ------------------------------------------------------------------
    # Fleet runs
    # ------------------------------------------------------------------

    @router.get("/runs")
    def list_runs(limit: int = Query(30, ge=1, le=365)) -> list[dict[str, Any]]:
        """List fleet run dates with agent counts and aggregate metrics."""
        rows = storage.execute_query(
            """
            SELECT date, COUNT(*) as agent_count,
                   SUM(json_extract(metrics_json, '$.total_tokens')) as total_tokens,
                   SUM(json_extract(metrics_json, '$.total_duration_seconds')) as total_duration,
                   GROUP_CONCAT(DISTINCT agent_id) as agents
            FROM proving_ground_journals
            GROUP BY date
            ORDER BY date DESC
            LIMIT :limit
            """,
            {"limit": limit},
            fetch_all=True,
        )
        return [
            {
                "date": r["date"],
                "agent_count": r["agent_count"],
                "total_tokens": r.get("total_tokens") or 0,
                "total_duration_seconds": r.get("total_duration") or 0,
                "agents": (r.get("agents") or "").split(","),
            }
            for r in (rows or [])
        ]

    @router.get("/runs/{date}")
    def get_run(date: str) -> dict[str, Any]:
        """Get all journals for a specific fleet run date."""
        journals = journal_store.load_for_date(date)
        if not journals:
            raise HTTPException(status_code=404, detail=f"No journals found for {date}")
        return {"date": date, "agent_count": len(journals), "journals": journals}

    @router.post("/runs")
    def start_run(date: str | None = None) -> dict[str, Any]:
        """Trigger a fleet run. Requires a fleet_runner callback at app creation."""
        if fleet_runner is None:
            raise HTTPException(status_code=501, detail="No fleet_runner configured")

        with _run_lock:
            if _active_run["running"]:
                raise HTTPException(status_code=409, detail="A fleet run is already in progress")
            _active_run["running"] = True

        date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            result = fleet_runner(date)
            return {"status": "completed", "date": date, "result": result}
        except Exception as e:
            return {"status": "failed", "date": date, "error": str(e)}
        finally:
            with _run_lock:
                _active_run["running"] = False

    @router.get("/runs/status/current")
    def run_status() -> dict[str, Any]:
        """Check if a fleet run is currently in progress."""
        return {"running": _active_run["running"]}

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    @router.get("/agents")
    def list_agents() -> list[dict[str, Any]]:
        """List all agents with their most recent run date."""
        rows = storage.execute_query(
            """
            SELECT agent_id, MAX(date) as last_run, COUNT(*) as journal_count
            FROM proving_ground_journals
            GROUP BY agent_id
            ORDER BY last_run DESC
            """,
            fetch_all=True,
        )
        return [
            {
                "agent_id": r["agent_id"],
                "last_run": r["last_run"],
                "journal_count": r["journal_count"],
            }
            for r in (rows or [])
        ]

    @router.get("/agents/{agent_id}/journals")
    def get_agent_journals(agent_id: str, limit: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
        """Get recent journals for a specific agent."""
        journals = journal_store.load(agent_id, limit=limit)
        if not journals:
            raise HTTPException(status_code=404, detail=f"No journals found for agent {agent_id}")
        return {"agent_id": agent_id, "count": len(journals), "journals": journals}

    # ------------------------------------------------------------------
    # Reviews
    # ------------------------------------------------------------------

    @router.get("/reviews")
    def list_reviews(limit: int = Query(30, ge=1, le=365)) -> list[dict[str, Any]]:
        """List cycle reviews."""
        rows = storage.execute_query(
            """
            SELECT id, review_date, review_type, health_assessment, created_at
            FROM proving_ground_reviews
            ORDER BY review_date DESC
            LIMIT :limit
            """,
            {"limit": limit},
            fetch_all=True,
        )
        results = []
        for r in rows or []:
            health = {}
            if r.get("health_assessment"):
                try:
                    health = json.loads(r["health_assessment"])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(
                {
                    "review_id": r["id"],
                    "date": r["review_date"],
                    "review_type": r["review_type"],
                    "fleet_health": health.get("fleet_health", "unknown"),
                    "summary": health.get("summary", ""),
                    "created_at": r["created_at"],
                }
            )
        return results

    @router.get("/reviews/{date}")
    def get_review(date: str) -> dict[str, Any]:
        """Get the full review for a specific date."""
        row = storage.execute_query(
            """
            SELECT id, review_date, review_type, bugs_json, improvements_json,
                   case_studies_json, health_assessment, created_at
            FROM proving_ground_reviews
            WHERE review_date = :date
            ORDER BY created_at DESC
            LIMIT 1
            """,
            {"date": date},
            fetch_one=True,
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"No review found for {date}")

        def _parse(val: str | None) -> Any:
            if not val:
                return []
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return []

        return {
            "review_id": row["id"],
            "date": row["review_date"],
            "review_type": row["review_type"],
            "bugs": _parse(row.get("bugs_json")),
            "improvements": _parse(row.get("improvements_json")),
            "case_studies": _parse(row.get("case_studies_json")),
            "health": _parse(row.get("health_assessment")),
            "created_at": row["created_at"],
        }

    # ------------------------------------------------------------------
    # Self-improvement
    # ------------------------------------------------------------------

    @router.get("/improvements")
    def list_improvements(
        last_n_runs: int = Query(5, ge=1, le=50),
        top_n: int = Query(20, ge=1, le=100),
    ) -> dict[str, Any]:
        """Harvest and rank current improvement items from recent journals."""
        items = harvest_and_rank(storage, last_n_runs=last_n_runs, top_n=top_n)
        return {
            "count": len(items),
            "items": [item.to_dict() for item in items],
        }

    return router
