Rook — AI agents for Rhino 3D & Grasshopper

Rook connects your AI assistant directly to Rhino 8 and Grasshopper for
AI-assisted modeling, parametric automation, and conversational design. It works
with any MCP-capable assistant (Claude Code, Codex, Cursor, Windsurf, and others).

What gets installed:
  - RookNative.rhp   C++ plugin (high-performance Rhino bridge)
  - Rook.rhp         C# companion (Grasshopper support)
  - MCP server       Python service with bundled CPython 3.11.9
  - Knowledge stores Component and command libraries
  - Curated skills for Codex (~/.codex/skills). Claude Code installs skills from
    the Rook marketplace plugin after setup.

Requirements:
  - Rhino 8 (must be installed before running this installer)
  - An MCP-capable AI assistant (Claude Code, Codex, ...)

Important:
  - Close Rhino, Rhino.Inside.Revit, and Revit before installing.
  - Run this installer as the same Windows user who runs Rhino/Revit.
    Rook registers Rhino plugins in that user's HKCU registry and APPDATA
    profile; an administrator installing for another user will not register
    the plugins for that user's Rhino session.

After installation:
  1. Open (or restart) Rhino 8.
  2. Connect your AI assistant to the Rook MCP server.
  3. Hand your assistant the post-install prompt placed in your Rook folder
     (ROOK_CLAUDE_POST_INSTALL.md or ROOK_CODEX_POST_INSTALL.md) - it verifies the
     connection, runs a quick smoke test, sets up skills, and reports.

--------------------------------------------------------------------------------

(c) 2026 Bringfire Games, LLC. Released under the MIT License.

Rook is open source: https://github.com/bringfire/Rook. This installer includes
runtime implementation files required for the local MCP server and related
Python-based components; bundled third-party components keep their own licenses.

Rook includes third-party open-source components, including FFmpeg, which are
provided under their own licenses and notices.

Rook is local-first and bring-your-own-key. See the Privacy Policy for details:
https://github.com/bringfire/rook-release/blob/main/PRIVACY.md
