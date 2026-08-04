"""Canonical MCP progressive-disclosure gateway tool contracts."""

from __future__ import annotations

from mcp.types import Tool


MCP_CAPABILITY_GATEWAY_NAMES = frozenset({
    "rook_tools_ls",
    "rook_tools_search",
    "rook_tools_read",
    "rook_tools_call",
})


def build_mcp_capability_gateway_tools() -> tuple[Tool, ...]:
    """Return fresh MCP Tool definitions for the canonical gateway."""
    return (
        Tool(
            name="rook_tools_ls",
            description=(
                "Browse the Rook tool catalog like a filesystem. Lists tool entries and child paths "
                "under a domain/group path (e.g. '/', '/rhino', '/gh', '/video'). Returns compact "
                "entries only (no input schemas) — use rook_tools_read for a tool's full schema. "
                "Pair with rook_tools_search to find tools, then rook_tools_call to invoke them."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Catalog path to list, e.g. '/' or '/rhino'. Default '/'.",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "How many path segments deep to expand. Default 1.",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="rook_tools_search",
            description=(
                "Search the Rook tool catalog by keyword; returns matching tools with a one-line "
                "summary each. Covers the full tool surface — geometry, Grasshopper, native "
                "road intersections, vision, BIM, scene, video, knowledge. Use this to discover a tool, then "
                "rook_tools_read for its schema and rook_tools_call to invoke it. "
                "Exact hidden GH aliases resolve through this gateway, including "
                "gh_update_script, gh_set_script_pins, gh_status, gh_create_csharp_script, "
                "and gh_snapshot."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords to search for, e.g. 'camera preview' or 'boolean union'.",
                    },
                    "domain": {
                        "type": "string",
                        "description": "Optional domain filter, e.g. 'rhino', 'gh', 'video', 'bim'.",
                    },
                    "readonly_safe": {
                        "type": "boolean",
                        "description": "If true, only return read-only-safe tools.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return. Default 10.",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="rook_tools_read",
            description=(
                "Read one Rook tool's full record: description, domain/groups, and input JSON schema. "
                "Call this after rook_tools_search to learn a tool's arguments before rook_tools_call. "
                "Use this after searching exact hidden GH names such as gh_update_script, "
                "gh_set_script_pins, gh_status, gh_create_csharp_script, and gh_snapshot."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Exact tool name, e.g. 'rhino_video_models'.",
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="rook_tools_call",
            description=(
                "Invoke any dispatchable Rook tool by name with its arguments, through the normal "
                "policy path (the readonly profile wall still applies to the target). Use "
                "rook_tools_read first to get the target's input schema. "
                "For hidden GH tools discovered by name, this invokes targets such as "
                "gh_update_script, gh_set_script_pins, gh_status, gh_create_csharp_script, "
                "and gh_snapshot through the normal policy path."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Exact tool name to invoke.",
                    },
                    "arguments": {
                        "type": "object",
                        "description": "Arguments object matching the target tool's input schema.",
                    },
                },
                "required": ["name"],
            },
        ),
    )
