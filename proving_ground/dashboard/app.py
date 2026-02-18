"""Application factory — builds a FastAPI app wired to a StorageBackend."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from proving_ground.dashboard.routes import build_router
from proving_ground.journal import JournalStore
from proving_ground.reviewer import _REVIEWS_TABLE_DDL
from proving_ground.types import StorageBackend


def create_app(
    storage: StorageBackend,
    title: str = "Proving Ground",
    cors_origins: list[str] | None = None,
    **kwargs: Any,
) -> FastAPI:
    """Create a FastAPI app wired to the given storage backend.

    Args:
        storage: A StorageBackend instance (e.g. SQLStorageBackend).
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

    # Ensure reviews table exists (same DDL the NightlyReviewer uses)
    storage.execute_ddl(_REVIEWS_TABLE_DDL)

    router = build_router(storage, journal_store)
    app.include_router(router, prefix="/api")

    return app
