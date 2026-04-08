"""
Agent Personas
==============

Load personality and role definitions for each agent type.
Each persona has a directory under ``personas/`` containing:

- ``display.json``    model_role, label, description, color, tool_access
- ``personality.md``  voice / character (injected first in system prompt)
- ``role.md``         process, constraints, domain knowledge

Neither ``.md`` file contains tool lists -- those are injected dynamically
by the spawn/planner prompt builders.

Ported from Engram's ``agent/personas/__init__.py``.
"""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_PERSONAS_DIR = Path(__file__).parent

_DISPLAY_DEFAULTS: Dict[str, Any] = {
    "label": "Agent",
    "description": "",
    "color": "#1d9bf0",
    "model_role": "worker",
    "tool_access": "full",
    "avatar": None,
}

_INFRASTRUCTURE_PERSONAS = frozenset({"planner", "guardian"})


# ═════════════════════════════════════════════════════════════════════════
# Core loaders
# ═════════════════════════════════════════════════════════════════════════

def load_persona(
    agent_type: str,
    persona_dir: Optional[Path] = None,
) -> Dict[str, str]:
    """Load personality.md and role.md for an agent type.

    Returns ``{"personality": str, "role": str}``.
    Missing files produce empty strings (not errors).
    """
    base = (persona_dir or _PERSONAS_DIR) / agent_type
    result = {"personality": "", "role": ""}

    for key in ("personality", "role"):
        md_path = base / f"{key}.md"
        if md_path.exists():
            try:
                result[key] = md_path.read_text(encoding="utf-8").strip()
            except Exception as e:
                logger.debug(f"Failed to read {md_path}: {e}")

    return result


def load_display_config(
    agent_type: str,
    persona_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Load display.json for an agent type, merged with defaults.

    Returns a dict with at least: label, description, color,
    model_role, tool_access, avatar.
    """
    base = (persona_dir or _PERSONAS_DIR) / agent_type
    display_path = base / "display.json"

    config = dict(_DISPLAY_DEFAULTS)

    if display_path.exists():
        try:
            with open(display_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                config.update(data)
        except Exception as e:
            logger.debug(f"Failed to read {display_path}: {e}")

    return config


def get_model_role(
    agent_type: str,
    persona_dir: Optional[Path] = None,
) -> str:
    """Return the model_role for an agent type.

    This is the key used to look up the model in a ModelSet.
    E.g. ``get_model_role("scripter")`` returns ``"specialist"``.
    """
    config = load_display_config(agent_type, persona_dir)
    return config["model_role"]


# ═════════════════════════════════════════════════════════════════════════
# Discovery
# ═════════════════════════════════════════════════════════════════════════

def available_personas(persona_dir: Optional[Path] = None) -> List[str]:
    """List agent types that have persona directories.

    A directory counts if it contains at least one .md file or display.json.
    Excludes underscore-prefixed directories and __pycache__.
    """
    base = persona_dir or _PERSONAS_DIR
    result = []
    try:
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            if child.name.startswith("_"):
                continue
            # Check for at least one content file
            has_content = (
                (child / "display.json").exists()
                or any(child.glob("*.md"))
            )
            if has_content:
                result.append(child.name)
    except Exception as e:
        logger.debug(f"Failed to list personas: {e}")
    return result


@lru_cache(maxsize=1)
def build_specialist_summary(persona_dir: Optional[Path] = None) -> str:
    """Build a markdown table of assignable (non-infrastructure) personas.

    Used by the planner to know what agent types it can assign to tasks.
    """
    personas = available_personas(persona_dir)
    assignable = [p for p in personas if p not in _INFRASTRUCTURE_PERSONAS]

    if not assignable:
        return ""

    lines = [
        "## Available Specialists",
        "",
        "| Agent Type | Description | Tool Access |",
        "|-----------|-------------|-------------|",
    ]

    for name in assignable:
        config = load_display_config(name, persona_dir)
        desc = config.get("description", "")
        access = config.get("tool_access", "full")
        lines.append(f"| `{name}` | {desc} | {access} |")

    return "\n".join(lines)
