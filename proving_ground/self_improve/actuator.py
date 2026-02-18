"""Self-Improvement Actuator.

Takes top-ranked improvement items, gathers relevant source code context,
calls an LLM to generate fixes, validates with tests, and logs results.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from proving_ground.self_improve.harvester import ImprovementItem

logger = logging.getLogger("proving_ground")


@dataclass
class FixResult:
    item: ImprovementItem
    status: str  # proposed | applied | tested | committed | skipped | failed
    file_path: str | None = None
    diff_summary: str | None = None
    test_passed: bool | None = None
    error: str | None = None
    llm_response: str | None = None

    def to_dict(self) -> dict:
        return {
            "category": self.item.category,
            "message": self.item.message[:200],
            "frequency": self.item.frequency,
            "status": self.status,
            "file_path": self.file_path,
            "diff_summary": self.diff_summary,
            "test_passed": self.test_passed,
            "error": self.error,
        }


def _find_relevant_files(item: ImprovementItem, project_root: Path) -> list[str]:
    """Heuristic: find source files relevant to an improvement item."""
    candidates = []

    if item.tool_name:
        parts = item.tool_name.replace(".", " ").replace("_", " ").split()
        for part in parts:
            if len(part) < 3:
                continue
            for p in project_root.glob("src/**/*.py"):
                if part.lower() in p.name.lower():
                    candidates.append(str(p.relative_to(project_root)))

    path_pattern = re.compile(r"(?:src/[\w/]+\.py|scripts/[\w/]+\.py)")
    for match in path_pattern.findall(item.message):
        full = project_root / match
        if full.exists():
            candidates.append(match)

    seen: set[str] = set()
    result = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result[:5]


def _read_file_excerpt(project_root: Path, rel_path: str, max_lines: int = 150) -> str:
    full = project_root / rel_path
    if not full.exists() or not full.is_file():
        return f"[File not found: {rel_path}]"
    try:
        lines = full.read_text().splitlines()[:max_lines]
        numbered = [f"{i + 1:4d} | {line}" for i, line in enumerate(lines)]
        return "\n".join(numbered)
    except Exception as e:
        return f"[Error reading {rel_path}: {e}]"


def build_fix_prompt(
    item: ImprovementItem,
    file_contexts: dict[str, str],
    system_prompt_prefix: str = "You are a senior developer fixing issues in a software project.",
) -> list[dict[str, str]]:
    """Build the LLM prompt for generating a fix.

    The system_prompt_prefix is configurable — no hardcoded domain references.
    """
    context_sections = ""
    for path, content in file_contexts.items():
        context_sections += f"\n### {path}\n```python\n{content}\n```\n\n"

    system = (
        f"{system_prompt_prefix} "
        "The autonomous agent fleet has repeatedly reported the following issue. "
        "Analyze the root cause and provide a minimal, focused fix.\n\n"
        "RULES:\n"
        "- Output ONLY a JSON object with keys: 'analysis', 'file_path', 'fix_description', 'original_code', 'fixed_code'\n"
        "- 'original_code' must be an EXACT substring of the current file (for search-and-replace)\n"
        "- 'fixed_code' is the replacement code\n"
        "- Keep fixes minimal — change only what's necessary\n"
        "- If the issue is not fixable from the provided context, set 'file_path' to null\n"
        "- Do NOT add comments, docstrings, or unrelated changes\n"
    )

    user = (
        f"## Issue [{item.category}] — reported {item.frequency}x by {len(item.agents)} agents\n\n"
        f"{item.message}\n\n"
        + (f"Tool: {item.tool_name}\n" if item.tool_name else "")
        + f"Agents: {', '.join(item.agents[:8])}\n"
        f"Runs: {', '.join(item.runs)}\n\n"
        f"## Source Code Context\n{context_sections}"
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def parse_fix_response(response: str) -> dict | None:
    """Extract JSON fix from LLM response, handling markdown fences."""
    cleaned = response.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)

    try:
        fix = json.loads(cleaned)
        if isinstance(fix, dict) and "file_path" in fix:
            return fix
    except json.JSONDecodeError:
        pass

    json_match = re.search(r"\{[^{}]*\"file_path\"[^{}]*\}", response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    return None


def _apply_fix(fix: dict, project_root: Path) -> bool:
    file_path = fix.get("file_path")
    original = fix.get("original_code")
    fixed = fix.get("fixed_code")

    if not file_path or not original or not fixed or original == fixed:
        return False

    full_path = project_root / file_path
    if not full_path.exists():
        return False

    content = full_path.read_text()
    if original not in content:
        logger.warning("Actuator: original_code not found in %s", file_path)
        return False

    full_path.write_text(content.replace(original, fixed, 1))
    return True


def _run_tests(project_root: Path, file_path: str | None, test_cmd: list[str] | None = None, timeout: int = 120) -> tuple[bool, str]:
    """Run tests. The test command is configurable."""
    if test_cmd is None:
        test_targets = ["tests/unit/"]
        if file_path:
            stem = Path(file_path).stem
            test_file = f"tests/unit/test_{stem}.py"
            if (project_root / test_file).exists():
                test_targets = [test_file]
        test_cmd = ["python", "-m", "pytest"] + test_targets + ["-q", "--tb=short", "-x"]

    try:
        result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=timeout, cwd=str(project_root))
        output = result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Test timeout exceeded"
    except Exception as e:
        return False, str(e)


def _revert_fix(fix: dict, project_root: Path) -> None:
    file_path = fix.get("file_path")
    original = fix.get("original_code")
    fixed = fix.get("fixed_code")

    if not file_path or not original or not fixed:
        return
    full_path = project_root / file_path
    if not full_path.exists():
        return
    content = full_path.read_text()
    if fixed in content:
        full_path.write_text(content.replace(fixed, original, 1))


def actuate(
    items: list[ImprovementItem],
    project_root: Path,
    llm_call: Any,
    max_fixes: int = 5,
    dry_run: bool = True,
    run_tests: bool = True,
    system_prompt_prefix: str = "You are a senior developer fixing issues in a software project.",
    test_cmd: list[str] | None = None,
) -> list[FixResult]:
    """Process top improvement items through an LLM actuator.

    Args:
        items: Ranked improvement items from the harvester.
        project_root: Path to the project root directory.
        llm_call: Callable(messages: list[dict]) -> str. The LLM call function.
        max_fixes: Maximum number of items to attempt fixing.
        dry_run: If True, propose fixes but don't apply them.
        run_tests: If True, run tests after applying each fix.
        system_prompt_prefix: Configurable system prompt opening.
        test_cmd: Override test command (default: pytest).
    """
    results: list[FixResult] = []

    for item in items[:max_fixes]:
        logger.info("Actuator: Processing [%s] freq=%d: %s", item.category, item.frequency, item.message[:80])

        relevant_files = _find_relevant_files(item, project_root)
        if not relevant_files:
            results.append(FixResult(item=item, status="skipped", error="No relevant source files found"))
            continue

        file_contexts = {f: _read_file_excerpt(project_root, f) for f in relevant_files}

        try:
            prompt = build_fix_prompt(item, file_contexts, system_prompt_prefix)
            response = llm_call(prompt)
        except Exception as e:
            logger.error("Actuator: LLM call failed: %s", e)
            results.append(FixResult(item=item, status="failed", error=f"LLM error: {e}"))
            continue

        fix = parse_fix_response(response)
        if not fix or not fix.get("file_path"):
            results.append(FixResult(
                item=item, status="skipped",
                error="LLM did not produce actionable fix",
                llm_response=response[:500],
            ))
            continue

        result = FixResult(
            item=item, status="proposed",
            file_path=fix.get("file_path"),
            diff_summary=fix.get("fix_description", ""),
            llm_response=response[:1000],
        )

        if dry_run:
            results.append(result)
            continue

        applied = _apply_fix(fix, project_root)
        if not applied:
            result.status = "failed"
            result.error = "Could not apply fix (original_code not found in file)"
            results.append(result)
            continue

        result.status = "applied"

        if run_tests:
            passed, test_output = _run_tests(project_root, fix["file_path"], test_cmd)
            result.test_passed = passed
            if not passed:
                logger.warning("Actuator: Tests failed after fix, reverting: %s", fix["file_path"])
                _revert_fix(fix, project_root)
                result.status = "failed"
                result.error = f"Tests failed:\n{test_output[-500:]}"
            else:
                result.status = "tested"

        results.append(result)

    return results
