# Tool Surface Cleanup — Shared `call_tool` Parser + Formatter Contract Pin

> **Slice:** Issue #218 (the executable half). The documentation deliverable already
> shipped in #219 (docstring on `_format_tool_result` + the "Tool Result Surface" section
> in `docs/CURRENT_ARCHITECTURE.md`). This is the pre-P7 router-plane cleanup.

## 1. One sentence

Centralize parsing of the public MCP `call_tool()` wire shape into one blessed leaf module,
migrate the router-plane live harnesses (p3–p6) onto it, and pin `server._format_tool_result()`
with a contract test so the formatter and its inverse parser cannot silently drift.

## 2. Why this slice (and why small)

The P6 Slice 1 live smoke cost a ~13-run detour because the harness read a *correctly parsed*
success result under the wrong key — the internal `{success, data}` dispatcher envelope is
**not** the public wire text. On the wire, success is `json.dumps(data)` (the `data` only) and
failure is `"Error: " + (json.dumps(data) | str(data))`. #219 documented that contract. This
slice removes the **active** footgun where we tripped over it: one parser, the four harnesses
that share an ad-hoc `_text`/`_json` pair, and a test that pins the formatter. The existing
`_json` is also *lenient and conflated* — it strips `Error:` and parses success or failure into
one dict, returning `{}` on any failure, which hides errors. The strict success parser is the
key behavioral improvement.

## 3. Non-goals (hard boundaries)

- Do **not** move `_format_tool_result` out of `server.py`. `server.py` owns *rendering*; the
  new module owns *reading*. No formatter move in this slice.
- Do **not** migrate the ~52 ad-hoc-parsing test files (~262 sites). That is legacy debt, not
  active ambiguity; it migrates opportunistically or as a separate low-risk cleanup.
- Do **not** touch `p2_bridge_diagnosis_live_harness.py` — it is bridge/HTTP-level (imports
  `httpx`/`bridge`) and never calls `server.call_tool`, so it has nothing generic to migrate.
- Do **not** touch the `gh_*` harnesses — they do not share the generic `call_tool` text-parse
  pattern.
- **No public MCP behavior change.** `call_tool()` output is unchanged; agents in the wild may
  depend on the success text being `data` rather than the whole envelope.

## 4. The module — `mcp_server/src/rook/tool_result.py`

A **parser-only leaf**. It imports nothing from `server` (the `call_tool` dependency is
injected), so there is zero circular-import risk and the contract test is the only place the two
sides meet. It is the semantic inverse of `_format_tool_result`.

```python
def text_from_call_tool_result(result) -> str
def is_error_result(result) -> bool
def parse_call_tool_data(result) -> dict
def parse_call_tool_error(result) -> dict | str
async def call_tool_data(call_tool, name, arguments) -> dict
```

Semantics:

- **`text_from_call_tool_result(result) -> str`** — the single `result[0].text`, or `""` when
  the list is empty/falsy.
- **`is_error_result(result) -> bool`** — text-based **only**:
  `text_from_call_tool_result(result).startswith("Error: ")`. No JSON, no semantic inference —
  boring and trustworthy by construction.
- **`parse_call_tool_data(result) -> dict`** — **SUCCESS-only.** Raises `ValueError` if
  `is_error_result(result)` is true or the text is not JSON. Never returns `{}` silently. (This
  is the function the issue tentatively called `parse_call_tool_text`; renamed for clarity and
  to parallel `parse_call_tool_error` / `call_tool_data`. Docstring states "success-only".)
- **`parse_call_tool_error(result) -> dict | str`** — **FAILURE-only.** Raises `ValueError` if
  the result is **not** an error. Strips the leading `"Error: "`, returns the parsed dict when
  the remainder is JSON, otherwise the raw remaining string.
- **`call_tool_data(call_tool, name, arguments) -> dict`** — convenience:
  `parse_call_tool_data(await call_tool(name, arguments))`. `call_tool` is injected (callers pass
  `server.call_tool`). Strict — propagates `ValueError` on an unexpected error result.

Module docstring points to `docs/CURRENT_ARCHITECTURE.md` "Tool Result Surface" and notes it is
the inverse of `server._format_tool_result`.

## 5. Error-token-check rule (normative — not "implementer's discretion")

When migrating a harness site that inspects an error response:

- If it only needs to assert **"an error happened"** or preserve an existing substring smoke
  check → `text_from_call_tool_result(...)` with `in` / `startswith` is acceptable.
- If it **branches on structured error data** (reads a field of the error payload) → it
  **must** use `parse_call_tool_error(...)`.

This keeps the refactor consistent without forcing churn on simple substring smokes.

