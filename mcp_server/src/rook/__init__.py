"""Rook MCP Server - Enables Claude to interact with Rhino 3D."""

import sys

# Prevent stale .pyc bytecode from masking source edits during development.
# Must be set before any downstream imports that may load the server.
sys.dont_write_bytecode = True


def main():
    from .__main__ import main as entry_main

    return entry_main()


def __getattr__(name: str):
    if name == "mcp":
        from .server import mcp

        return mcp
    raise AttributeError(name)

__all__ = ["mcp", "main"]
