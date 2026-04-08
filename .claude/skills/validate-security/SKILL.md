---
name: validate-security
description: |
  Run interactive security validation against live Rhino. Exercises all
  Phase 1+2 hardening fixes using MCP tools. Use when: /validate-security,
  "test security fixes", "verify security hardening", "run security checks".
---

# Security Validation Protocol

Run each section in order using MCP tools. Track every check as PASS or
FAIL. Do NOT skip checks. Do NOT stop on first failure — run all checks
and report the full picture.

## Prerequisites

1. Call `rhino_ping` — must return pong. If ping fails, stop.
2. Read the discovery file to get the native server port (needed for the
   manual CORS check in Phase 2A). Use the bridge or check
   `%TEMP%/rook/instance-*-native.json` directly.
3. Call `rhino_document` to check document state. If the active document
   has never been saved (no path), create a temp file first:
   call `rhino_document_ops` action="save" with
   `path="%TEMP%/rook_security_test.3dm"`. This establishes a saved-file
   baseline required for the empty-path fallback test in Phase 1C.

## Phase 1A: /command control-character rejection

Use `rhino_command` for each test.

**Rejection tests — expect error containing "control characters":**

| # | Command string | Notes |
|---|---------------|-------|
| 1A.1 | `_Circle 0,0,0 10\n_Delete _All` | Newline injection |
| 1A.2 | `_Circle 0,0,0 10\r_Delete` | Carriage return |
| 1A.3 | `_Circle\t0,0,0 10` | Tab |

**Acceptance tests — expect success or non-validation error:**

| # | Command string | Notes |
|---|---------------|-------|
| 1A.4 | `_SelNone` | Normal command |
| 1A.5 | `_-SetUserText "key" "value"` | Quotes are legitimate |

**Verdict:** error message must contain "control characters" for 1A.1-3.
1A.4-5 must NOT contain "control characters".

## Phase 1C: Path validation on file endpoints

### Dangerous paths — must be rejected on every endpoint

| ID | Path | Rejection reason |
|----|------|-----------------|
| P1 | `..\..\..\..\windows\system32\config\SAM` | Traversal |
| P2 | `C:\Users\..\Admin\secret.3dm` | Mid-path traversal |
| P3 | `C:..\temp\file.3dm` | Drive-relative traversal |
| P4 | `\\attacker\share\file.3dm` | UNC backslash |
| P5 | `//evil.com/share/file.3dm` | UNC forward-slash |
| P6 | `\\?\C:\file.3dm` | Device namespace |

**Endpoints to test each path against (all 7 hardened endpoints):**

| Endpoint | Tool | Call pattern |
|----------|------|-------------|
| `/document/open` | `rhino_document_ops` action="open" | `{"path": "<P>"}` |
| `/document/save` | `rhino_document_ops` action="save" | `{"path": "<P>"}` |
| `/import` | `rhino_import` | `{"path": "<P>"}` |
| `/export` | `rhino_export` | `{"path": "<P>"}` |
| `/block/link` | `rhino_block_link` | `{"path": "<P>"}` |
| `/game-export/export` | `rhino_export_with_manifest` | `{"path": "<P>"}` |
| `/game-export/prepare` | `rhino_prepare_for_game_export` | `{"path": "<P>"}` |

**Verdict for each:** error must contain one of:
- "Path traversal (..) is not permitted"
- "UNC and device namespace paths are not permitted"
- "File path contains control characters"
- "File path contains quote characters"

### Safe paths — must NOT be rejected by validation

| ID | Path | Notes |
|----|------|-------|
| S1 | `C:\Users\<user>\Documents\test.3dm` | Standard absolute |
| S2 | `C:\Users\<user>\Desktop\My Project\output.3dm` | Spaces in path |

Test S1 and S2 against `/document/save` and `/export`. They may fail for
"File not found" or other runtime reasons — that is fine. The error must
NOT be one of the validation rejection messages above.

### Edge case: /document/save with empty path

**Precondition:** the active document must have an existing save path
(established in Prerequisites step 3).

Call `rhino_document_ops` action="save" with no path argument. Must NOT
return "File path is empty" — it should fall back to the document's
existing save path. If the document has no path (precondition not met),
record SKIP with a note, not FAIL.

## Phase 2A: CORS headers removed

This cannot be fully tested via MCP tools (they use Python httpx, not a
browser). Perform a partial check and note the manual step:

**Automated check:** Call `rhino_ping` — if it succeeds, the non-browser
path (Python httpx) still works without CORS headers. Record PASS.

**Manual check (instruct user):** Ask the user to open a browser console
on any page and run the following, substituting the port from
Prerequisites step 2:

```javascript
fetch('http://127.0.0.1:PORT/ping')
  .then(r => r.json()).then(console.log)
  .catch(e => console.log('BLOCKED:', e.message))
```

Expected: `BLOCKED: ...` (CORS or network error). If the user confirms
this, record PASS. If they see `{result: "pong"}`, record FAIL — CORS
headers are still present.

## Functional smoke tests — Rhino

| # | Action | Tool | Expected | Cleanup |
|---|--------|------|----------|---------|
| R.1 | Create a box | `rhino_create` type=box, origin=[0,0,0], width=10, depth=10, height=5 | Returns object ID | Delete after |
| R.2 | List objects | `rhino_objects` | Returns list including the box | — |
| R.3 | Delete the box | `rhino_delete` with box ID from R.1 | Success | — |
| R.4 | Run a normal command | `rhino_command` `_SelNone` | Success | — |

## Functional smoke tests — Grasshopper

**Note:** GH smoke tests verify that Grasshopper operations still work
after hardening but are more brittle than the Rhino-side checks (intent
routing, solver timing). GH failures should be reported separately and
do NOT block the Phase 1A/1C/2A security verdict.

| # | Action | Tool | Expected | Cleanup |
|---|--------|------|----------|---------|
| G.1 | Check GH status | `gh_status` | Returns GH version and canvas info | — |
| G.2 | Search library | `gh_library` search="sphere" | Returns component list | — |
| G.3 | Read canvas | `gh_snapshot` | Returns canvas state | — |
| G.4 | Create a slider | `gh_execute_intent` intent="create a number slider from 0 to 10" | Creates component, returns ID | Delete after |
| G.5 | Delete the slider | `gh_edit` with delete action using ID from G.4 | Removed from canvas | — |

## Cleanup

After all tests:
1. Delete any geometry created during smoke tests (box from R.1)
2. Delete any GH components created during smoke tests (slider from G.4)
3. If a temp file was written during prerequisites or acceptance tests,
   note path for manual cleanup (e.g., `%TEMP%/rook_security_test.3dm`)
4. Run `_SelNone` to clear selection state

## Summary Report

Output two verdict sections:

**Security verdict (Phase 1A + 1C + 2A):**

```
| Phase | Checks | Passed | Failed |
|-------|--------|--------|--------|
| 1A    | 5      | ?      | ?      |
| 1C    | ~47    | ?      | ?      |
| 2A    | 1-2    | ?      | ?      |
```

- **PASS — safe to merge.** All security checks passed.
- **FAIL — do not merge.** Security checks failed; list them.

**Functional verdict (Rhino + GH smoke):**

```
| Suite | Checks | Passed | Failed |
|-------|--------|--------|--------|
| Rhino | 4      | ?      | ?      |
| GH    | 5      | ?      | ?      |
```

- **PASS** — normal operations work.
- **PARTIAL** — GH flaky but Rhino fine (does not block merge).
- **FAIL** — Rhino operations broken (blocks merge).