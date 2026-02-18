"""Self-Improvement Harvester + Ranker.

Reads agent journal entries, extracts bugs/suggestions/tool errors,
deduplicates by similarity, and ranks by frequency across agents and runs.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from proving_ground.types import StorageBackend

logger = logging.getLogger("proving_ground")


@dataclass
class ImprovementItem:
    category: str  # bug | suggestion | tool_error | risk_flag
    message: str
    frequency: int = 1
    agents: list[str] = field(default_factory=list)
    runs: list[str] = field(default_factory=list)
    tool_name: str | None = None

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "message": self.message,
            "frequency": self.frequency,
            "agents": sorted(set(self.agents)),
            "runs": sorted(set(self.runs)),
            "tool_name": self.tool_name,
        }


def _similar(a: str, b: str, threshold: float = 0.75) -> bool:
    prefix = min(80, len(a), len(b))
    if a[:prefix] == b[:prefix]:
        return True
    return SequenceMatcher(None, a[:200], b[:200]).ratio() >= threshold


def _merge_into(items: list[ImprovementItem], new: ImprovementItem, threshold: float = 0.75) -> None:
    for existing in items:
        if existing.category != new.category:
            continue
        if existing.tool_name != new.tool_name and existing.tool_name and new.tool_name:
            continue
        if _similar(existing.message, new.message, threshold):
            existing.frequency += 1
            existing.agents.extend(new.agents)
            existing.runs.extend(new.runs)
            if new.tool_name and not existing.tool_name:
                existing.tool_name = new.tool_name
            return
    items.append(new)


def harvest(storage: StorageBackend, last_n_runs: int = 5) -> list[ImprovementItem]:
    """Extract improvement items from the last N fleet runs.

    Reads proving_ground_journals, extracts:
    - bugs_suspected from diagnosis
    - improvements (suggestions) from diagnosis
    - tool_errors from phase data
    - risk_assessment flagged items
    """
    items: list[ImprovementItem] = []

    dates = storage.execute_query(
        "SELECT DISTINCT date FROM proving_ground_journals ORDER BY date DESC LIMIT :n",
        {"n": last_n_runs},
        fetch_all=True,
    )
    if not dates:
        logger.info("SelfImprove: No journal data found")
        return []

    date_list = [d["date"] for d in dates]
    logger.info("SelfImprove: Harvesting from %d runs: %s", len(date_list), date_list)

    placeholders = ",".join(f":d{i}" for i in range(len(date_list)))
    params = {f"d{i}": d for i, d in enumerate(date_list)}
    rows = storage.execute_query(
        f"SELECT agent_id, date, journal_json FROM proving_ground_journals WHERE date IN ({placeholders})",
        params,
        fetch_all=True,
    )

    for row in rows or []:
        agent_id = row["agent_id"]
        run_date = row["date"]
        try:
            journal = json.loads(row["journal_json"]) if row.get("journal_json") else {}
        except (json.JSONDecodeError, TypeError):
            continue

        diagnosis = journal.get("diagnosis") or {}
        if isinstance(diagnosis, str):
            try:
                diagnosis = json.loads(diagnosis)
            except (json.JSONDecodeError, TypeError):
                diagnosis = {}
        if not isinstance(diagnosis, dict):
            diagnosis = {}

        for bug in diagnosis.get("bugs_suspected", []):
            if not bug or not isinstance(bug, str):
                continue
            _merge_into(items, ImprovementItem(category="bug", message=bug.strip(), agents=[agent_id], runs=[run_date]))

        for suggestion in diagnosis.get("improvements", []):
            if not suggestion or not isinstance(suggestion, str):
                continue
            _merge_into(
                items,
                ImprovementItem(category="suggestion", message=suggestion.strip(), agents=[agent_id], runs=[run_date]),
            )

        risk = diagnosis.get("risk_assessment", "")
        if (
            isinstance(risk, str)
            and risk
            and any(kw in risk.lower() for kw in ["high", "critical", "broken", "failure"])
        ):
            _merge_into(
                items,
                ImprovementItem(category="risk_flag", message=risk.strip()[:500], agents=[agent_id], runs=[run_date]),
            )

        for phase in journal.get("phases", []):
            phase_data = phase.get("data", {})
            if not isinstance(phase_data, dict):
                continue
            for err in phase_data.get("tool_errors", []):
                if isinstance(err, dict):
                    tool = err.get("tool", "unknown")
                    error_msg = err.get("error", str(err))
                elif isinstance(err, str):
                    tool = "unknown"
                    error_msg = err
                else:
                    continue
                _merge_into(
                    items,
                    ImprovementItem(
                        category="tool_error",
                        message=str(error_msg).strip()[:500],
                        tool_name=tool,
                        agents=[agent_id],
                        runs=[run_date],
                    ),
                )

    logger.info("SelfImprove: Harvested %d unique items from %d journals", len(items), len(rows or []))
    return items


def rank(items: list[ImprovementItem], top_n: int = 20) -> list[ImprovementItem]:
    """Rank improvement items by frequency, return top N."""
    for item in items:
        item.agents = sorted(set(item.agents))
        item.runs = sorted(set(item.runs))
    ranked = sorted(items, key=lambda x: (x.frequency, len(x.agents), len(x.runs)), reverse=True)
    return ranked[:top_n]


def harvest_and_rank(storage: StorageBackend, last_n_runs: int = 5, top_n: int = 20) -> list[ImprovementItem]:
    """Full pipeline: harvest from storage, deduplicate, rank."""
    items = harvest(storage, last_n_runs=last_n_runs)
    return rank(items, top_n=top_n)


def format_report(items: list[ImprovementItem]) -> str:
    """Format ranked items as a human-readable report."""
    if not items:
        return "No improvement items found."

    lines = []
    lines.append(f"{'#':<4} {'Cat':<12} {'Freq':>4} {'Agents':>6} {'Runs':>4}  {'Tool':<30} Message")
    lines.append("-" * 120)

    for i, item in enumerate(items, 1):
        tool = item.tool_name or "-"
        msg = item.message[:60].replace("\n", " ")
        lines.append(
            f"{i:<4} {item.category:<12} {item.frequency:>4} {len(item.agents):>6} {len(item.runs):>4}  {tool:<30} {msg}"
        )

    cat_counts = Counter(item.category for item in items)
    lines.append("")
    lines.append(f"Categories: {dict(cat_counts)}")
    lines.append(f"Total items: {len(items)}")
    return "\n".join(lines)


def format_llm_prompt(items: list[ImprovementItem], max_items: int = 5) -> str:
    """Format top items as a prompt for an LLM actuator to generate fixes."""
    top = items[:max_items]
    if not top:
        return ""

    sections = []
    for i, item in enumerate(top, 1):
        agents_str = ", ".join(item.agents[:5])
        if len(item.agents) > 5:
            agents_str += f" (+{len(item.agents) - 5} more)"
        sections.append(
            f"## Issue {i} [{item.category}] (reported {item.frequency}x by {len(item.agents)} agents)\n\n"
            f"{item.message}\n\n"
            f"Agents: {agents_str}\n"
            f"Runs: {', '.join(item.runs)}\n" + (f"Tool: {item.tool_name}\n" if item.tool_name else "")
        )

    return (
        "# Fleet Self-Improvement: Top Issues\n\n"
        "The following issues were reported most frequently by the autonomous agent fleet.\n"
        "For each issue, analyze the root cause and suggest a concrete code fix.\n\n" + "\n---\n\n".join(sections)
    )
