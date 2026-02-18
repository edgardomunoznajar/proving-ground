"""Protocol interfaces for proving-ground.

These define the boundaries between the framework and its host application.
Implement these to wire proving-ground into your own project.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ToolClient(Protocol):
    """Adapter for tool execution (e.g. MCP, function-calling, local tools)."""

    def list_tools(self) -> list[dict[str, Any]]:
        ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        ...


@runtime_checkable
class StorageBackend(Protocol):
    """Persistence layer — SQL, file, or cloud storage."""

    def execute_query(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        *,
        fetch_one: bool = False,
        fetch_all: bool = False,
    ) -> Any:
        ...

    def execute_ddl(self, ddl: str) -> None:
        ...


@runtime_checkable
class ContextProvider(Protocol):
    """Supplies domain-specific context to agent phases."""

    def get_context(self, topic: str, **kwargs: Any) -> str:
        ...
