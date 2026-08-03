You're helping me finish setting up Rook (the Rhino + Grasshopper plugin) right
after installing it. Run these checks in order, then clean up and report.

1. MCP connection — list your MCP servers or inspect your available MCP tools. Confirm
   "rook" is present with the lean catalog. Confirm hidden admitted tools can be
   progressively discovered with rook_tools_search, inspected with rook_tools_read,
   and invoked with rook_tools_call. If missing, tell me (the installer registers it;
   I may need to restart you).
2. Rhino — make sure Rhino 8 is running, then call rhino_ping; expect "pong". If it
   fails, remind me to start Rhino and that the RookNative plugin must be loaded
   (I can run ShowRookChat in Rhino to check).
3. Geometry round-trip — create a red sphere at the origin, radius 5; then list the
   document objects to confirm it exists.
4. Grasshopper (only if GH is open) — take a canvas snapshot to confirm GH control;
   skip if GH isn't open.
5. Skills — confirm the curated Rook skills are installed (under ~/.codex/skills)
   and that AGENTS.md guidance is present. The Grasshopper workflow skills are exactly
   design-grasshopper, plan-grasshopper, and execute-grasshopper. Route a clear bounded
   build directly to execute, an ambiguous brief to read-only design, and large or
   high-risk work through the optional read-only plan stage. Other curated skills include
   chirp, chirp-cascade, capture-convention, clean-layers, project-setup, and
   twisted-column. If any are missing, tell me to re-run the Rook installer with Codex
   support.
6. Clean up — delete the test sphere you created (and any test layer) so my document
   is left exactly as it was.
7. Report — a short PASS/FAIL for each step; for any FAIL, the most likely cause and
   fix.
