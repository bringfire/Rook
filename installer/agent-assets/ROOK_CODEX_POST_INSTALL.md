You're helping me finish setting up Rook (the Rhino + Grasshopper plugin) right after installing it. Run these checks in order, then clean up and report. Use only the Rook tools; never use any screen-control, computer-use or Windows-control tool, and never ask me to use a terminal. Don't mark a step PASS without showing me the tool output.

1. Connection: call rhino_ping and expect "pong". If there are no Rook tools at all, tell me to quit the ChatGPT app completely and reopen it; if that doesn't help, I should run the Rook installer again with the Codex component ticked. If Rhino isn't running, ask me to start Rhino 8 from the Start menu; don't launch it yourself. If Rook didn't load in Rhino, I can type ShowRookChat in Rhino to check. If the call hangs, Rhino is showing a dialog: tell me to switch to Rhino and close it.
2. Rhino sessions: call rhino_sessions and confirm exactly one Rhino window is available.
3. Before touching anything: call rhino_document and tell me the units and object count. Warn me if the model already has work in it, and wait for my go-ahead if it does.
4. Round trip: create a red sphere at the origin with radius 5 (document units), then list the objects to confirm it exists. Note the new object's ID.
5. Grasshopper: call gh_status. If Grasshopper isn't open, ask me to open it and try again instead of marking this FAILED. Once it's available, report its version and take a canvas snapshot with gh_snapshot.
6. Skills: list the Rook skills you have. They come from your session rather than a tool call, so mark this step PASS when all nine are listed. I expect nine: capture-convention, chirp, chirp-cascade, clean-layers, design-grasshopper, execute-grasshopper, plan-grasshopper, project-setup, twisted-column. The Rook installer puts them in ~/.codex/skills. Don't try to install anything. If they're missing, tell me to run the Rook installer again with the Codex component ticked.
7. Clean up: delete only the sphere you created, by its ID, and confirm the object count is back to the number from step 3.
8. Report: a short PASS/FAIL for each step, and for any FAIL, the most likely cause and the fix in plain words.

About tools and approvals: you see a short list of Rook's tools and reach the rest through rook_tools_search, rook_tools_read and rook_tools_call; in this check, rhino_document, gh_status and the create and delete tools go through the gateway. With "Ask for approval", ChatGPT asks before each tool. It's safe for me to approve tools that only read, such as rhino_ping, permanently. For anything that creates, changes or deletes, and for rook_tools_call (which can run any Rook tool), I should approve once at a time.

Full guide: https://bringfire.github.io/rook-release/start/setup-verify/
