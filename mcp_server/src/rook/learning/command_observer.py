"""Rhino Command Observation System.

This module captures and structures Rhino command executions, parsing the
command-line dialogue to learn command syntax patterns.

The key insight: Rhino commands are interactive dialogues, not single calls.
We capture the full prompt→input sequence to learn how to script commands.
"""

from __future__ import annotations

import json
import logging
import re
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from ..bridge import get_rhino_host
from ..runtime_paths import resolve_writable_knowledge_path

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================


class InputType(Enum):
    """Types of input a Rhino command prompt can accept."""
    POINT = "point"              # 3D coordinate: x,y,z
    NUMBER = "number"            # Numeric value
    TEXT = "text"                # String input
    OPTION = "option"            # Command option/flag
    CONFIRM = "confirm"          # Enter to confirm/accept default
    SELECTION = "selection"      # Object selection
    UNKNOWN = "unknown"


class PromptType(Enum):
    """Types of prompts Rhino commands display."""
    POINT_REQUEST = "point_request"      # Asking for a point
    NUMBER_REQUEST = "number_request"    # Asking for a number
    OPTION_MENU = "option_menu"          # Showing available options
    CONFIRM_DEFAULT = "confirm_default"  # Press Enter for default
    SELECTION_REQUEST = "selection"      # Select objects
    COMMAND_START = "command_start"      # Command name echo
    UNKNOWN = "unknown"


@dataclass
class DialogueStep:
    """A single step in a command dialogue."""
    prompt: str                              # The raw prompt text
    prompt_type: PromptType                  # Classified prompt type
    input_value: Optional[str] = None        # What was entered
    input_type: Optional[InputType] = None   # Classified input type
    options_available: list[str] = field(default_factory=list)  # Options shown
    default_value: Optional[str] = None      # Default if Enter pressed
    default_description: Optional[str] = None  # What default does

    def to_dict(self) -> dict:
        return {
            "prompt": self.prompt,
            "prompt_type": self.prompt_type.value,
            "input_value": self.input_value,
            "input_type": self.input_type.value if self.input_type else None,
            "options_available": self.options_available,
            "default_value": self.default_value,
            "default_description": self.default_description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DialogueStep":
        return cls(
            prompt=data["prompt"],
            prompt_type=PromptType(data["prompt_type"]),
            input_value=data.get("input_value"),
            input_type=InputType(data["input_type"]) if data.get("input_type") else None,
            options_available=data.get("options_available", []),
            default_value=data.get("default_value"),
            default_description=data.get("default_description"),
        )


@dataclass
class CommandPreconditions:
    """Preconditions required before running a command."""
    requires_selection: bool = False
    selection_type: Optional[str] = None  # "curves", "surfaces", "any", etc.
    selection_count: Optional[str] = None  # "one", "multiple", "two", etc.
    clear_pending_first: bool = True  # Should run _Cancel first

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CommandPreconditions":
        return cls(**data)


@dataclass
class CommandResult:
    """Result of command execution."""
    object_ids: list[str] = field(default_factory=list)
    object_types: list[str] = field(default_factory=list)
    objects_created: int = 0
    objects_modified: int = 0
    objects_deleted: int = 0
    bbox: Optional[dict] = None  # Bounding box of created geometry
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CommandResult":
        return cls(**data)


@dataclass
class CommandObservation:
    """Complete observation of a command execution."""
    id: str                                  # Unique observation ID
    timestamp: str                           # ISO format timestamp
    command: str                             # Command name (e.g., "_Box")
    full_syntax: str                         # Complete command string executed
    mode: str                                # "scripted" or "interactive"
    success: bool                            # Did command complete successfully
    dialogue: list[DialogueStep]             # The prompt→input sequence
    preconditions: CommandPreconditions      # What was needed before
    result: CommandResult                    # What happened after
    intent: Optional[str] = None             # User intent if provided
    raw_history_before: Optional[str] = None # Command history before
    raw_history_after: Optional[str] = None  # Command history after
    execution_time_ms: Optional[int] = None  # How long it took

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "command": self.command,
            "full_syntax": self.full_syntax,
            "mode": self.mode,
            "success": self.success,
            "dialogue": [step.to_dict() for step in self.dialogue],
            "preconditions": self.preconditions.to_dict(),
            "result": self.result.to_dict(),
            "intent": self.intent,
            "raw_history_before": self.raw_history_before,
            "raw_history_after": self.raw_history_after,
            "execution_time_ms": self.execution_time_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CommandObservation":
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            command=data["command"],
            full_syntax=data["full_syntax"],
            mode=data["mode"],
            success=data["success"],
            dialogue=[DialogueStep.from_dict(d) for d in data["dialogue"]],
            preconditions=CommandPreconditions.from_dict(data["preconditions"]),
            result=CommandResult.from_dict(data["result"]),
            intent=data.get("intent"),
            raw_history_before=data.get("raw_history_before"),
            raw_history_after=data.get("raw_history_after"),
            execution_time_ms=data.get("execution_time_ms"),
        )

    @staticmethod
    def generate_id(command: str, timestamp: str) -> str:
        """Generate unique observation ID."""
        hash_input = f"{command}_{timestamp}_{datetime.now().microsecond}"
        return f"obs_{hashlib.md5(hash_input.encode()).hexdigest()[:12]}"


