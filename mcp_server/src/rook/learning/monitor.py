"""
Monitoring and Logging for the Autonomous Learning Agent.

Provides:
- Structured logging to file and console
- Status file for external monitoring
- Progress tracking and reporting
- Real-time status updates
"""

import json
import logging
import sys
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Any
from ..runtime_paths import resolve_writable_knowledge_path

# Paths for monitoring files
LEARNING_DIR = resolve_writable_knowledge_path()
LOG_FILE = resolve_writable_knowledge_path("learning_agent.log")
STATUS_FILE = resolve_writable_knowledge_path("agent_status.json")


def setup_logging(verbose: bool = False, log_to_file: bool = True) -> logging.Logger:
    """
    Configure logging for the learning agent.

    Args:
        verbose: Enable DEBUG level logging
        log_to_file: Also write logs to file

    Returns:
        Configured logger
    """
    # Create learning directory if needed
    LEARNING_DIR.mkdir(parents=True, exist_ok=True)

    # Create logger
    logger = logging.getLogger("rook.learning")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Clear existing handlers and prevent propagation to root
    logger.handlers.clear()
    logger.propagate = False

    # Console handler with colored output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Format: timestamp [LEVEL] message
    console_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler with more detail
    if log_to_file:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

    return logger


@dataclass
class AgentStatus:
    """Current status of the learning agent."""
    # Identity
    session_id: str = ""
    started_at: str = ""
    updated_at: str = ""

    # State
    state: str = "idle"  # idle, orienting, investigating, verifying, handoff, stopped, error
    current_target: str | None = None
    current_phase: str | None = None

    # Progress
    investigations_completed: int = 0
    patterns_discovered: int = 0
    antipatterns_discovered: int = 0
    gaps_resolved: int = 0
    verifications_performed: int = 0

    # Context
    context_usage_estimate: float = 0.0
    estimated_remaining_capacity: int = 0

    # Recent activity
    last_action: str = ""
    last_result: str = ""
    recent_discoveries: list[str] = field(default_factory=list)

    # Errors
    error_count: int = 0
    last_error: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentStatus":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ProgressReporter:
    """
    Reports progress of the learning agent.

    Updates status file and logs progress in a structured way.
    """

    def __init__(self, session_id: str, logger: logging.Logger | None = None):
        """
        Initialize the reporter.

        Args:
            session_id: Current session ID
            logger: Logger to use (creates one if not provided)
        """
        self.session_id = session_id
        self.logger = logger or logging.getLogger("rook.learning")
        self.status = AgentStatus(
            session_id=session_id,
            started_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )
        self._save_status()

    def _save_status(self):
        """Save current status to file."""
        self.status.updated_at = datetime.now().isoformat()
        try:
            STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATUS_FILE.write_text(
                json.dumps(self.status.to_dict(), indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            self.logger.warning(f"Failed to save status: {e}")

    def set_state(self, state: str, target: str | None = None, phase: str | None = None):
        """
        Update agent state.

        Args:
            state: New state (orienting, investigating, verifying, handoff, stopped, error)
            target: Current investigation target
            phase: Current phase within investigation
        """
        self.status.state = state
        self.status.current_target = target
        self.status.current_phase = phase
        self._save_status()

        # Log state change
        if target:
            self.logger.info(f"State: {state} | Target: {target}")
        else:
            self.logger.info(f"State: {state}")

    def log_action(self, action: str, result: str = "", success: bool = True):
        """
        Log an action taken by the agent.

        Args:
            action: Description of the action
            result: Result of the action
            success: Whether it succeeded
        """
        self.status.last_action = action
        self.status.last_result = result

        level = logging.INFO if success else logging.WARNING
        if result:
            self.logger.log(level, f"Action: {action} -> {result}")
        else:
            self.logger.log(level, f"Action: {action}")

        self._save_status()

    def log_discovery(self, discovery_type: str, description: str):
        """
        Log a discovery (pattern, antipattern, insight).

        Args:
            discovery_type: Type of discovery
            description: Description
        """
        entry = f"[{discovery_type}] {description}"
        self.status.recent_discoveries.append(entry)
        # Keep only last 10
        self.status.recent_discoveries = self.status.recent_discoveries[-10:]

        if discovery_type == "pattern":
            self.status.patterns_discovered += 1
            self.logger.info(f"[+] Pattern: {description}")
        elif discovery_type == "antipattern":
            self.status.antipatterns_discovered += 1
            self.logger.info(f"[-] Antipattern: {description}")
        elif discovery_type == "gap_resolved":
            self.status.gaps_resolved += 1
            self.logger.info(f"[*] Gap resolved: {description}")
        elif discovery_type == "verification":
            self.status.verifications_performed += 1
            self.logger.info(f"[v] Verified: {description}")
        else:
            self.logger.info(f"Discovery: {entry}")

        self._save_status()

    def log_investigation_complete(self, target: str, patterns: int, antipatterns: int):
        """
        Log completion of an investigation.

        Args:
            target: What was investigated
            patterns: Number of patterns found
            antipatterns: Number of antipatterns found
        """
        self.status.investigations_completed += 1
        self.logger.info(
            f"Investigation complete: {target} | "
            f"Patterns: {patterns}, Antipatterns: {antipatterns}"
        )
        self._save_status()

    def log_error(self, error: str, fatal: bool = False):
        """
        Log an error.

        Args:
            error: Error message
            fatal: Whether this is a fatal error
        """
        self.status.error_count += 1
        self.status.last_error = error

        if fatal:
            self.status.state = "error"
            self.logger.error(f"FATAL: {error}")
        else:
            self.logger.warning(f"Error: {error}")

        self._save_status()

    def update_context_usage(self, usage: float):
        """
        Update context usage estimate.

        Args:
            usage: Estimated context usage (0.0 to 1.0)
        """
        self.status.context_usage_estimate = usage
        self.status.estimated_remaining_capacity = int((1.0 - usage) * 100)

        if usage > 0.8:
            self.logger.warning(f"Context usage high: {usage:.1%}")
        elif usage > 0.5:
            self.logger.info(f"Context usage: {usage:.1%}")

        self._save_status()

    def log_handoff(self, accomplishments: list[str], next_priorities: list[str]):
        """
        Log session handoff.

        Args:
            accomplishments: What was accomplished
            next_priorities: What next session should focus on
        """
        self.status.state = "handoff"
        self.logger.info("=" * 60)
        self.logger.info("SESSION HANDOFF")
        self.logger.info("=" * 60)
        self.logger.info(f"Session: {self.session_id[:8]}...")
        self.logger.info(f"Investigations: {self.status.investigations_completed}")
        self.logger.info(f"Patterns discovered: {self.status.patterns_discovered}")
        self.logger.info(f"Antipatterns: {self.status.antipatterns_discovered}")
        self.logger.info(f"Gaps resolved: {self.status.gaps_resolved}")
        self.logger.info(f"Verifications: {self.status.verifications_performed}")
        self.logger.info("-" * 60)
        self.logger.info("Accomplishments:")
        for acc in accomplishments[:5]:
            self.logger.info(f"  - {acc}")
        self.logger.info("-" * 60)
        self.logger.info("Next priorities:")
        for pri in next_priorities[:5]:
            self.logger.info(f"  - {pri}")
        self.logger.info("=" * 60)
        self._save_status()

    def get_summary(self) -> str:
        """
        Get a text summary of current status.

        Returns:
            Formatted status summary
        """
        elapsed = ""
        if self.status.started_at:
            try:
                start = datetime.fromisoformat(self.status.started_at)
                elapsed = str(datetime.now() - start).split(".")[0]
            except Exception:
                pass

        lines = [
            f"Session: {self.session_id[:8]}...",
            f"State: {self.status.state}",
            f"Elapsed: {elapsed}",
            f"Investigations: {self.status.investigations_completed}",
            f"Patterns: {self.status.patterns_discovered}",
            f"Antipatterns: {self.status.antipatterns_discovered}",
            f"Gaps resolved: {self.status.gaps_resolved}",
            f"Context usage: {self.status.context_usage_estimate:.1%}",
        ]

        if self.status.current_target:
            lines.append(f"Current: {self.status.current_target}")

        if self.status.last_error:
            lines.append(f"Last error: {self.status.last_error}")

        return "\n".join(lines)


def read_agent_status() -> AgentStatus | None:
    """
    Read current agent status from file.

    Returns:
        AgentStatus or None if not available
    """
    if not STATUS_FILE.exists():
        return None

    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        return AgentStatus.from_dict(data)
    except Exception:
        return None


def print_agent_status():
    """Print current agent status to console."""
    status = read_agent_status()

    if status is None:
        print("No agent status available")
        print(f"Status file: {STATUS_FILE}")
        return

    print("=" * 50)
    print("LEARNING AGENT STATUS")
    print("=" * 50)
    print(f"Session ID: {status.session_id[:8]}..." if status.session_id else "No session")
    print(f"State: {status.state}")
    print(f"Started: {status.started_at}")
    print(f"Updated: {status.updated_at}")
    print("-" * 50)
    print(f"Investigations: {status.investigations_completed}")
    print(f"Patterns discovered: {status.patterns_discovered}")
    print(f"Antipatterns: {status.antipatterns_discovered}")
    print(f"Gaps resolved: {status.gaps_resolved}")
    print(f"Verifications: {status.verifications_performed}")
    print(f"Context usage: {status.context_usage_estimate:.1%}")
    print("-" * 50)

    if status.current_target:
        print(f"Current target: {status.current_target}")
        print(f"Current phase: {status.current_phase}")

    if status.last_action:
        print(f"Last action: {status.last_action}")
        print(f"Last result: {status.last_result}")

    if status.recent_discoveries:
        print("-" * 50)
        print("Recent discoveries:")
        for d in status.recent_discoveries[-5:]:
            print(f"  {d}")

    if status.error_count > 0:
        print("-" * 50)
        print(f"Errors: {status.error_count}")
        if status.last_error:
            print(f"Last error: {status.last_error}")

    print("=" * 50)


def tail_log(lines: int = 20):
    """
    Print last N lines of the log file.

    Args:
        lines: Number of lines to show
    """
    if not LOG_FILE.exists():
        print(f"Log file not found: {LOG_FILE}")
        return

    try:
        content = LOG_FILE.read_text(encoding="utf-8")
        log_lines = content.strip().split("\n")
        for line in log_lines[-lines:]:
            print(line)
    except Exception as e:
        print(f"Error reading log: {e}")
