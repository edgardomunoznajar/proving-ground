# Proving Ground

Multi-agent orchestration framework with self-improvement. Run fleets of autonomous agents against any tool surface, collect structured journals, review results, and close the loop with automated fixes — no human in the middle.

## Core Concepts

**Agents and Personas** — An `AgentPersona` defines an agent's identity: codename, mandate, phase sequence, tool allowlist, and config. The `Agent` executor runs injected phases sequentially, builds a `DailyJournal` with metrics and diagnosis, and has zero hardcoded domain logic.

**Phases** — A `Phase` is a single step in an agent's daily cycle. Phases are abstract: subclass `Phase`, implement `execute()`, return a `PhaseResult` with status, timing, tools called, tokens used, and arbitrary data. The agent doesn't know what kind of phases it runs.

**Fleets and Waves** — The `FleetOrchestrator` runs agents in waves. Wave 1 agents execute in parallel via `ThreadPoolExecutor`. Their journals feed a pluggable `ContextBuilder` callback, whose output is injected into Wave 2's context. This enables multi-wave choreography: explorers first, auditors second.

**Journals** — Every agent run produces a `DailyJournal`: phase results, aggregate metrics, and an optional `DiagnosisResult` (bugs suspected, improvements, confidence score, risk assessment, next-day plan). Journals persist to SQL via `JournalStore` with optional JSONL archival.

**Cycle Review** — `CycleReviewer` aggregates journals for a date, calls an LLM with a configurable prompt, and produces structured output: fleet health, summary, patterns, and `ReviewTicket` objects (PG-XXXXX IDs, severity, type, evidence). Run it after every fleet cycle, on a schedule, or on-demand.

**Self-Improvement Loop** — The `Harvester` reads journals from the last N runs, extracts bugs/suggestions/tool errors/risk flags, deduplicates by similarity (75% threshold), and ranks by frequency across agents. The `Actuator` takes top items, finds relevant source files, calls an LLM to generate fixes, applies via search-and-replace, runs tests, and reverts on failure. A cloud variant (`cloud.py`) does the same via GitHub API — creates branches and PRs without touching the local filesystem.

## Architecture

```
Define Personas (mandates, phases, constraints)
        |
        v
  FleetOrchestrator.run()
        |
        v
  Wave 1: Agents run in parallel
    Each agent: execute phases -> build DailyJournal -> persist to storage
        |
        v
  Context bridge: Wave 1 journals -> ContextBuilder -> Wave 2 context
        |
        v
  Wave 2+: Specialized agents act on previous findings
        |
        v
  CycleReviewer: aggregate journals -> LLM critique -> ReviewTickets
        |
        v
  Self-Improvement: harvest -> rank -> actuate -> test -> commit/PR
        |
        v
  Next run with improved codebase
```

## Pluggable Interfaces

All core dependencies are runtime-checkable protocols:

- **`ToolClient`** — `list_tools()` and `call_tool(name, arguments)`. Adapter for MCP servers, function-calling APIs, or local tools.
- **`StorageBackend`** — `execute_query()` and `execute_ddl()`. Ships with `SQLStorageBackend` (SQLAlchemy). Swap in any SQL, cloud, or file-based backend.
- **`ContextProvider`** — `get_context(topic, **kwargs)`. Supplies domain knowledge to agent phases.

## Project Structure