# =============================================================================
# Dialogue Parser
# =============================================================================


class DialogueParser:
    """Parses Rhino command history into structured dialogue steps.

    This is where we extract intelligence from Rhino's prompts - understanding
    what the command is asking for at each step.
    """

    # Patterns for classifying prompts
    POINT_PATTERNS = [
        r"corner", r"point", r"center", r"start", r"end", r"location",
        r"origin", r"position", r"from", r"to", r"vertex", r"pick"
    ]

    NUMBER_PATTERNS = [
        r"radius", r"height", r"length", r"width", r"depth", r"distance",
        r"angle", r"diameter", r"offset", r"tolerance", r"scale", r"factor"
    ]

    SELECTION_PATTERNS = [
        r"select", r"pick object", r"choose", r"click on"
    ]

    # Pattern to extract options from prompts like "( Option1  Option2  Option3 )"
    OPTIONS_PATTERN = re.compile(r'\(\s*([\w\s]+(?:\s{2,}[\w\s]+)*)\s*\)')

    # Pattern to extract default value hints
    DEFAULT_PATTERN = re.compile(r'Press Enter to use (\w+)|<([\d.]+)>|default[:\s]+(\w+)', re.I)

    # Pattern for coordinate input
    COORD_PATTERN = re.compile(r'^-?[\d.]+,-?[\d.]+,-?[\d.]+$')

    # Pattern for command echo
    COMMAND_PATTERN = re.compile(r'^Command:\s*(.+)$|^_?-?(\w+)$')

    def parse_history_diff(
        self,
        history_before: str,
        history_after: str,
        command_string: str
    ) -> list[DialogueStep]:
        """Parse the difference in command history to extract dialogue.

        Args:
            history_before: Command history before execution
            history_after: Command history after execution
            command_string: The command that was executed

        Returns:
            List of DialogueStep objects representing the command dialogue
        """
        # Get new lines in history
        before_lines = set(history_before.strip().split('\n')) if history_before else set()
        after_lines = history_after.strip().split('\n') if history_after else []

        new_lines = []
        for line in after_lines:
            if line and line not in before_lines:
                new_lines.append(line.strip())

        return self.parse_lines(new_lines, command_string)

    def parse_lines(self, lines: list[str], command_string: str) -> list[DialogueStep]:
        """Parse history lines into dialogue steps."""
        steps = []
        current_prompt = None

        # Extract the command parts to match against inputs
        command_parts = command_string.split()
        command_part_index = 0

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip certain noise lines
            if self._is_noise(line):
                continue

            # Check if this is a prompt line
            if self._is_prompt(line):
                # If we have a pending prompt, save it
                if current_prompt is not None:
                    steps.append(current_prompt)

                # Create new prompt
                current_prompt = DialogueStep(
                    prompt=line,
                    prompt_type=self._classify_prompt(line),
                    options_available=self._extract_options(line),
                    default_value=self._extract_default(line),
                )

                # Try to match the next command part as input
                if command_part_index < len(command_parts):
                    part = command_parts[command_part_index]
                    if not part.startswith('_'):  # Skip command/option names
                        current_prompt.input_value = part
                        current_prompt.input_type = self._classify_input(part)
                        command_part_index += 1
                    elif part in ['_Enter', '_enter']:
                        current_prompt.input_value = "_Enter"
                        current_prompt.input_type = InputType.CONFIRM
                        command_part_index += 1
                    else:
                        command_part_index += 1  # Skip option

            elif self._is_input_echo(line):
                # This line shows what was input
                if current_prompt is not None and current_prompt.input_value is None:
                    current_prompt.input_value = line
                    current_prompt.input_type = self._classify_input(line)

            elif "Unknown command" in line:
                # Record failed input attempt
                if current_prompt is not None:
                    current_prompt.input_value = line.replace("Unknown command:", "").strip()
                    current_prompt.input_type = InputType.UNKNOWN

        # Don't forget the last prompt
        if current_prompt is not None:
            steps.append(current_prompt)

        return steps

    def _is_noise(self, line: str) -> bool:
        """Check if line is noise we should ignore."""
        noise_patterns = [
            "Creating meshes",
            "Press Esc to cancel",
            "added to selection",
            "Command History:",
            "Loading",
            "started",
        ]
        return any(pattern in line for pattern in noise_patterns)

    def _is_prompt(self, line: str) -> bool:
        """Check if line is a command prompt."""
        # Prompts typically end with : or have options in parentheses
        if line.endswith(':'):
            return True
        if '(' in line and ')' in line:
            return True
        # Check for common prompt patterns
        prompt_indicators = [
            "corner", "point", "center", "radius", "height", "select",
            "Enter to", "pick", "choose"
        ]
        return any(ind in line.lower() for ind in prompt_indicators)

    def _is_input_echo(self, line: str) -> bool:
        """Check if line is an echo of user input."""
        # Coordinate input
        if self.COORD_PATTERN.match(line):
            return True
        # Number input
        try:
            float(line)
            return True
        except ValueError:
            pass
        return False

    def _classify_prompt(self, prompt: str) -> PromptType:
        """Classify what type of prompt this is."""
        prompt_lower = prompt.lower()

        # Check for selection request
        if any(p in prompt_lower for p in self.SELECTION_PATTERNS):
            return PromptType.SELECTION_REQUEST

        # Check for point request
        if any(p in prompt_lower for p in self.POINT_PATTERNS):
            return PromptType.POINT_REQUEST

        # Check for number request
        if any(p in prompt_lower for p in self.NUMBER_PATTERNS):
            return PromptType.NUMBER_REQUEST

        # Check for default/confirm
        if "enter to" in prompt_lower or "press enter" in prompt_lower:
            return PromptType.CONFIRM_DEFAULT

        # Check for option menu
        if '(' in prompt and ')' in prompt:
            return PromptType.OPTION_MENU

        return PromptType.UNKNOWN

    def _classify_input(self, input_value: str) -> InputType:
        """Classify what type of input was provided."""
        if not input_value:
            return InputType.UNKNOWN

        # Check for Enter/confirm
        if input_value in ["_Enter", "_enter", "Enter", ""]:
            return InputType.CONFIRM

        # Check for coordinate
        if self.COORD_PATTERN.match(input_value):
            return InputType.POINT

        # Check for option (starts with _)
        if input_value.startswith('_'):
            return InputType.OPTION

        # Check for number
        try:
            float(input_value)
            return InputType.NUMBER
        except ValueError:
            pass

        return InputType.TEXT

    def _extract_options(self, prompt: str) -> list[str]:
        """Extract available options from a prompt."""
        match = self.OPTIONS_PATTERN.search(prompt)
        if match:
            options_str = match.group(1)
            # Options are separated by multiple spaces
            options = re.split(r'\s{2,}', options_str.strip())
            return [opt.strip() for opt in options if opt.strip()]
        return []

    def _extract_default(self, prompt: str) -> Optional[str]:
        """Extract default value from prompt."""
        match = self.DEFAULT_PATTERN.search(prompt)
        if match:
            return match.group(1) or match.group(2) or match.group(3)
        return None


