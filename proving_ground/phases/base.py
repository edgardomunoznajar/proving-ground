"""Abstract Phase base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from proving_ground.models import PhaseResult


class Phase(ABC):
    """A single step in an agent's daily cycle.

    Implement `execute` to define what this phase does.
    The agent calls phases sequentially, passing prior results forward.
    """

    @property
    def name(self) -> str:
        """Phase name used in logs and journal entries."""
        return self.__class__.__name__

    @abstractmethod
    def execute(self, context: dict[str, Any], prior_results: list[PhaseResult]) -> PhaseResult:
        """Run this phase.

        Args:
            context: Shared context dict (date, knowledge, fleet_context, etc.)
            prior_results: Results from earlier phases in this cycle.

        Returns:
            PhaseResult describing the outcome.
        """
        ...
