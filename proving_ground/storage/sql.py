"""SQLAlchemy-backed StorageBackend implementation."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from proving_ground.types import StorageBackend

logger = logging.getLogger("proving_ground")


class SQLStorageBackend:
    """StorageBackend implementation backed by a SQLAlchemy engine.

    The engine is injected at construction — no global imports, no singletons.
    """

    def __init__(self, engine: Any):
        self.engine = engine

    def execute_query(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        *,
        fetch_one: bool = False,
        fetch_all: bool = False,
    ) -> Any:
        with self.engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            if fetch_one:
                row = result.mappings().fetchone()
                conn.commit()
                return dict(row) if row else None
            if fetch_all:
                rows = result.mappings().fetchall()
                conn.commit()
                return [dict(r) for r in rows]
            conn.commit()
            return None

    def execute_ddl(self, ddl: str) -> None:
        with self.engine.connect() as conn:
            conn.execute(text(ddl))
            conn.commit()


# Verify protocol conformance
assert isinstance(SQLStorageBackend.__new__(SQLStorageBackend), StorageBackend)
