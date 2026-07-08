STATUS: DONE

commits made
- `Extract LM7 planner authoring prompt support` (single task commit, amended to finalize the report)

files changed
- C:/UDEV/Rook/.superpowers/sdd/task-1-report.md
- C:/UDEV/Rook/scripts/lm7_planner_authoring_prompt_support.py
- C:/UDEV/Rook/scripts/lm7c_planner_authoring_probe.py
- C:/UDEV/Rook/mcp_server/tests/test_lm7c_planner_authoring_probe.py

tests run with exact command and result
- `.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_prompt_support_helper_matches_lm7c_sparse_artifacts mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_prompt_support_helper_matches_lm7c_shape_guidance_artifacts -q`
  - Result: FAIL as expected before extraction; `FileNotFoundError` for `C:\UDEV\Rook\scripts\lm7_planner_authoring_prompt_support.py`; `2 failed in 0.24s`
- `.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_prompt_support_helper_matches_lm7c_sparse_artifacts mcp_server\tests\test_lm7c_planner_authoring_probe.py::test_prompt_support_helper_matches_lm7c_shape_guidance_artifacts -q`
  - Result: PASS after extraction; `2 passed in 0.16s`
- `.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm7c_planner_authoring_probe.py -q`
  - Result: PASS; `59 passed in 0.58s`
- `py -3.10 -m py_compile scripts\lm7_planner_authoring_prompt_support.py scripts\lm7c_planner_authoring_probe.py mcp_server\tests\test_lm7c_planner_authoring_probe.py`
  - Result: PASS; exit 0

self-review notes
- Extracted only the pure prompt/menu/brief/parser/classifier support into the new helper and left LM7C scoring, provider execution, summary generation, CLI, and `_run_probe` in place.
- Preserved LM7C module-scope constants and underscore helper surface by importing helper exports under the existing LM7C names.
- Added the script-directory `sys.path` insertion in LM7C so the sibling helper imports cleanly when the probe is loaded by file path in tests.
- Did not modify LM7E, LM7E tests, `mcp_server/src`, or unrelated workspace changes.
