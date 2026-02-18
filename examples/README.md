# Examples

Two runnable use-case agents. Both work out of the box with in-memory stubs — no API keys or external services needed.

## Self-Improvement Agent

**`self_improve_agent.py`** — Demonstrates the full harvest-actuate loop across two waves.

```
Wave 1                          Wave 2
┌───────────┐                   ┌───────────────┐
│  Alpha    │──┐                │   Improver    │
│ WorkPhase │  │  journals      │ HarvestPhase  │ reads Wave 1 journals
│ Diagnose  │  ├──────────────▶ │ ActuatePhase  │ proposes fixes via LLM
├───────────┤  │                └───────────────┘
│  Beta     │──┘
│ WorkPhase │
│ Diagnose  │
└───────────┘
```

- **Wave 1** — Worker agents (`Alpha`, `Beta`) run tasks, encounter tool errors, and self-diagnose (bugs suspected, improvement suggestions).
- **Wave 2** — An `Improver` agent harvests issues from the Wave 1 journals, ranks them by frequency, and calls an LLM to propose fixes.

```bash
python -m examples.self_improve_agent
```

### Key classes

| Class | Role |
|---|---|
| `WorkPhase` | Simulates tool calls, records tool errors |
| `DiagnosePhase` | Writes `bugs_suspected` and `improvements` into journal diagnosis |
| `HarvestPhase` | Calls `harvest_and_rank()` on stored journals |
| `ActuatePhase` | Calls `build_fix_prompt()` + LLM to propose fixes |
| `fake_llm_call` | Stub LLM — swap with a real LiteLLM call for actual fixes |

### Extending

To use a real LLM, replace `fake_llm_call`:

```python
import litellm

def real_llm_call(messages: list[dict]) -> str:
    response = litellm.completion(model="gpt-4o", messages=messages)
    return response.choices[0].message.content

fleet = build_fleet(storage)
# Patch the ActuatePhase's LLM call
fleet.waves[1][0].phases[1]._llm_call = real_llm_call
fleet.run()
```

---

## MCP Debug Agent

**`mcp_debug_agent.py`** — Automated MCP/tool-surface testing.

```
Wave 1                          Wave 2
┌──────────────┐                ┌──────────────┐
│  Discoverer  │                │  Exerciser   │
│ list_tools() │  tool names    │ call_tool()  │ for each tool
│ validate     │──────────────▶ │ validate     │ check response shape
│  schemas     │                │  responses   │ record mismatches
└──────────────┘                └──────────────┘
```

- **Wave 1** — `Discoverer` lists all tools and validates input schemas (missing descriptions, missing required fields, wrong types).
- **Wave 2** — `Exerciser` calls each tool with sample inputs and validates response shapes against expected keys. Catches missing keys, wrong return types, and timeouts.

```bash
python -m examples.mcp_debug_agent
```

### Key classes

| Class | Role |
|---|---|
| `FlakyToolClient` | Stub `ToolClient` simulating a broken MCP server |
| `DiscoverToolsPhase` | Calls `list_tools()`, validates each tool's `inputSchema` |
| `ExerciseToolsPhase` | Calls each tool, compares response keys against expected shape |

### What the stub simulates

| Tool | Behavior | Detection |
|---|---|---|
| `get_weather` | Returns correct shape | Pass |
| `run_query` | Missing `columns` key in response | Schema mismatch |
| `send_email` | Raises `TimeoutError` | Error captured in journal |

### Using with a real MCP server

Replace `FlakyToolClient` with any class that implements `ToolClient`:

```python
from my_project.mcp import MyMCPClient

tool_client = MyMCPClient(url="http://localhost:8080")

discoverer = Agent(
    persona=AgentPersona(codename="Discoverer", mandate="Validate MCP schemas"),
    phases=[DiscoverToolsPhase(tool_client)],
    journal_store=journal_store,
)
```
