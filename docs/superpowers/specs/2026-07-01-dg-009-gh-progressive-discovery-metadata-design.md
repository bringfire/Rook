# DG-009 GH Progressive Discovery Metadata Design

- **Status:** Approved for implementation.
- **Date:** 2026-07-01
- **Branch:** `codex/dg-009-gh-progressive-discovery-metadata`
- **Base:** `origin/main` at `a1a386f1bfb811f283afbd4fd50b729dc710d25a`
- **Issue:** DG-009 in `H:/AI EXPERIMENTS/Pearson/ANIMATION/.rook/director_planning/TOOLING_GAPS_AND_ISSUES.md`

## Problem

Codex agents using Rook's `lean` MCP profile may use Codex's outer `tool_search` to look for an exact hidden
GH tool such as `gh_update_script`, `gh_set_script_pins`, or `gh_status`. Those tools are intentionally not
advertised in `lean`, so direct outer discovery can return zero results even though the live Rook GH bridge is
healthy and Rook's internal progressive-disclosure gateway can resolve the tools.

The current implementation already proves the internal boundary: `rook_tools_search({"query":"gh_update_script"})`
returns the real `gh_update_script` record, and `rook_tools_read` exposes its schema. The missing piece is making
the advertised gateway discoverable when an agent searches for high-value hidden GH scripting/readiness names.

## Acceptance Boundary

The desired behavior is:

1. Codex outer `tool_search("gh_update_script")` should discover the Rook progressive-disclosure gateway, not
   necessarily the hidden `gh_update_script` tool definition.
2. `rook_tools_search({"query":"gh_update_script"})` should return the real GH record.
3. `rook_tools_read({"name":"gh_update_script"})` should expose the schema.
4. `rook_tools_call({"name":"gh_update_script", "arguments": ...})` should invoke through the existing policy path.

## Non-Goals

- Do not add hidden GH mutators such as `gh_update_script` or `gh_set_script_pins` to `PUBLIC_LEAN_TOOL_NAMES`.
- Do not modify, extend, or unify the LM2A `CapabilityRecord` / `CapabilityInventory` model.
- Do not create a second GH-specific gateway that duplicates `rook_tools_search`.
- Do not change readonly enforcement; `PUBLIC_READONLY_TOOL_NAMES` remains the authority.
- Do not touch native/managed GH bridge code for this metadata issue.

## Design

Use the existing progressive-disclosure gateway and enrich only its advertised metadata.

Update the `Tool(...)` descriptions for `rook_tools_search`, `rook_tools_read`, and `rook_tools_call` in
`mcp_server/src/rook/server.py` with compact exact-name aliases for the DG-009 GH surface:

- `gh_update_script`
- `gh_set_script_pins`
- `gh_status`
- `gh_create_csharp_script`
- `gh_snapshot`

The wording should make the gateway discoverable without bloating the lean surface or implying those hidden tools
are directly advertised. The metadata should describe the intended flow:

`tool_search` finds `rook_tools_search/read/call` -> `rook_tools_search` resolves the hidden Rook tool ->
`rook_tools_read` returns the schema -> `rook_tools_call` invokes the target through normal policy.

## Tests

Add focused Python tests that cover both layers Rook controls:

- Lean advertised metadata for the gateway contains the DG-009 exact aliases.
- Lean membership remains unchanged at 22 and does not include hidden GH mutators.
- `rook_tools_search` exact-name queries return the real GH records for all DG-009 names.
- `rook_tools_read` returns the schema for those records.

Extend `scripts/lm_surface_smoke.py` with a progressive-disclosure smoke mode or equivalent coverage so a deployed
runtime can prove the gateway exact-name metadata and internal GH resolution after startup.

## Rollout

This is a V1.1 metadata hardening patch for the Phase One progressive-disclosure architecture. It should be safe for
the LM campaign because it consumes the existing public-MCP facet as-is and does not change LM2A data structures,
profile enforcement, dispatch routing, native routes, or managed bridge ownership.
