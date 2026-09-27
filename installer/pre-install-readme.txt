Rook — AI agents for Rhino 3D & Grasshopper

Rook connects your AI assistant directly to Rhino 8 and Grasshopper for
AI-assisted modeling, parametric automation, and conversational design. It works
with the Claude and ChatGPT desktop apps, and with other MCP-capable assistants.
No terminal, Git, or config files are needed.

What gets installed:
  - RookNative.rhp   C++ plugin (high-performance Rhino bridge)
  - Rook.rhp         C# companion (Grasshopper support)
  - MCP server       Python service with bundled CPython 3.11.9
  - Knowledge stores Component and command libraries
  - Connections to the Claude and ChatGPT (Codex) desktop apps, and Rook's
    skills for ChatGPT. Claude gets the skills from the Rook plugin after setup.

Requirements:
  - Rhino 8 (must be installed before running this installer)
  - The Claude or ChatGPT desktop app, installed and opened once BEFORE you
    run this installer. The installer only connects the apps it finds; if you
    add an app later, run this installer again.

Important:
  - Close Rhino, Rhino.Inside.Revit, and Revit before installing.
  - Run this installer as the same Windows user who runs Rhino/Revit.
    Rook registers Rhino plugins in that user's HKCU registry and APPDATA
    profile; an administrator installing for another user will not register
    the plugins for that user's Rhino session.

After installation:
  1. Start Rhino 8 from the Start menu.
  2. Fully quit your AI app and open it again (closing the window is not
     always enough; use Quit from its icon near the clock).
  3. Claude only: add Rook's skills in the Claude app. Open Customize >
     Plugins > Add > Add marketplace, enter bringfire/rook-release, select
     Sync (again if it says "Failed to add marketplace"), then add Rook.
  4. Paste the post-install prompt from your Rook folder into a new
     conversation (ROOK_CLAUDE_POST_INSTALL.md for Claude, or
     ROOK_CODEX_POST_INSTALL.md for ChatGPT). It checks the connection, runs
     a quick test, and reports.

Step-by-step guide:
https://bringfire.github.io/rook-release/start/install/

--------------------------------------------------------------------------------

(c) 2026 Bringfire Games, LLC. Released under the MIT License.

Rook is open source: https://github.com/bringfire/Rook. This installer includes
runtime implementation files required for the local MCP server and related
Python-based components; bundled third-party components keep their own licenses.

Rook includes third-party open-source components, including FFmpeg, which are
provided under their own licenses and notices.

Rook is local-first and bring-your-own-key. See the Privacy Policy for details:
https://github.com/bringfire/rook-release/blob/main/PRIVACY.md
