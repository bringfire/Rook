status: DONE

commits:
- `3ebbbdf0` - `Add LM7D shape guidance prompt profile`

files_changed:
- `scripts/lm7c_planner_authoring_probe.py`
- `mcp_server/tests/test_lm7c_planner_authoring_probe.py`

tests_run:
- `.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_prompt_contains_rules_but_no_full_request_exemplar mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_shape_guidance_prompt_includes_isolated_shape_snippets_only mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_prompt_version_follows_prompt_profile -q` -> passed (`3 passed in 0.19s`)
- `.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm7c_planner_authoring_probe.py -k "prompt or brief or template_menu" -q` -> passed (`8 passed, 43 deselected in 0.13s`)
- `.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm7c_planner_authoring_probe.py -q` -> passed (`51 passed in 0.50s`)

self_review_notes:
- Added a profile-dispatching `_planner_authoring_prompt(prompt_profile=...)` that keeps sparse behavior intact and renders a separate `shape_guidance_v2` prompt.
- The new shape-guidance prompt uses isolated `json.dumps(..., indent=2, sort_keys=True)` fragments for the routing delta and canonical unresolved-intent snippets, with no full solved request object.
- Updated tests to pin sparse compatibility explicitly, cover the shape-guidance prompt text, verify prompt-version selection, and keep artifact marker checks profile-aware.
- I did not thread prompt-profile metadata into row/manifest generation or marker scanning; that remains for later LM7D tasks.