# =============================================================================
# Observation Storage
# =============================================================================


class ObservationStore:
    """Stores and retrieves command observations."""

    def __init__(self, storage_path: Path | str):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.observations_file = self.storage_path / "command_observations.json"
        self.index_file = self.storage_path / "command_index.json"
        self._load_index()

    def _load_index(self):
        """Load the command index."""
        if self.index_file.exists():
            with open(self.index_file, 'r') as f:
                self.index = json.load(f)
        else:
            self.index = {
                "commands": {},  # command -> [observation_ids]
                "total_observations": 0,
                "last_updated": None
            }

    def _save_index(self):
        """Save the command index."""
        self.index["last_updated"] = datetime.utcnow().isoformat() + "Z"
        with open(self.index_file, 'w') as f:
            json.dump(self.index, f, indent=2)

    def reload(self) -> int:
        """Reload index from disk. Returns number of observations loaded."""
        self._load_index()
        return self.index.get("total_observations", 0)

    def store(self, observation: CommandObservation) -> str:
        """Store an observation and return its ID."""
        # Load existing observations
        observations = self._load_observations()

        # Add new observation
        observations[observation.id] = observation.to_dict()

        # Update index
        command = observation.command
        if command not in self.index["commands"]:
            self.index["commands"][command] = []
        self.index["commands"][command].append(observation.id)
        self.index["total_observations"] += 1

        # Save
        self._save_observations(observations)
        self._save_index()

        logger.info(f"Stored observation {observation.id} for command {command}")
        return observation.id

    def get(self, observation_id: str) -> Optional[CommandObservation]:
        """Retrieve an observation by ID."""
        observations = self._load_observations()
        if observation_id in observations:
            return CommandObservation.from_dict(observations[observation_id])
        return None

    def get_by_command(self, command: str) -> list[CommandObservation]:
        """Get all observations for a command."""
        if command not in self.index["commands"]:
            return []

        observations = self._load_observations()
        return [
            CommandObservation.from_dict(observations[obs_id])
            for obs_id in self.index["commands"][command]
            if obs_id in observations
        ]

    def get_all_commands(self) -> list[str]:
        """Get list of all observed commands."""
        return list(self.index["commands"].keys())

    def get_stats(self) -> dict:
        """Get storage statistics."""
        return {
            "total_observations": self.index["total_observations"],
            "unique_commands": len(self.index["commands"]),
            "commands": {
                cmd: len(obs_ids)
                for cmd, obs_ids in self.index["commands"].items()
            },
            "last_updated": self.index["last_updated"]
        }

    def remove_by_command(self, command: str) -> int:
        """Remove all observations for a command.

        Args:
            command: The command name (e.g., "-Box" or "-CurveBoolean")

        Returns:
            Number of observations removed
        """
        if command not in self.index["commands"]:
            logger.info(f"No observations found for {command}")
            return 0

        observations = self._load_observations()
        obs_ids = self.index["commands"][command]

        # Remove observations
        removed = 0
        for obs_id in obs_ids:
            if obs_id in observations:
                del observations[obs_id]
                removed += 1

        # Update index
        del self.index["commands"][command]
        self.index["total_observations"] -= removed
        self.index["last_updated"] = datetime.now().isoformat()

        # Save both files
        self._save_observations(observations)
        self._save_index()

        logger.info(f"Removed {removed} observations for {command}")
        return removed

    def _load_observations(self) -> dict:
        """Load all observations from file."""
        if self.observations_file.exists():
            with open(self.observations_file, 'r') as f:
                return json.load(f)
        return {}

    def _save_observations(self, observations: dict):
        """Save observations to file."""
        with open(self.observations_file, 'w') as f:
            json.dump(observations, f, indent=2)


