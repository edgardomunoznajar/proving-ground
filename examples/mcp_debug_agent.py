"""Example: MCP Debug Agent.

Demonstrates a fleet that exercises MCP tool endpoints, validates responses
against expected schemas, and journals every mismatch and error.

  Wave 1 — Discovery agent lists available tools, validates their schemas.
  Wave 2 — Exerciser agents call each tool with sample inputs, record
            errors, timeouts, and unexpected return shapes.

The stub ``FlakyToolClient`` simulates a real MCP server that occasionally
returns malformed responses or raises errors. Replace it with a real
``ToolClient`` implementation to debug an actual MCP server.

Usage:
    python -m examples.mcp_debug_agent
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from proving_ground import (
    Agent,
    AgentPersona,
    FleetOrchestrator,
    JournalStore,
    Phase,
    PhaseResult,
    PhaseStatus,
    SQLStorageBackend,
    ToolClient,
)

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

# ---------------------------------------------------------------------------
# Stub MCP tool client — simulates a flaky server
# ---------------------------------------------------------------------------


class FlakyToolClient:
    """A ToolClient that deliberately misbehaves for debugging.

    Some tools return correct data, some return wrong shapes, and some raise.
    Swap this out for a real MCP client to debug a live server.
    """

    TOOLS = [
        {
            "name": "get_weather",
            "description": "Get current weather for a city",
            "inputSchema": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
            "expected_keys": ["temperature", "conditions"],
        },
        {
            "name": "run_query",
            "description": "Run a SQL query",
            "inputSchema": {
                "type": "object",
                "properties": {"sql": {"type": "string"}},
                "required": ["sql"],
            },
            "expected_keys": ["rows", "columns"],
        },
        {
            "name": "send_email",
            "description": "Send an email",
            "inputSchema": {
                "type": "object",
                "properties": {"to": {"type": "string"}, "body": {"type": "string"}},
                "required": ["to", "body"],
            },
            "expected_keys": ["status", "message_id"],
        },
    ]

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]}
            for t in self.TOOLS
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "get_weather":
            return {"temperature": 72, "conditions": "sunny"}
        if name == "run_query":
            # Returns wrong shape — missing "columns" key
            return {"rows": [["a", "b"]], "row_count": 2}
        if name == "send_email":
            raise TimeoutError("MCP server did not respond within 10s")
        return {"error": f"Unknown tool: {name}"}


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------


class DiscoverToolsPhase(Phase):
    """List tools from the MCP server and validate their schemas."""

    def __init__(self, tool_client: ToolClient):
        self._client = tool_client

    @property
    def name(self) -> str:
        return "discover_tools"

    def execute(self, context: dict[str, Any], prior_results: list[PhaseResult]) -> PhaseResult:
        started = datetime.now(timezone.utc).isoformat()
        issues: list[str] = []
        tool_errors: list[dict] = []

        try:
            tools = self._client.list_tools()
        except Exception as e:
            return PhaseResult(
                phase=self.name,
                status=PhaseStatus.FAILED,
                started_at=started,
                finished_at=datetime.now(timezone.utc).isoformat(),
                duration_seconds=0.0,
                error=f"list_tools failed: {e}",
                data={"tool_errors": [{"tool": "list_tools", "error": str(e)}]},
            )

        for tool in tools:
            name = tool.get("name", "<unnamed>")
            schema = tool.get("inputSchema", {})
            if not tool.get("description"):
                issues.append(f"{name}: missing description")
            if schema.get("type") != "object":
                issues.append(f"{name}: inputSchema.type is not 'object'")
            if not schema.get("properties"):
                issues.append(f"{name}: inputSchema has no properties")
            if not schema.get("required"):
                issues.append(f"{name}: inputSchema has no required fields")

        for issue in issues:
            tool_errors.append({"tool": "schema_validation", "error": issue})

        return PhaseResult(
            phase=self.name,
            status=PhaseStatus.COMPLETED,
            started_at=started,
            finished_at=datetime.now(timezone.utc).isoformat(),
            duration_seconds=0.01,
            tools_called=["list_tools"],
            data={
                "tools_found": len(tools),
                "tool_names": [t.get("name") for t in tools],
                "schema_issues": issues,
                "tool_errors": tool_errors,
            },
        )


class ExerciseToolsPhase(Phase):
    """Call each tool with sample inputs and validate the response shape."""

    def __init__(
        self,
        tool_client: ToolClient,
        test_cases: list[dict[str, Any]] | None = None,
    ):
        self._client = tool_client
        self._test_cases = test_cases or []

    @property
    def name(self) -> str:
        return "exercise_tools"

    def execute(self, context: dict[str, Any], prior_results: list[PhaseResult]) -> PhaseResult:
        started = datetime.now(timezone.utc).isoformat()
        results: list[dict[str, Any]] = []
        tool_errors: list[dict] = []
        tools_called: list[str] = []

        for case in self._test_cases:
            tool_name = case["tool"]
            args = case.get("args", {})
            expected_keys = set(case.get("expected_keys", []))
            tools_called.append(tool_name)

            entry: dict[str, Any] = {"tool": tool_name, "args": args, "status": "ok"}

            try:
                t0 = time.monotonic()
                response = self._client.call_tool(tool_name, args)
                duration = round(time.monotonic() - t0, 4)
                entry["duration_seconds"] = duration
                entry["response_type"] = type(response).__name__

                # Validate response shape
                if expected_keys and isinstance(response, dict):
                    actual_keys = set(response.keys())
                    missing = expected_keys - actual_keys
                    extra = actual_keys - expected_keys
                    if missing:
                        entry["status"] = "schema_mismatch"
                        entry["missing_keys"] = sorted(missing)
                        tool_errors.append({
                            "tool": tool_name,
                            "error": f"Missing keys in response: {sorted(missing)}",
                        })
                    if extra:
                        entry["extra_keys"] = sorted(extra)

                elif expected_keys and not isinstance(response, dict):
                    entry["status"] = "wrong_type"
                    tool_errors.append({
                        "tool": tool_name,
                        "error": f"Expected dict, got {type(response).__name__}",
                    })

            except Exception as e:
                entry["status"] = "error"
                entry["error"] = str(e)
                entry["error_type"] = type(e).__name__
                tool_errors.append({"tool": tool_name, "error": f"{type(e).__name__}: {e}"})

            results.append(entry)

        passed = sum(1 for r in results if r["status"] == "ok")
        failed = len(results) - passed
        bugs = [
            f"{r['tool']}: {r.get('error') or 'missing keys ' + str(r.get('missing_keys'))}"
            for r in results
            if r["status"] != "ok"
        ]

        return PhaseResult(
            phase=self.name,
            status=PhaseStatus.COMPLETED,
            started_at=started,
            finished_at=datetime.now(timezone.utc).isoformat(),
            duration_seconds=0.01,
            tools_called=tools_called,
            tokens_used=0,
            data={
                "results": results,
                "passed": passed,
                "failed": failed,
                "tool_errors": tool_errors,
                "diagnosis": {
                    "bugs_suspected": bugs,
                    "improvements": [
                        f"Fix {failed} tool endpoint(s)" if failed else "All tools healthy",
                    ],
                    "confidence_score": passed / max(len(results), 1),
                    "risk_assessment": "high" if failed > len(results) / 2 else "low",
                },
            },
        )


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def build_fleet(storage: SQLStorageBackend) -> FleetOrchestrator:
    """Build a 2-wave MCP debug fleet."""
    journal_store = JournalStore(storage)
    journal_store.ensure_table()

    tool_client = FlakyToolClient()

    # Test cases: exercise each tool with sample inputs
    test_cases = [
        {
            "tool": "get_weather",
            "args": {"city": "New York"},
            "expected_keys": ["temperature", "conditions"],
        },
        {
            "tool": "run_query",
            "args": {"sql": "SELECT 1"},
            "expected_keys": ["rows", "columns"],
        },
        {
            "tool": "send_email",
            "args": {"to": "test@example.com", "body": "Hello"},
            "expected_keys": ["status", "message_id"],
        },
    ]

    # Wave 1: discover and validate schemas
    discoverer = Agent(
        persona=AgentPersona(codename="Discoverer", mandate="List and validate MCP tool schemas"),
        phases=[DiscoverToolsPhase(tool_client)],
        journal_store=journal_store,
    )

    # Wave 2: exercise tools and validate responses
    exerciser = Agent(
        persona=AgentPersona(codename="Exerciser", mandate="Call each MCP tool and validate responses"),
        phases=[ExerciseToolsPhase(tool_client, test_cases=test_cases)],
        journal_store=journal_store,
    )

    return FleetOrchestrator(waves=[[discoverer], [exerciser]], max_workers=1)


def main() -> dict[str, Any]:
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///proving_ground_example.db")
    storage = SQLStorageBackend(engine)

    fleet = build_fleet(storage)
    result = fleet.run()

    print(f"\nFleet run: {result['status']}")
    print(f"  Agents: {result['agents_completed']}/{result['total_agents']}")

    for codename, agent_result in result["agents"].items():
        print(f"\n  {codename}: {agent_result['status']}")
        if agent_result.get("status") == "completed":
            journal_id = agent_result["journal_id"]
            print(f"    Journal: {journal_id}")

    return result


if __name__ == "__main__":
    main()