```
proving_ground/
├── __init__.py              # Public API exports
├── types.py                 # Protocol interfaces (ToolClient, StorageBackend, ContextProvider)
├── models.py                # Data models (AgentPersona, PhaseResult, DailyJournal, etc.)
├── agent.py                 # Generic agent executor
├── fleet.py                 # Wave-based fleet orchestration
├── journal.py               # Journal persistence (SQL + JSONL)
├── reviewer.py              # Cycle review and critique
├── llm.py                   # LLM interface via litellm (multi-provider)
├── persona.py               # Load personas from JSON files
├── dashboard/
│   ├── __init__.py          # create_app export
│   ├── app.py               # FastAPI app factory
│   ├── routes.py            # API endpoints (runs, agents, reviews, improvements)
│   └── ui.py                # Single-page HTML frontend
├── phases/
│   ├── base.py              # Abstract Phase class
│   └── common.py            # Utilities (parse_llm_action, now_iso)
├── storage/
│   └── sql.py               # SQLAlchemy-backed StorageBackend
└── self_improve/
    ├── harvester.py          # Extract and rank improvement items from journals
    ├── actuator.py           # Generate and apply fixes (local)
    └── cloud.py              # GitHub API-based fix cycle (branches + PRs)

examples/
├── self_improve_agent.py     # Self-improvement loop: workers → harvester → actuator
└── mcp_debug_agent.py        # MCP tool-surface testing: discover → exercise → validate
```

## Installation

```bash
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
```

Requires Python 3.11+.

## Dependencies

- **litellm** — Unified LLM interface. Supports OpenAI, Anthropic, DeepSeek, Gemini, local models, and more. Router support for multi-provider failover and rate limiting.
- **SQLAlchemy** — Storage backend for journal and review persistence.

## Dashboard

An optional FastAPI-based monitoring UI. Install with:

```bash
pip install -e ".[dashboard]"
```

Start the server:

```python
from sqlalchemy import create_engine
from proving_ground.storage.sql import SQLStorageBackend
from proving_ground.dashboard import create_app

engine = create_engine("sqlite:///proving_ground.db")
storage = SQLStorageBackend(engine)

# Optional: wire up a fleet_runner to enable the "Start Fleet Run" button.
# fleet_runner is any callable(date: str) -> dict that triggers your fleet.
app = create_app(storage, fleet_runner=my_fleet.run)

# uvicorn entrypoint:
# uvicorn myapp:app --reload
```

The HTML frontend is served at `/`. It provides tabbed views for runs, agents, reviews, and improvements, plus a button to trigger fleet runs.

### API Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | HTML dashboard UI |
| `GET /api/runs` | List fleet run dates with agent counts and token totals |
| `GET /api/runs/{date}` | All journals for a specific run date |
| `POST /api/runs` | Trigger a fleet run (requires `fleet_runner` at app creation) |
| `GET /api/runs/status/current` | Check if a fleet run is in progress |
| `GET /api/agents` | List agents with most recent run date |
| `GET /api/agents/{agent_id}/journals` | Recent journals for an agent |
| `GET /api/reviews` | List cycle reviews |
| `GET /api/reviews/{date}` | Full review detail for a date |
| `GET /api/improvements` | Harvested and ranked improvement items from recent runs |

Interactive API docs available at `/docs` (Swagger) and `/redoc`.

## Running Tests

```bash
pytest
```

Tests use in-memory stubs and SQLite for isolation. No external services required.

## Examples

Two runnable examples live in `examples/`. Both work out of the box with in-memory stubs — no API keys or external services needed.

### Self-Improvement Agent (`examples/self_improve_agent.py`)

Demonstrates the full harvest-actuate loop across two waves:

- **Wave 1** — Worker agents (`Alpha`, `Beta`) run tasks, encounter tool errors, and self-diagnose (bugs suspected, improvement suggestions).
- **Wave 2** — An `Improver` agent harvests issues from the Wave 1 journals, ranks them by frequency, and calls an LLM to propose fixes.

```bash
python -m examples.self_improve_agent
```

Key classes: `WorkPhase`, `DiagnosePhase`, `HarvestPhase`, `ActuatePhase`. Swap `fake_llm_call` with a real LiteLLM call to get actual fix proposals.

### MCP Debug Agent (`examples/mcp_debug_agent.py`)

Demonstrates automated MCP/tool-surface testing:

- **Wave 1** — A `Discoverer` agent lists all tools from the MCP server and validates their input schemas (missing descriptions, missing required fields, wrong types).
- **Wave 2** — An `Exerciser` agent calls each tool with sample inputs and validates response shapes against expected keys. Catches schema mismatches, timeouts, and unexpected errors.

