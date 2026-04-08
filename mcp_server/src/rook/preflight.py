"""
Pre-dispatch validators for tool calls.

These run before a tool reaches Rhino, catching malformed input that would
otherwise silently succeed or trigger modal dialogs. Shared by both the MCP
path (server.py call_tool) and the agent path (tool_dispatcher.py).
"""

from typing import Any


def preflight_rhino_command(
    command: Any,
    knowledge_store: Any | None = None,
) -> dict[str, Any] | None:
    """Reject obviously malformed Rhino command strings before they hit RunScript.

    Returns an error dict if the command should be rejected, or None if it passes.
    The knowledge_store is optional — when absent, only the underscore check runs.
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
        return None

    parsed = knowledge_store.parse_command_string(command_text)
    if not isinstance(parsed, dict):
        return None

    cmd_name = parsed.get("command")
    syntax = parsed.get("syntax")
    if not isinstance(cmd_name, str) or not isinstance(syntax, str) or not syntax:
        return None

    cmd_knowledge = knowledge_store.get_command(cmd_name)
    if cmd_knowledge is None:
        return None

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
        return {
            "success": False,
            "data": (
                f"Command syntax incomplete for {cmd_name}. Missing required values for: "
                f"{', '.join(missing_required)}. Expected syntax: {syntax}. "
                "Use rhino_command_interactive_* if the command must prompt for input."
            ),
        }

    allowed_options: set[str] = set(cmd_knowledge.options.keys())
    for mode_data in cmd_knowledge.modes.values():
        mode_syntax = getattr(mode_data, "syntax", "")
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

    return None
