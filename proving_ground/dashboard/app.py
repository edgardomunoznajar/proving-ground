"""Application factory — builds a FastAPI app wired to a StorageBackend."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from proving_ground.dashboard.routes import build_router
from proving_ground.dashboard.ui import INDEX_HTML
from proving_ground.journal import JournalStore
from proving_ground.reviewer import _REVIEWS_TABLE_DDL
from proving_ground.types import StorageBackend

# Type alias: takes a date string, returns fleet result dict
FleetRunner = Callable[[str], dict[str, Any]]


def create_app(
    storage: StorageBackend,
    fleet_runner: FleetRunner | None = None,
    title: str = "Proving Ground",
    cors_origins: list[str] | None = None,
    **kwargs: Any,
) -> FastAPI:
    """Create a FastAPI app wired to the given storage backend.

    Args:
        storage: A StorageBackend instance (e.g. SQLStorageBackend).
        fleet_runner: Optional callback to trigger a fleet run. Takes a date
            string, returns the fleet result dict. If None, the POST /api/runs
            endpoint returns 501.
        title: App title shown in OpenAPI docs.
        cors_origins: Allowed CORS origins. Defaults to ["*"] for local dev.
        **kwargs: Passed through to FastAPI().
    """
    app = FastAPI(title=title, **kwargs)

    if cors_origins is None:
        cors_origins = ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    journal_store = JournalStore(storage)
    journal_store.ensure_table()

    # Ensure reviews table exists (same DDL the CycleReviewer uses)
    storage.execute_ddl(_REVIEWS_TABLE_DDL)

    router = build_router(storage, journal_store, fleet_runner=fleet_runner)
    app.include_router(router, prefix="/api")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return INDEX_HTML

    return app
