---
name: test
description: |
  Run tests by layer for this repo. Use when the user mentions: /test unit,
  /test integration, /test rhino, /test layer1, /test layer2, /test layer3,
  /test layer4, or /test all.
---

# Test Runner

Run the smallest test slice that answers the request.

## Modes

| Mode | Scope | Rhino required |
|------|-------|----------------|
| `unit` | `mcp_server/tests` plus non-Rhino root tests | No |
| `integration` | Layer 1 + Layer 2 integration suites | No |
| `layer1` | `tests/test_integration_layer1.py` | No |
| `layer2` | `tests/test_integration_layer2.py` | No |
| `layer3` | `tests/test_integration_layer3_rhino.py` | Yes |
| `layer4` | `tests/test_integration_layer4_e2e.py` | Yes |
| `rhino` | Pytest-based live Rhino suites | Yes |
| `all` | Unit + integration, then live Rhino layers if available | Mixed |

Default to `unit` if the user just says `/test`.

## Commands

Run from the repo root unless noted otherwise.

### `unit`

```powershell
Set-Location mcp_server
.venv\Scripts\python -m pytest `
  tests `
  ..\tests\test_command_consolidator.py `
  ..\tests\test_command_knowledge_store.py `
  ..\tests\test_end_to_end_learning.py `
  ..\tests\test_parse_command.py `
  ..\tests\test_session_tools.py `
  ..\tests\test_token_reduction.py `
  -m "not requires_rhino" -v
```

### `integration`

```powershell
Set-Location mcp_server
.venv\Scripts\python -m pytest `
  ..\tests\test_integration_layer1.py `
  ..\tests\test_integration_layer2.py `
  -v
```

### `layer1`

```powershell
Set-Location mcp_server
.venv\Scripts\python -m pytest ..\tests\test_integration_layer1.py -v
```

### `layer2`

```powershell
Set-Location mcp_server
.venv\Scripts\python -m pytest ..\tests\test_integration_layer2.py -v
```

### `layer3`

```powershell
Set-Location mcp_server
.venv\Scripts\python ..\tests\test_integration_layer3_rhino.py
```

### `layer4`

```powershell
Set-Location mcp_server
.venv\Scripts\python ..\tests\test_integration_layer4_e2e.py
```

### `rhino`

```powershell
Set-Location mcp_server
.venv\Scripts\python -m pytest `
  ..\tests\test_session_integration.py `
  ..\tests\test_intersection_integration.py `
  -m requires_rhino -v
```

Then run `layer3` and `layer4` if the user wants the full live stack, since those are script-style suites rather than pytest files.

### `all`

Run in this order:
1. `unit`
2. `integration`
3. If Rhino is reachable, `rhino`
4. If Rhino is reachable and the user wants full end-to-end coverage, `layer3` then `layer4`

## Preflight

For any live Rhino mode (`rhino`, `layer3`, `layer4`, or the live portion of `all`):

1. Call `rhino_ping` first.
2. If Rhino is unavailable, stop before live tests and report that only the non-Rhino layers can run.

## Reporting

- Report which mode ran.
- Report exact failures and whether the suite was blocked by missing Rhino or missing `.venv`.
- Do not claim `all` if live layers were skipped.
