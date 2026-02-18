"""Cloud-compatible self-improvement cycle.

Uses the GitHub API to read source, push fixes to a branch, and create PRs.
No local filesystem access needed — works inside containers.
"""

from __future__ import annotations

import base64
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Callable

import httpx

from proving_ground.self_improve.actuator import FixResult, build_fix_prompt, parse_fix_response
from proving_ground.self_improve.harvester import ImprovementItem, harvest_and_rank
from proving_ground.types import StorageBackend

logger = logging.getLogger("proving_ground")


class GitHubClient:
    """Minimal GitHub API client for file operations and PR creation."""

    def __init__(self, token: str, owner: str, repo: str, default_branch: str = "main"):
        self.token = token
        self.owner = owner
        self.repo = repo
        self.default_branch = default_branch
        self._base = f"https://api.github.com/repos/{owner}/{repo}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def get_file(self, path: str, ref: str | None = None) -> str | None:
        ref = ref or self.default_branch
        try:
            resp = httpx.get(f"{self._base}/contents/{path}", headers=self._headers(), params={"ref": ref}, timeout=30)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return base64.b64decode(resp.json().get("content", "")).decode("utf-8")
        except Exception as e:
            logger.error("GitHub: Failed to read %s: %s", path, e)
            return None

    def get_file_sha(self, path: str, ref: str | None = None) -> str | None:
        ref = ref or self.default_branch
        try:
            resp = httpx.get(f"{self._base}/contents/{path}", headers=self._headers(), params={"ref": ref}, timeout=30)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json().get("sha")
        except Exception:
            return None

    def create_branch(self, branch_name: str) -> bool:
        try:
            resp = httpx.get(f"{self._base}/git/ref/heads/{self.default_branch}", headers=self._headers(), timeout=30)
            resp.raise_for_status()
            base_sha = resp.json()["object"]["sha"]

            resp = httpx.post(
                f"{self._base}/git/refs",
                headers=self._headers(),
                json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
                timeout=30,
            )
            if resp.status_code == 422:
                return True  # already exists
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error("GitHub: Failed to create branch %s: %s", branch_name, e)
            return False

    def update_file(self, path: str, content: str, branch: str, message: str) -> bool:
        sha = self.get_file_sha(path, ref=branch)
        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        try:
            resp = httpx.put(f"{self._base}/contents/{path}", headers=self._headers(), json=payload, timeout=30)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error("GitHub: Failed to update %s on %s: %s", path, branch, e)
            return False

    def create_pr(self, branch: str, title: str, body: str) -> str | None:
        try:
            resp = httpx.post(
                f"{self._base}/pulls",
                headers=self._headers(),
                json={"title": title, "body": body, "head": branch, "base": self.default_branch},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("html_url")
        except Exception as e:
            logger.error("GitHub: Failed to create PR: %s", e)
            return None


def run_cloud_improvement_cycle(
    storage: StorageBackend,
    github: GitHubClient,
    llm_call: Callable[[list[dict]], str],
    max_fixes: int = 3,
    auto_pr: bool = True,
    last_n_runs: int = 5,
    find_relevant_files: Callable[[ImprovementItem], list[str]] | None = None,
    system_prompt_prefix: str = "You are a senior developer fixing issues in a software project.",
) -> dict[str, Any]:
    """Run the full self-improvement cycle in the cloud.

    Args:
        storage: StorageBackend for reading journals.
        github: GitHubClient for reading/writing files and creating PRs.
        llm_call: Callable(messages) -> str for LLM calls.
        max_fixes: Max items to attempt.
        auto_pr: Whether to create a PR automatically.
        last_n_runs: How many fleet runs to harvest from.
        find_relevant_files: Optional custom file finder. Defaults to tool-name heuristic.
        system_prompt_prefix: Configurable system prompt.
    """
    logger.info("Cloud: Starting self-improvement (max_fixes=%d, auto_pr=%s)", max_fixes, auto_pr)

    items = harvest_and_rank(storage, last_n_runs=last_n_runs, top_n=max_fixes * 2)
    if not items:
        return {"status": "no_items", "items_found": 0}

    date_str = datetime.now(UTC).strftime("%Y%m%d")
    branch_name = f"auto-fix/pg-{date_str}"
    branch_created = False
    results: list[dict] = []
    files_changed: list[str] = []

    for item in items[:max_fixes]:
        logger.info("Cloud: Processing [%s] freq=%d: %s", item.category, item.frequency, item.message[:80])

        # Find relevant files
        if find_relevant_files:
            relevant_files = find_relevant_files(item)
        else:
            relevant_files = _default_find_files(item)

        if not relevant_files:
            results.append(FixResult(item=item, status="skipped", error="No relevant source files").to_dict())
            continue

        # Read from GitHub
        file_contexts = {}
        for f in relevant_files:
            content = github.get_file(f)
            if content:
                lines = content.splitlines()[:150]
                numbered = [f"{i + 1:4d} | {line}" for i, line in enumerate(lines)]
                file_contexts[f] = "\n".join(numbered)

        if not file_contexts:
            results.append(FixResult(item=item, status="skipped", error="Could not read files from GitHub").to_dict())
            continue

        # Call LLM
        try:
            prompt = build_fix_prompt(item, file_contexts, system_prompt_prefix)
            response = llm_call(prompt)
        except Exception as e:
            results.append(FixResult(item=item, status="failed", error=f"LLM error: {e}").to_dict())
            continue

        fix = parse_fix_response(response)
        if not fix or not fix.get("file_path"):
            results.append(FixResult(item=item, status="skipped", error="No actionable fix", llm_response=response[:500]).to_dict())
            continue

        fix_result = FixResult(item=item, status="proposed", file_path=fix.get("file_path"), diff_summary=fix.get("fix_description", ""))

        original_code = fix.get("original_code", "")
        fixed_code = fix.get("fixed_code", "")
        if not original_code or not fixed_code or original_code == fixed_code:
            fix_result.status = "skipped"
            fix_result.error = "No code change produced"
            results.append(fix_result.to_dict())
            continue

        current_content = github.get_file(fix["file_path"])
        if not current_content or original_code not in current_content:
            fix_result.status = "failed"
            fix_result.error = "original_code not found in current file"
            results.append(fix_result.to_dict())
            continue

        if not branch_created:
            if not github.create_branch(branch_name):
                fix_result.status = "failed"
                fix_result.error = "Could not create branch"
                results.append(fix_result.to_dict())
                continue
            branch_created = True

        new_content = current_content.replace(original_code, fixed_code, 1)
        commit_msg = f"fix(auto): {fix.get('fix_description', item.message)[:72]}"
        if github.update_file(fix["file_path"], new_content, branch_name, commit_msg):
            fix_result.status = "committed"
            files_changed.append(fix["file_path"])
        else:
            fix_result.status = "failed"
            fix_result.error = "GitHub file update failed"

        results.append(fix_result.to_dict())

    # Create PR
    pr_url = None
    if branch_created and files_changed and auto_pr:
        committed = [r for r in results if r.get("status") == "committed"]
        body_lines = ["## Auto-generated fixes from self-improvement loop\n"]
        body_lines.append(f"**Date**: {date_str}")
        body_lines.append(f"**Fixes**: {len(committed)}\n")
        for r in committed:
            body_lines.append(f"- `{r.get('file_path', '?')}`: {r.get('diff_summary', '')[:100]}")
        body_lines.append("\n---\n*Auto-generated. Review before merging.*")

        pr_url = github.create_pr(
            branch=branch_name,
            title=f"fix(auto): self-improvement {date_str} ({len(committed)} fixes)",
            body="\n".join(body_lines),
        )

    return {
        "status": "completed",
        "items_found": len(items),
        "items_processed": len(results),
        "fixes_committed": len(files_changed),
        "files_changed": files_changed,
        "branch": branch_name if branch_created else None,
        "pr_url": pr_url,
        "results": results,
    }


def _default_find_files(item: ImprovementItem) -> list[str]:
    """Fallback file finder based on tool name heuristics."""
    import re

    candidates = []
    if item.tool_name:
        parts = item.tool_name.replace(".", " ").replace("_", " ").split()
        for part in parts:
            if len(part) >= 3:
                candidates.append(f"src/**/{part}*.py")

    path_pattern = re.compile(r"(?:src/[\w/]+\.py|scripts/[\w/]+\.py)")
    candidates.extend(path_pattern.findall(item.message))
    return candidates[:5]
