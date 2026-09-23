# OpenRouter Live Smoke Checklist

Three tiers of live coverage for the OpenRouter provider integration. All tests skip by
default — no network calls, no spend in CI.

---

## PowerShell setup

```powershell
cd <repo>/.worktrees/codex-openrouter/mcp_server
$env:OPENROUTER_API_KEY="sk-or-..."
```

---

## Tier 0 — Free (catalog fetch, no LLM calls)

Gate: `OPENROUTER_LIVE_SMOKE=1`

Proves `/api/v1/models` fetches, populates cache, resolves a known model to its
metadata, and confirms `tools` appears in `supported_parameters`. Zero spend.

```powershell
Remove-Item Env:OPENROUTER_LIVE_LLM_SMOKE -ErrorAction SilentlyContinue  # ensure no paid tests run
$env:OPENROUTER_LIVE_SMOKE="1"
python -m pytest tests/test_openrouter_live_smoke.py -v
```

Expected: `test_live_refresh_populates_cache` PASSED; the two routing tests SKIPPED.
(The `Remove-Item` line clears any leftover paid gate from a prior run in the same
session, so this Tier 0 command never spends.)

---

## Tier 1 — Paid (LLM routing, real spend)

Gate: `OPENROUTER_LIVE_LLM_SMOKE=1`

Proves that:
- `litellm.completion(model="openrouter/...")` authenticates with `OPENROUTER_API_KEY`
  and returns a non-empty response (no bogus `api_base` attached by the prefix fix).
- `configure_dspy(model="openrouter/...")` resolves `OPENROUTER_API_KEY` without
  demanding `ANTHROPIC_API_KEY`, and a direct LM call returns a non-empty response.

Cost: sub-cent per run at `max_tokens=5`. Default model is `openrouter/openai/gpt-4o-mini`.
Override with `OPENROUTER_SMOKE_MODEL` to use a different (e.g. cheaper) model.

```powershell
Remove-Item Env:OPENROUTER_LIVE_SMOKE -ErrorAction SilentlyContinue  # isolate the paid run
$env:OPENROUTER_LIVE_LLM_SMOKE="1"
$env:OPENROUTER_SMOKE_MODEL="openrouter/openai/gpt-4o-mini"
python -m pytest tests/test_openrouter_live_smoke.py -v
```

Expected: `test_live_openrouter_routes_via_litellm` and
`test_live_openrouter_routes_via_dspy` PASSED; catalog test SKIPPED (unless you also
set `OPENROUTER_LIVE_SMOKE=1`).

To run all three tiers at once:

```powershell
$env:OPENROUTER_LIVE_SMOKE="1"; $env:OPENROUTER_LIVE_LLM_SMOKE="1"; $env:OPENROUTER_SMOKE_MODEL="openrouter/openai/gpt-4o-mini"; python -m pytest tests/test_openrouter_live_smoke.py -v
```

---

## Tier 2 — Deploy integration (manual, after deploy + `/mcp` reconnect)

Run after deploying the `feature/codex-openrouter` branch, restarting Rhino, and
reconnecting `/mcp`. Record results as a comment on the PR.

- [ ] MCP `openrouter_refresh_catalog` via the running MCP server returns `models_fetched > 0`
- [ ] Profile FULL (default): `openrouter_refresh_catalog` present in `list_tools()` output
- [ ] Profile READONLY (`ROOK_MCP_TOOL_PROFILE=readonly`): `openrouter_refresh_catalog`
  hidden from `list_tools()` AND a direct call returns `tool_profile_blocked`
- [ ] Profile LEAN (`ROOK_MCP_TOOL_PROFILE=lean`): `openrouter_refresh_catalog` present
  AND callable without error
- [ ] RookChat: a role/profile configured to `openrouter/openai/gpt-4o-mini` completes
  one chat turn; health endpoint reports the openrouter model as configured
- [ ] Chirp: a Chirp component with `model="openrouter/openai/gpt-4o-mini"` solves and
  returns non-empty output on the Grasshopper canvas

Note results on the PR before merging.
