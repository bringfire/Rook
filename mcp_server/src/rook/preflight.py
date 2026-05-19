"""
Pre-dispatch validators for tool calls.

These run before a tool reaches Rhino, catching malformed input that would
otherwise silently succeed or trigger modal dialogs. Shared by both the MCP
path (server.py call_tool) and the agent path (tool_dispatcher.py).
"""

from typing import Any


RUNSCRIPT_REFUSAL_ERROR = "run_script_safety_refusal"


def _runscript_safety_refusal(
    reason: str,
    command: Any = None,
    mode: Any = None,
    **extra_data: Any,
) -> dict[str, Any]:
    data = {
        "error": RUNSCRIPT_REFUSAL_ERROR,
        "reason": reason,
        "command": command,
        "mode": mode,
        "verified": False,
        "recovery": "Use a typed Rook tool or a known-safe fully scripted command.",
    }
    data.update(extra_data)
    return {
        "success": False,
        "data": data,
    }


def _get_mapping_value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _safe_modes_from_metadata(metadata: Any) -> set[str]:
    modes = _get_mapping_value(metadata, "safe_non_interactive_modes", [])
    if isinstance(modes, str):
        return {modes}
    if isinstance(modes, (list, tuple, set)):
        return {mode for mode in modes if isinstance(mode, str)}
    return set()


def _is_safe_non_interactive(cmd_knowledge: Any, mode: Any) -> bool:
    if not isinstance(mode, str):
        return False

    preconditions = _get_mapping_value(cmd_knowledge, "preconditions", {})
    if _get_mapping_value(preconditions, "safe_non_interactive") is True:
        return True
    if mode in _safe_modes_from_metadata(preconditions):
        return True

    modes = _get_mapping_value(cmd_knowledge, "modes", {})
    mode_metadata = _get_mapping_value(modes, mode)
    if mode_metadata is None:
        return False
    if _get_mapping_value(mode_metadata, "safe_non_interactive") is True:
        return True
    return mode in _safe_modes_from_metadata(mode_metadata)


def preflight_rhino_command(
    command: Any,
    knowledge_store: Any | None = None,
) -> dict[str, Any] | None:
    """Reject obviously malformed Rhino command strings before they hit RunScript.

    Returns an error dict if the command should be rejected, or None if it passes.
    A command knowledge store is required so RunScript only executes commands
    that are known and explicitly marked safe for non-interactive use.
    """
    if not isinstance(command, str) or not command.strip():
        return {"success": False, "data": "Missing required parameter: command"}

    # Reject control characters before any parsing — mirrors the native check
    # in CommandHandler.cpp (c < 0x20).  Without this, .split() treats \n and
    # \r as whitespace and the later option parser rejects them with a
    # misleading "Unknown option(s)" message instead of the security error.
    if any(ord(c) < 0x20 for c in command):
        return {
            "success": False,
            "data": "Command contains invalid control characters",
        }

    command_text = command.strip()
    first_token = command_text.split()[0]

    # Locale-independent execution should always use underscore-prefixed commands.
    if not first_token.startswith("_"):
        return {
            "success": False,
            "data": (
                "Rhino command strings must start with '_' for locale-independent execution. "
                f"Use '_{first_token}' instead of '{first_token}'."
            ),
        }

    if knowledge_store is None:
        return _runscript_safety_refusal(
            "command_safety_unavailable",
            command=command_text,
        )

    parsed = knowledge_store.parse_command_string(command_text)
    if not isinstance(parsed, dict):
        return _runscript_safety_refusal(
            "unknown_command",
            command=first_token.lstrip("_"),
        )

    cmd_name = parsed.get("command")
    mode = parsed.get("mode")
    if not isinstance(cmd_name, str):
        return _runscript_safety_refusal(
            "unknown_command",
            command=first_token.lstrip("_"),
            mode=mode,
        )

    cmd_knowledge = knowledge_store.get_command(cmd_name)
    if cmd_knowledge is None:
        return _runscript_safety_refusal(
            "unknown_command",
            command=cmd_name,
            mode=mode,
        )

    syntax = parsed.get("syntax")
    if not isinstance(cmd_name, str) or not isinstance(syntax, str) or not syntax:
        return _runscript_safety_refusal(
            "unknown_command",
            command=cmd_name,
            mode=mode,
        )

    from .learning.command_knowledge_store import parse_syntax_template

    _, param_specs = parse_syntax_template(syntax)
    provided_params = parsed.get("parameters", {})
    if not isinstance(provided_params, dict):
        provided_params = {}

    missing_required = [
        param_name
        for param_name, is_optional in param_specs
        if not is_optional and param_name not in provided_params
    ]
    if missing_required:
        return _runscript_safety_refusal(
            "missing_required_command_values",
            command=cmd_name,
            mode=mode,
            missing_required=missing_required,
            expected_syntax=syntax,
        )

    options = _get_mapping_value(cmd_knowledge, "options", {})
    allowed_options: set[str] = set(options.keys()) if isinstance(options, dict) else set()
    modes = _get_mapping_value(cmd_knowledge, "modes", {})
    mode_values = modes.values() if isinstance(modes, dict) else []
    for mode_data in mode_values:
        mode_syntax = _get_mapping_value(mode_data, "syntax", "")
        for token in str(mode_syntax).split()[1:]:
            if token.startswith("_") and "," not in token:
                allowed_options.add(token)

    options_used = parsed.get("options_used", [])
    if isinstance(options_used, list):
        unknown_options = [
            opt for opt in options_used
            if isinstance(opt, str) and opt not in allowed_options
        ]
        if unknown_options:
            allowed_preview = ", ".join(sorted(allowed_options)[:8]) or "<none recorded>"
            return {
                "success": False,
                "data": (
                    f"Unknown option(s) for {cmd_name}: {', '.join(unknown_options)}. "
                    f"Known options: {allowed_preview}."
                ),
            }

    raw_values = parsed.get("raw_values", [])
    if isinstance(raw_values, list):
        unmatched_values = [value for value in raw_values if isinstance(value, str)]
        if unmatched_values:
            return _runscript_safety_refusal(
                "unmatched_command_tokens",
                command=cmd_name,
                mode=mode,
                raw_values=unmatched_values,
            )

    if not _is_safe_non_interactive(cmd_knowledge, mode):
        return _runscript_safety_refusal(
            "command_not_marked_safe_non_interactive",
            command=cmd_name,
            mode=mode,
        )

    return None
