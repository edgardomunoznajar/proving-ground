"""Verify protocol conformance with minimal stubs."""

from proving_ground.types import ContextProvider, StorageBackend, ToolClient


class StubToolClient:
    def list_tools(self):
        return [{"name": "test_tool"}]

    def call_tool(self, name, arguments):
        return {"result": "ok"}


class StubStorage:
    def execute_query(self, query, params=None, *, fetch_one=False, fetch_all=False):
        if fetch_all:
            return []
        if fetch_one:
            return None
        return None

    def execute_ddl(self, ddl):
        pass


class StubContextProvider:
    def get_context(self, topic, **kwargs):
        return f"context for {topic}"


def test_tool_client_protocol():
    client = StubToolClient()
    assert isinstance(client, ToolClient)
    assert client.list_tools() == [{"name": "test_tool"}]
    assert client.call_tool("test", {}) == {"result": "ok"}


def test_storage_backend_protocol():
    storage = StubStorage()
    assert isinstance(storage, StorageBackend)
    assert storage.execute_query("SELECT 1", fetch_all=True) == []


def test_context_provider_protocol():
    provider = StubContextProvider()
    assert isinstance(provider, ContextProvider)
    assert "context for markets" in provider.get_context("markets")
