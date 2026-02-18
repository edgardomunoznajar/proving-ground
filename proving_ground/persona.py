"""Load agent personas from JSON config files."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from proving_ground.models import AgentPersona

logger = logging.getLogger("proving_ground")


def load_persona(codename: str, persona_dir: Path) -> AgentPersona:
    """Load a single persona by codename."""
    path = persona_dir / f"{codename.lower()}.json"
    if not path.exists():
        raise FileNotFoundError(f"Persona not found: {path}")
    with open(path) as f:
        data = json.load(f)
    logger.info("Loaded persona '%s' from %s", codename, path)
    return AgentPersona.from_dict(data)


def load_all_personas(persona_dir: Path) -> dict[str, AgentPersona]:
    """Load all persona JSON files from a directory."""
    if not persona_dir.exists():
        logger.warning("Persona directory not found: %s", persona_dir)
        return {}
    personas: dict[str, AgentPersona] = {}
    for path in sorted(persona_dir.glob("*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
            persona = AgentPersona.from_dict(data)
            personas[persona.codename.lower()] = persona
        except Exception as e:
            logger.error("Failed to load persona from %s: %s", path, e)
    return personas


def list_persona_names(persona_dir: Path) -> list[str]:
    """List available persona codenames without loading them."""
    if not persona_dir.exists():
        return []
    return sorted(p.stem for p in persona_dir.glob("*.json"))