```bash
python -m examples.mcp_debug_agent
```

The stub `FlakyToolClient` simulates a server where `get_weather` works, `run_query` returns a wrong shape (missing `columns` key), and `send_email` times out. Replace it with any `ToolClient` implementation to debug a real MCP server.

Key classes: `FlakyToolClient`, `DiscoverToolsPhase`, `ExerciseToolsPhase`.

## Other Use Cases Along the Same Axis

The proving-ground architecture — fleets of persona-driven agents, structured journals, wave-based orchestration, and a self-improvement loop — generalizes beyond its original context. The same machinery applies anywhere you want multiple autonomous perspectives hammering a system surface and harvesting structured feedback.

### MCP / API Development

- **Schema validation**: Agents discover tools that return unexpected shapes, missing fields, or inconsistent types across calls.
- **State machine coverage**: Agents with different mandates hit different state transitions — "the auditor always calls `get_position` before `close_position`, but the aggressive trader calls `close_position` on things that don't exist."
- **Concurrency bugs**: Fleet runs agents in parallel against the same stateful backend — surfaces race conditions, stale reads, double-writes.
- **Regression detection**: Run the fleet after every commit, diff journals against the previous run, surface behavioral changes nobody intended.

### Prompt Engineering / System Prompt QA

- **Prompt robustness testing**: Fleet of agents with different "personalities" (adversarial, naive, literal, creative) hammer the same system prompt to find where it breaks.
- **Tool-use policy validation**: "Does the agent ever call `delete_account` without calling `confirm_action` first?" — the fleet explores the policy surface, journals catch violations.
- **Guardrail testing**: Agents deliberately try to get the system to produce out-of-policy outputs. The journal captures what worked. Self-improvement tightens the guardrails.

### Agent Development Itself

- **Agent-builds-agent**: Your proving-ground agents test an MCP, but the MCP is the agent framework. Agents that use the framework surface issues in the framework, and the self-improvement loop patches the framework. Recursive.
- **Prompt iteration**: Run fleet with prompt v1, harvest journal feedback, actuator rewrites the prompt, run again. Automated prompt optimization without evals infrastructure.
- **Tool description tuning**: Agents misuse a tool, journal says "I expected X but got Y," actuator rewrites the tool's description/schema, next run agents use it correctly.

### LLM Evaluation

- **Model comparison on real tasks**: Swap the engine (DeepSeek, Gemini, Claude, local) and run the same personas against the same MCP. Journals give you structured, comparable output — not just "which chat response is better" but "which model correctly sequenced 14 tool calls to achieve the mandate."
- **Capability regression**: New model version drops, run the fleet, compare journal metrics (phases completed, tools called, errors) against baseline. Catches "GPT-5 is better at chat but worse at function calling" before it hits production.

### DevOps / Infrastructure

- **Runbook validation**: Agents execute operational runbooks (deploy, rollback, scale, failover) against staging. Journals capture where the runbook is ambiguous or wrong. Self-improvement patches the runbook.
- **Chaos engineering with reasoning**: Instead of randomly killing pods, agents decide what to break based on architecture understanding, then observe consequences. More targeted than Chaos Monkey, and the journal explains why it broke things.

### Data Pipeline QA

- **Schema drift detection**: Agents ingest data through a pipeline, journal what they expected vs. what they got. Fleet consensus ("3 of 5 agents flagged this column as suspicious") is a signal.
- **Transformation validation**: Agent runs a pipeline, another agent audits the output. Wave 1 / Wave 2 pattern maps directly.

### Knowledge Base / RAG Validation

- **Coverage testing**: Agents with different personas ask questions against a RAG system. Journals capture where retrieval failed, where answers contradicted source material, where context was insufficient.
- **Staleness detection**: Agents probe for time-sensitive information and flag when answers are outdated. Self-improvement could trigger re-ingestion.

## License

MIT
