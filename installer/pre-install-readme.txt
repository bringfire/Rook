Welcome to Rook — AI Bridge for Rhino 3D & Grasshopper

Rook connects Claude (Anthropic's AI) directly to Rhino 8, enabling
AI-assisted 3D modeling, Grasshopper automation, and conversational design.

What gets installed:
  - RookNative.rhp   C++ plugin (high-performance Rhino bridge)
  - Rook.rhp          C# companion (Grasshopper support)
  - MCP Server        Python service for Claude Code / Claude Desktop
  - Knowledge stores  Component and command libraries

Requirements:
  - Rhino 8 (must be installed before running this installer)
  - Python 3.10+ (required for the MCP server component)
  - Claude Code or Claude Desktop (install from claude.ai)

Important:
  - Close Rhino, Rhino.Inside.Revit, and Revit before installing.
  - Run this installer as the same Windows user who runs Rhino/Revit.
    Rook registers Rhino plugins in that user's HKCU registry and APPDATA
    profile; an administrator installing for another user will not register
    the plugins for that user's Rhino session.

After installation:
  1. Open (or restart) Rhino 8
  2. In Claude Code, type: rhino_ping
  3. You're connected!
