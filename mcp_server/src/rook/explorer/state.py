"""
State Persistence - Saves and loads exploration progress.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("explorer.state")


class ExplorerState:
    """
    Manages exploration state persistence.
    Allows resuming exploration from where it left off.
    """

    DEFAULT_STATE_FILE = "knowledge/explorer_state.json"

    def __init__(self, state_file: str | Path | None = None):
        if state_file is None:
            # Find project root
            current = Path(__file__).parent
            while current.parent != current:
                if (current / "knowledge").exists():
                    break
                current = current.parent
            state_file = current / self.DEFAULT_STATE_FILE

        self.state_file = Path(state_file)
        self.state: dict[str, Any] = self._default_state()

    def _default_state(self) -> dict[str, Any]:
        """Return default state structure."""
        return {
            "version": "1.0",
            "started": None,
            "last_updated": None,
            "mode": None,
            "tools_total": 0,
            "tools_tested": 0,
            "tools_completed": [],
            "tools_remaining": [],
            "successes": 0,
            "failures": 0,
            "corrections_found": 0,
            "current_tool": None,
            "per_tool_stats": {},
        }

    def load(self) -> bool:
        """Load state from file."""
        try:
            if self.state_file.exists():
                self.state = json.loads(self.state_file.read_text(encoding="utf-8"))
                logger.info(f"Loaded state from {self.state_file}")
                return True
            else:
                logger.info("No existing state file, starting fresh")
                return False
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return False

    def save(self) -> bool:
        """Save state to file."""
        try:
            self.state["last_updated"] = datetime.now().isoformat()
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
            logger.debug(f"Saved state to {self.state_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            return False

    def start_session(self, mode: str, tools: list[str]) -> None:
        """Start a new exploration session."""
        self.state["started"] = datetime.now().isoformat()
        self.state["mode"] = mode
        self.state["tools_total"] = len(tools)
        self.state["tools_remaining"] = tools.copy()
        self.state["tools_completed"] = []
        self.state["successes"] = 0
        self.state["failures"] = 0
        self.state["corrections_found"] = 0
        self.save()

    def resume_session(self) -> list[str]:
        """Resume a previous session, return remaining tools."""
        return self.state.get("tools_remaining", [])

    def record_result(self, tool_name: str, success: bool, correction_found: bool = False) -> None:
        """Record the result of testing a tool."""
        # Update counts
        if success:
            self.state["successes"] = self.state.get("successes", 0) + 1
        else:
            self.state["failures"] = self.state.get("failures", 0) + 1

        if correction_found:
            self.state["corrections_found"] = self.state.get("corrections_found", 0) + 1

        # Move tool from remaining to completed
        remaining = self.state.get("tools_remaining", [])
        if tool_name in remaining:
            remaining.remove(tool_name)
            self.state["tools_remaining"] = remaining

        completed = self.state.get("tools_completed", [])
        if tool_name not in completed:
            completed.append(tool_name)
            self.state["tools_completed"] = completed

        self.state["tools_tested"] = len(completed)
        self.state["current_tool"] = None

        # Update per-tool stats
        if "per_tool_stats" not in self.state:
            self.state["per_tool_stats"] = {}

        if tool_name not in self.state["per_tool_stats"]:
            self.state["per_tool_stats"][tool_name] = {
                "tests_run": 0,
                "successes": 0,
                "failures": 0,
            }

        stats = self.state["per_tool_stats"][tool_name]
        stats["tests_run"] = stats.get("tests_run", 0) + 1
        if success:
            stats["successes"] = stats.get("successes", 0) + 1
        else:
            stats["failures"] = stats.get("failures", 0) + 1

        self.save()

    def set_current_tool(self, tool_name: str) -> None:
        """Set the currently-being-tested tool."""
        self.state["current_tool"] = tool_name
        self.save()

    def get_progress(self) -> dict[str, Any]:
        """Get progress summary."""
        total = self.state.get("tools_total", 0)
        tested = self.state.get("tools_tested", 0)
        remaining = len(self.state.get("tools_remaining", []))

        return {
            "mode": self.state.get("mode"),
            "started": self.state.get("started"),
            "last_updated": self.state.get("last_updated"),
            "total_tools": total,
            "tested": tested,
            "remaining": remaining,
            "progress_pct": (tested / total * 100) if total > 0 else 0,
            "successes": self.state.get("successes", 0),
            "failures": self.state.get("failures", 0),
            "corrections_found": self.state.get("corrections_found", 0),
            "current_tool": self.state.get("current_tool"),
        }

    def is_complete(self) -> bool:
        """Check if exploration is complete."""
        return len(self.state.get("tools_remaining", [])) == 0

    def reset(self) -> None:
        """Reset state to default."""
        self.state = self._default_state()
        self.save()
