---
name: test
description: |
  Run the Python tests for this repo. Use when the user mentions: /test unit,
  /test rhino, or /test all.
---

# Test Runner

Run the smallest test slice that answers the request.

## Modes

| Mode | Scope | Rhino required |
|------|-------|----------------|
| `unit` | `mcp_server/tests`, tests not marked `requires_rhino` | No |
| `rhino` | `mcp_server/tests`, tests marked `requires_rhino` | Yes |
| `all` | `unit`, then `rhino` if Rhino is reachable | Mixed |

Default to `unit` if the user just says `/test`.

## Commands

Run from the repo root.

### `unit`

```powershell
Set-Location mcp_server
.venv\Scripts\python -m pytest tests -m "not requires_rhino" -v
```

### `rhino`

```powershell
Set-Location mcp_server
.venv\Scripts\python -m pytest tests -m requires_rhino -v
```

### `all`

Run in this order:
1. `unit`
2. If Rhino is reachable, `rhino`

## Preflight

For any live Rhino mode (`rhino`, or the live portion of `all`):

1. Call `rhino_ping` first.
2. If Rhino is unavailable, stop before live tests and report that only the non-Rhino tests can run.

## Reporting

- Report which mode ran.
- Report exact failures and whether the suite was blocked by missing Rhino or missing `.venv`.
- Do not claim `all` if the live tests were skipped.