## 6. Refactor — p3 / p4 / p5 / p6

Each harness deletes its local `_text`/`_json` and imports from `rook.tool_result`. It is **not**
a blind swap — there are three site types:

- **Pure success reads** → `parse_call_tool_data` / `call_tool_data`. This collapses p3's
  `_object_count` envelope-hedge — currently
  `d.get("objectCount") or d.get("data", {}).get("objectCount")` (a scar from the very confusion
  #219 documented) — down to `parse_call_tool_data(...)["objectCount"]`.
- **Outcome branches** where success *or* failure is a valid result the harness inspects (e.g.
  p6's `rhino_workbench_launch`) → `if is_error_result(r): <fail path> else: parse_call_tool_data(r)`.
  This replaces the lenient `_json` that silently turned a launch error into `{}` / "not owned".
- **Error-token checks** → governed by §5.

`p2` is untouched (§3).

## 7. Testing — `mcp_server/tests/test_tool_result.py`

**Unit (the parsers):**

- `text_from_call_tool_result`: returns the payload; `""` for an empty list.
- `is_error_result`: true for `"Error: ..."`, false for success text.
- `parse_call_tool_data`: returns the data dict on success; raises `ValueError` on an error
  envelope; raises `ValueError` on non-JSON success text.
- `parse_call_tool_error`: returns the dict for an error-dict; returns the raw string for an
  error-string; raises `ValueError` on a success envelope.
- `call_tool_data`: with a fake async `call_tool`, returns the data on success and propagates
  `ValueError` on an error result.

**Contract (load-bearing — pins the formatter):** import `server._format_tool_result` and the
parsers; assert against rendered envelopes:

- success + dict data → text is bare `json.dumps(data)` → `parse_call_tool_data` returns `data`
  (roundtrip).
- failure + dict data → text starts with `"Error: "` → `parse_call_tool_error` returns `data`
  (roundtrip).
- failure + string data → text equals `"Error: " + s` → `parse_call_tool_error` returns `s`.
- `parse_call_tool_data` raises `ValueError` on a failure envelope; `parse_call_tool_error`
  raises on a success envelope.

The roundtrip properties mean editing `_format_tool_result` breaks this test unless the parser is
updated in lockstep — that is the anti-drift pin.

## 8. Files

- **Create:** `mcp_server/src/rook/tool_result.py`, `mcp_server/tests/test_tool_result.py`.
- **Modify:** `mcp_server/tools/p3_session_mutation_live_harness.py`,
  `mcp_server/tools/p4_workbench_lifecycle_live_harness.py`,
  `mcp_server/tools/p5_registry_reclaim_live_harness.py`,
  `mcp_server/tools/p6_artifact_perception_live_harness.py` (drop local `_text`/`_json`, import
  the module, apply §5 + §6).
- **Untouched:** `mcp_server/src/rook/server.py` (formatter stays), `p2_*`, the `gh_*` harnesses,
  the ~52 ad-hoc-parsing test files.

## 9. Scope note (carry into the PR + issue #218 body)

> "Establishes the blessed `tool_result` helper and migrates the router-plane live harnesses
> (p3–p6); broad test-suite migration (~52 files) is intentionally deferred to opportunistic /
> separate low-risk cleanup."

## 10. Verification

- **Non-live gate** (`pytest mcp_server/tests -m "not requires_rhino"`): `test_tool_result.py`
  passes; failed/errors otherwise **UNCHANGED** vs `main` (the module + its tests are purely
  additive). Baseline parity is the merge gate.
- **`py_compile`** each modified harness (mechanical-edit safety net).
- **Live re-verification (needs Rhino, gated checkpoint with the user):** re-run at least the
  `p6-artifact-perception` live smoke (the one we know in detail) — ideally p3/p4/p5 too — to
  confirm the harness refactor did not regress the live path. The unit + contract tests cover
  the module itself; the live re-run covers the harness migration.

## 11. Decision log

- **Parser-only leaf module**, not co-located with the formatter; no `server` import; `call_tool`
  injected. [user]
- **Strict success parser raises `ValueError`** — not a silent `{}`, and not `AssertionError`
  (which reads as test-only and is strippable under `python -O`). [user + author]
- **`is_error_result` is text-based only** — a thin predicate over the public surface. [user]
- **Error-token-check rule is normative (§5)**, not discretionary. [user]
- **Renamed** `parse_call_tool_text` → **`parse_call_tool_data`** for clarity and parallelism;
  docstring states "success-only". Supersedes the issue's tentative name. [user suggestion]
- **Surgical breadth** — p3–p6 only; p2 and the ~52 test files out. [user]
- **No formatter move** in this slice. [user]