# =============================================================================
# Command Observer
# =============================================================================


class CommandObserver:
    """Executes Rhino commands and captures structured observations.

    This is the core learning component - it wraps command execution with
    full dialogue capture, enabling us to learn command syntax patterns.

    Supports two modes:
    1. Legacy mode (execute_and_observe): Sends full command string at once
    2. Interactive mode (execute_interactive): Step-by-step dialogue capture

    Interactive mode is preferred for learning as it captures real prompts.
    """

    def __init__(
        self,
        http_client,  # httpx.AsyncClient
        base_url: str | None = None,
        store: Optional[ObservationStore] = None
    ):
        self.client = http_client
        resolved_url = base_url or get_rhino_host()
        if resolved_url is None:
            raise RuntimeError(
                "No Rhino instance discovered. "
                "Ensure Rhino is running with RookNative loaded."
            )
        self.base_url = resolved_url.rstrip("/")
        self.parser = DialogueParser()
        self.store = store

    async def _poll_for_prompt_change(
        self,
        previous_prompt: Optional[str],
        timeout_ms: int = 2000,
        poll_interval_ms: int = 100,
        stable_count_required: int = 2
    ) -> dict:
        """
        Poll until the command prompt changes from the previous value.

        This solves the stale prompt bug where Rhino hasn't updated its CommandPrompt
        property yet when we read it after sending a command.

        Args:
            previous_prompt: The prompt text before the command was sent
            timeout_ms: Maximum time to wait for change (default 2000ms)
            poll_interval_ms: Time between polls (default 100ms)
            stable_count_required: Number of consecutive same readings to consider stable

        Returns:
            Dict with prompt data from the final read
        """
        import asyncio

        elapsed = 0
        stable_count = 0
        last_prompt = None
        last_data = None

        # Initial delay to let Rhino process
        await asyncio.sleep(0.1)
        elapsed += 100

        while elapsed < timeout_ms:
            try:
                response = await self.client.get(f"{self.base_url}/command/prompt")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        current_prompt = data.get("data", {}).get("prompt", "Command")

                        # If prompt has changed from previous, track stability
                        if current_prompt != previous_prompt:
                            if current_prompt == last_prompt:
                                stable_count += 1
                                if stable_count >= stable_count_required:
                                    return data.get("data", {})
                            else:
                                last_prompt = current_prompt
                                last_data = data.get("data", {})
                                stable_count = 1
            except Exception as e:
                logger.warning(f"Error polling prompt: {e}")

            await asyncio.sleep(poll_interval_ms / 1000)
            elapsed += poll_interval_ms

        # Timeout - return whatever we have
        if last_data is not None:
            return last_data

        # Fall back to final read
        try:
            response = await self.client.get(f"{self.base_url}/command/prompt")
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return data.get("data", {})
        except Exception:
            pass

        return {"prompt": "Command", "options": [], "default_value": None, "is_active": False}

    # =========================================================================
    # Interactive Command Execution (NEW - Preferred for learning)
    # =========================================================================

    async def start_command_interactive(self, command: str) -> dict:
        """Start a command interactively and get the first prompt.

        Args:
            command: The command to start (e.g., "_-Box")

        Returns:
            Dict with prompt, options, default_value, is_complete, objects_before
        """
        try:
            # Get the current prompt BEFORE starting the command
            # This is critical for detecting when the prompt actually changes
            try:
                initial_response = await self.client.get(f"{self.base_url}/command/prompt")
                if initial_response.status_code == 200:
                    initial_data = initial_response.json()
                    previous_prompt = initial_data.get("data", {}).get("prompt", "Command")
                else:
                    previous_prompt = "Command"
            except Exception:
                previous_prompt = "Command"

            # Start the command
            response = await self.client.post(
                f"{self.base_url}/command/start",
                json={"command": command}
            )
            if response.status_code != 200:
                return {"error": f"HTTP {response.status_code}"}

            start_data = response.json()
            if not start_data.get("success"):
                return {"error": start_data.get("data", "Failed to start command")}

            # Poll until prompt changes from previous value
            # This fixes the stale prompt bug
            prompt_info = await self._poll_for_prompt_change(
                previous_prompt,
                timeout_ms=2000,
                poll_interval_ms=100
            )

            prompt_text = prompt_info.get("prompt", "Command")

            return {
                "prompt": prompt_text,
                "options": prompt_info.get("options", []),
                "default_value": prompt_info.get("default_value"),
                "is_active": prompt_info.get("is_active", False),
                "is_complete": prompt_text == "Command",
                "objects_before": start_data.get("data", {}).get("objects_before", 0),
            }
        except Exception as e:
            logger.error(f"Error starting command: {e}")
            return {"error": str(e)}

    async def send_input_interactive(self, input_value: str) -> dict:
        """Send input to an active command and get the next prompt.

        Args:
            input_value: The input to send (coordinate, number, option, or empty for Enter)

        Returns:
            Dict with prompt, options, default_value, is_complete, objects_created
        """
        try:
            # Get object count before
            obj_count_before = await self.get_object_count()

            # Get the current prompt BEFORE sending input
            try:
                initial_response = await self.client.get(f"{self.base_url}/command/prompt")
                if initial_response.status_code == 200:
                    initial_data = initial_response.json()
                    previous_prompt = initial_data.get("data", {}).get("prompt", "Command")
                else:
                    previous_prompt = None
            except Exception:
                previous_prompt = None

            # Send the input
            response = await self.client.post(
                f"{self.base_url}/command/send",
                json={"input": input_value}
            )
            if response.status_code != 200:
                return {"error": f"HTTP {response.status_code}"}

            # Poll until prompt changes from previous value
            # This fixes the stale prompt bug
            prompt_info = await self._poll_for_prompt_change(
                previous_prompt,
                timeout_ms=2000,
                poll_interval_ms=100
            )

            prompt_text = prompt_info.get("prompt", "Command")

            # Get object count after
            obj_count_after = await self.get_object_count()

            return {
                "prompt": prompt_text,
                "options": prompt_info.get("options", []),
                "default_value": prompt_info.get("default_value"),
                "is_active": prompt_info.get("is_active", False),
                "is_complete": prompt_text == "Command",
                "objects_before": obj_count_before,
                "objects_after": obj_count_after,
                "objects_created": obj_count_after - obj_count_before,
            }
        except Exception as e:
            logger.error(f"Error sending input: {e}")
            return {"error": str(e)}

    async def cancel_command_interactive(self) -> dict:
        """Cancel any active command."""
        try:
            response = await self.client.post(f"{self.base_url}/command/cancel")
            if response.status_code == 200:
                data = response.json()
                return {"cancelled": True, "prompt": data.get("data", {}).get("prompt", "Command")}
            return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    async def get_current_prompt(self) -> dict:
        """Get the current command prompt without sending input."""
        try:
            response = await self.client.get(f"{self.base_url}/command/prompt")
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return data.get("data", {})
            return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    async def execute_interactive(
        self,
        command: str,
        inputs: list[str],
        intent: Optional[str] = None,
        max_steps: int = 20,
    ) -> CommandObservation:
        """Execute a command interactively with step-by-step dialogue capture.

        This is the PREFERRED method for learning command syntax, as it captures
        the actual prompts from Rhino in real-time.

        Args:
            command: The command to execute (e.g., "_-Box")
            inputs: List of inputs to send in sequence (e.g., ["0,0,0", "10,10,0", "5"])
            intent: Optional description of what we're trying to accomplish
            max_steps: Maximum number of dialogue steps before giving up

        Returns:
            CommandObservation with captured dialogue and results
        """
        import time
        start_time = time.time()
        timestamp = datetime.utcnow().isoformat() + "Z"

        # Extract command name
        command_name = self._extract_command_name(command)

        dialogue: list[DialogueStep] = []
        input_index = 0
        objects_before = 0
        objects_after = 0
        success = False
        error_message = None

        try:
            # Cancel any pending command first
            await self.cancel_command_interactive()

            # Start the command
            result = await self.start_command_interactive(command)
            if "error" in result:
                error_message = result["error"]
                success = False
            else:
                objects_before = result.get("objects_before", 0)

                # Capture first prompt as dialogue step
                prompt_text = result.get("prompt", "")
                if prompt_text and prompt_text != "Command":
                    step = DialogueStep(
                        prompt=prompt_text,
                        prompt_type=self._classify_prompt_text(prompt_text),
                        options_available=result.get("options", []),
                        default_value=result.get("default_value"),
                    )
                    dialogue.append(step)

                # Process inputs step by step
                for step_num in range(max_steps):
                    if result.get("is_complete"):
                        success = True
                        objects_after = result.get("objects_after", objects_before)
                        break

                    # Get next input
                    if input_index < len(inputs):
                        input_value = inputs[input_index]
                        input_index += 1
                    else:
                        # No more inputs - try Enter to accept default
                        input_value = ""

                    # Record input in last dialogue step
                    if dialogue:
                        dialogue[-1].input_value = input_value
                        dialogue[-1].input_type = self._classify_input_value(input_value)

                    # Send input
                    result = await self.send_input_interactive(input_value)
                    if "error" in result:
                        error_message = result["error"]
                        break

                    # Capture next prompt as dialogue step
                    prompt_text = result.get("prompt", "")
                    if prompt_text and prompt_text != "Command":
                        step = DialogueStep(
                            prompt=prompt_text,
                            prompt_type=self._classify_prompt_text(prompt_text),
                            options_available=result.get("options", []),
                            default_value=result.get("default_value"),
                        )
                        dialogue.append(step)
                    elif prompt_text == "Command":
                        # Command completed
                        success = True
                        objects_after = result.get("objects_after", objects_before)
                        break
                else:
                    # Max steps reached
                    error_message = f"Command did not complete after {max_steps} steps"
                    await self.cancel_command_interactive()

        except Exception as e:
            error_message = str(e)
            logger.error(f"Interactive execution failed: {e}")

        execution_time = int((time.time() - start_time) * 1000)

        # Build the full syntax string from command + inputs
        full_syntax = command + " " + " ".join(inputs[:input_index])

        # Build result
        cmd_result = CommandResult(
            objects_created=max(0, objects_after - objects_before),
            error_message=error_message,
        )

        # Get object IDs if created
        if cmd_result.objects_created > 0:
            recent_objects = await self.get_recent_objects(cmd_result.objects_created)
            if recent_objects:
                cmd_result.object_ids = [obj.get("id", "") for obj in recent_objects[:cmd_result.objects_created]]
                cmd_result.object_types = [obj.get("type", "") for obj in recent_objects[:cmd_result.objects_created]]

        # Build observation
        observation = CommandObservation(
            id=CommandObservation.generate_id(command_name, timestamp),
            timestamp=timestamp,
            command=command_name,
            full_syntax=full_syntax.strip(),
            mode="interactive",
            success=success,
            dialogue=dialogue,
            preconditions=CommandPreconditions(clear_pending_first=True),
            result=cmd_result,
            intent=intent,
            execution_time_ms=execution_time,
        )

        # Store observation if we have a store
        if self.store:
            self.store.store(observation)
            logger.info(f"Interactive observation stored: {observation.id}")

        return observation

    def _classify_prompt_text(self, prompt: str) -> PromptType:
        """Classify a prompt string into a PromptType."""
        prompt_lower = prompt.lower()

        if any(p in prompt_lower for p in ["select", "pick object", "choose"]):
            return PromptType.SELECTION_REQUEST
        if any(p in prompt_lower for p in ["corner", "point", "center", "start", "end", "location"]):
            return PromptType.POINT_REQUEST
        if any(p in prompt_lower for p in ["radius", "height", "length", "width", "distance", "angle"]):
            return PromptType.NUMBER_REQUEST
        if "enter to" in prompt_lower or "press enter" in prompt_lower:
            return PromptType.CONFIRM_DEFAULT
        if '(' in prompt and ')' in prompt:
            return PromptType.OPTION_MENU
        return PromptType.UNKNOWN

    def _classify_input_value(self, input_value: str) -> InputType:
        """Classify an input value into an InputType."""
        if not input_value or input_value in ["", "_Enter"]:
            return InputType.CONFIRM
        if re.match(r'^-?[\d.]+,-?[\d.]+,-?[\d.]+$', input_value):
            return InputType.POINT
        if input_value.startswith('_'):
            return InputType.OPTION
        try:
            float(input_value)
            return InputType.NUMBER
        except ValueError:
            pass
        return InputType.TEXT

    # =========================================================================
    # Legacy Command Execution (kept for compatibility)
    # =========================================================================

    async def get_command_history(self) -> str:
        """Get current command history from Rhino."""
        try:
            response = await self.client.post(
                f"{self.base_url}/execute",
                json={"code": "import Rhino; print(Rhino.RhinoApp.CommandHistoryWindowText)"}
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return data.get("data", {}).get("output", "")
        except Exception as e:
            logger.warning(f"Failed to get command history: {e}")
        return ""

    async def get_object_count(self) -> int:
        """Get current object count in document."""
        try:
            response = await self.client.get(f"{self.base_url}/document")
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return data.get("data", {}).get("objectCount", 0)
        except Exception as e:
            logger.warning(f"Failed to get object count: {e}")
        return 0

    async def get_recent_objects(self, count: int = 10) -> list[dict]:
        """Get the most recently created objects."""
        try:
            response = await self.client.get(
                f"{self.base_url}/objects",
                params={"limit": count}
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return data.get("data", {}).get("objects", [])
        except Exception as e:
            logger.warning(f"Failed to get recent objects: {e}")
        return []

    async def run_command(self, command_string: str) -> tuple[bool, str]:
        """Execute a Rhino command and return success status."""
        try:
            response = await self.client.post(
                f"{self.base_url}/command",
                json={"command": command_string}
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("success", False), data.get("data", "")
            return False, f"HTTP {response.status_code}"
        except Exception as e:
            return False, str(e)

    async def execute_and_observe(
        self,
        command_string: str,
        intent: Optional[str] = None,
        clear_pending: bool = True
    ) -> CommandObservation:
        """Execute a command and capture a full observation.

        Args:
            command_string: The complete command to execute (e.g., "_-Box 0,0,0 10,10,0 _Enter")
            intent: Optional description of what we're trying to accomplish
            clear_pending: Whether to run _Cancel first (default True)

        Returns:
            CommandObservation with full dialogue and result capture
        """
        import time
        start_time = time.time()
        timestamp = datetime.utcnow().isoformat() + "Z"

        # Extract command name
        command_name = self._extract_command_name(command_string)
        mode = "scripted" if "-" in command_string.split()[0] else "interactive"

        # 1. Clear pending state if requested
        if clear_pending:
            await self.run_command("_Cancel")

        # 2. Capture state before
        history_before = await self.get_command_history()
        object_count_before = await self.get_object_count()

        # 3. Execute the command
        success, result_message = await self.run_command(command_string)

        # 4. Capture state after
        history_after = await self.get_command_history()
        object_count_after = await self.get_object_count()

        # 5. Parse dialogue from history diff
        dialogue = self.parser.parse_history_diff(
            history_before, history_after, command_string
        )

        # 6. Calculate results
        objects_created = max(0, object_count_after - object_count_before)

        # If objects were created, get their details
        result = CommandResult(
            objects_created=objects_created,
        )

        if objects_created > 0:
            recent_objects = await self.get_recent_objects(objects_created)
            if recent_objects:
                result.object_ids = [obj.get("id", "") for obj in recent_objects[:objects_created]]
                result.object_types = [obj.get("type", "") for obj in recent_objects[:objects_created]]
                # Calculate combined bbox
                if recent_objects[0].get("bbox"):
                    bbox = recent_objects[0]["bbox"]
                    result.bbox = {"min": bbox.get("min"), "max": bbox.get("max")}

        if not success:
            result.error_message = result_message

        # 7. Determine actual success (command succeeded AND created objects if expected)
        # For now, we consider success if Rhino didn't error
        actual_success = success

        # Check for failure indicators in history
        if "Unknown command" in history_after and "Unknown command" not in history_before:
            actual_success = False
            result.error_message = "Unknown command or parameter"

        execution_time = int((time.time() - start_time) * 1000)

        # 8. Build observation
        observation = CommandObservation(
            id=CommandObservation.generate_id(command_name, timestamp),
            timestamp=timestamp,
            command=command_name,
            full_syntax=command_string,
            mode=mode,
            success=actual_success,
            dialogue=dialogue,
            preconditions=CommandPreconditions(clear_pending_first=clear_pending),
            result=result,
            intent=intent,
            raw_history_before=history_before[-2000:] if history_before else None,  # Limit size
            raw_history_after=history_after[-2000:] if history_after else None,
            execution_time_ms=execution_time,
        )

        # 9. Store observation if we have a store
        if self.store:
            self.store.store(observation)
            logger.info(f"Observation stored: {observation.id}")

        return observation

    def _extract_command_name(self, command_string: str) -> str:
        """Extract the command name from a command string."""
        parts = command_string.strip().split()
        if not parts:
            return "Unknown"

        first_part = parts[0]
        # Remove - prefix for scripted mode
        if first_part.startswith("_-"):
            return first_part[1:]  # Keep the underscore, remove dash
        return first_part

    async def experiment_with_command(
        self,
        command_name: str,
        variations: list[str],
        intent: Optional[str] = None
    ) -> list[CommandObservation]:
        """Try multiple variations of a command to learn syntax patterns.

        DEPRECATED: Use experiment_interactive for better dialogue capture.

        Args:
            command_name: The base command (e.g., "_Box")
            variations: List of full command strings to try
            intent: What we're trying to accomplish

        Returns:
            List of observations from each variation
        """
        observations = []

        for variation in variations:
            logger.info(f"Experimenting with: {variation}")

            # Execute and observe
            obs = await self.execute_and_observe(
                command_string=variation,
                intent=intent,
                clear_pending=True
            )
            observations.append(obs)

            # Log result
            if obs.success:
                logger.info(f"  SUCCESS: Created {obs.result.objects_created} objects")
            else:
                logger.info(f"  FAILED: {obs.result.error_message}")

        return observations

    async def experiment_interactive(
        self,
        command: str,
        input_variations: list[list[str]],
        intent: Optional[str] = None
    ) -> list[CommandObservation]:
        """Experiment with a command using interactive mode.

        This is the PREFERRED method for learning command syntax, as it
        captures the actual prompts from Rhino in real-time.

        Args:
            command: The command to experiment with (e.g., "_-Box")
            input_variations: List of input sequences to try, e.g.,
                [["0,0,0", "10,10,0", "5"], ["_Center", "5,5,0", "10,10,0", ""]]
            intent: What we're trying to accomplish

        Returns:
            List of observations from each input sequence
        """
        observations = []

        for inputs in input_variations:
            logger.info(f"Experimenting with {command}: inputs={inputs}")

            obs = await self.execute_interactive(
                command=command,
                inputs=inputs,
                intent=intent,
            )
            observations.append(obs)

            # Log result
            if obs.success:
                logger.info(f"  SUCCESS: Created {obs.result.objects_created} objects, {len(obs.dialogue)} dialogue steps")
                for i, step in enumerate(obs.dialogue):
                    logger.debug(f"    Step {i+1}: '{step.prompt[:50]}...' -> '{step.input_value}'")
            else:
                logger.info(f"  FAILED: {obs.result.error_message}")

        return observations

    async def explore_command_interactively(
        self,
        command: str,
        intent: Optional[str] = None,
    ) -> CommandObservation:
        """Explore a command interactively by reading prompts and responding.

        This method lets you explore a command without pre-defined inputs -
        it stops after each prompt so you can see what options are available.

        Args:
            command: The command to explore (e.g., "_-Box")
            intent: What we're trying to accomplish

        Returns:
            CommandObservation with whatever dialogue was captured
        """
        import time
        start_time = time.time()
        timestamp = datetime.utcnow().isoformat() + "Z"

        command_name = self._extract_command_name(command)
        dialogue: list[DialogueStep] = []

        try:
            # Cancel any pending command first
            await self.cancel_command_interactive()

            # Start the command
            result = await self.start_command_interactive(command)
            if "error" in result:
                logger.error(f"Failed to start command: {result['error']}")
                return CommandObservation(
                    id=CommandObservation.generate_id(command_name, timestamp),
                    timestamp=timestamp,
                    command=command_name,
                    full_syntax=command,
                    mode="interactive",
                    success=False,
                    dialogue=[],
                    preconditions=CommandPreconditions(clear_pending_first=True),
                    result=CommandResult(error_message=result["error"]),
                    intent=intent,
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )

            # Capture the first prompt
            prompt_text = result.get("prompt", "")
            options = result.get("options", [])
            default = result.get("default_value")

            logger.info(f"Command started. First prompt: {prompt_text}")
            logger.info(f"  Options: {options}")
            logger.info(f"  Default: {default}")

            if prompt_text and prompt_text != "Command":
                step = DialogueStep(
                    prompt=prompt_text,
                    prompt_type=self._classify_prompt_text(prompt_text),
                    options_available=options,
                    default_value=default,
                )
                dialogue.append(step)

            # Build and return observation (caller can continue with send_input_interactive)
            return CommandObservation(
                id=CommandObservation.generate_id(command_name, timestamp),
                timestamp=timestamp,
                command=command_name,
                full_syntax=command,
                mode="interactive",
                success=not result.get("is_complete", True),  # Not complete = still waiting
                dialogue=dialogue,
                preconditions=CommandPreconditions(clear_pending_first=True),
                result=CommandResult(objects_created=0),
                intent=intent,
                execution_time_ms=int((time.time() - start_time) * 1000),
            )

        except Exception as e:
            logger.error(f"Exploration failed: {e}")
            return CommandObservation(
                id=CommandObservation.generate_id(command_name, timestamp),
                timestamp=timestamp,
                command=command_name,
                full_syntax=command,
                mode="interactive",
                success=False,
                dialogue=dialogue,
                preconditions=CommandPreconditions(clear_pending_first=True),
                result=CommandResult(error_message=str(e)),
                intent=intent,
                execution_time_ms=int((time.time() - start_time) * 1000),
            )


# =============================================================================
# Default storage path
# =============================================================================

DEFAULT_OBSERVATION_STORE_PATH = resolve_writable_knowledge_path("commands")
