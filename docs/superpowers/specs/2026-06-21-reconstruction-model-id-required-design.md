# D4 — `rhino_2d_to_3d_submit` `model_id` contract honesty

**Date:** 2026-06-21
**Type:** Contract-honesty fix (behavior-neutral; MCP schema ↔ parser alignment)
**Branch:** `codex/reconstruction-model-id-required` (off `origin/main` `0ec4bb30`)

## Problem

The MCP `rhino_2d_to_3d_submit` tool schema marks `model_id` **optional** and its
description promises *"default Hunyuan rapid when omitted by managed contract"*
(`mcp_server/src/rook/server.py:12685`, `required: ["source_artifact_id"]`). But
the C# parser **hard-rejects** a missing `model_id`
(`ReconstructionSubmitRequestParser.cs:57-59` → `"model_id is required."`), and
no default-selection logic exists anywhere — the catalog only offers exact-match
`Find()`. So the schema advertises a default that was never implemented; an agent
following the schema and omitting `model_id` gets a hard `invalid_request`.

This surfaced during the 2026-06-21 textureless-mesh investigation (defect D4 of
that report). The C# parser is the correct, enforced source of truth.

## Decision

Align the **advertised** contract to the **enforced** one: make `model_id`
required in the MCP schema and delete the false default promise. **No implicit
default** is added — the model catalog (`rhino_2d_to_3d_models`) stays load-bearing
and the caller selects a model explicitly. Behavior-neutral: the parser already
required `model_id`, so no request that succeeds today changes, and no request
that fails today starts succeeding.

## Changes (MCP layer only — 2 files)

1. `mcp_server/src/rook/server.py` — the `rhino_2d_to_3d_submit` tool:
   - Add `"model_id"` to `required` → `["source_artifact_id", "model_id"]`.
   - Replace the `model_id` description with a short, drift-resistant line:
     > `Full fal model id returned by rhino_2d_to_3d_models. Required; no implicit default.`

2. `mcp_server/tests/test_reconstruction_mcp_tools.py` — the submit-schema test
   (currently `test_reconstruction_submit_requires_source_artifact_id_only_for_identity`,
   asserting `required == {"source_artifact_id"}`):
   - Update the required-set assertion to `{"source_artifact_id", "model_id"}`.
   - Add an assertion that the `model_id` description no longer contains
     `"default"` (case-insensitive) — guards against the default promise drifting
     back in.
   - Rename the test to reflect the contract (e.g.
     `test_reconstruction_submit_requires_source_artifact_id_and_model_id`); keep
     its existing path-rejection assertions (still valid — artifact-only contract).

## Out of scope (do not touch)

- The C# parser / `ReconstructionSubmitRequestParser.cs` — already correct; it is
  the source of truth we are aligning to. No C# change.
- Any default / fallback model-selection logic — deliberately **not** added.
- The original `docs/superpowers/specs|plans/2026-06-19-reconstruction-2d-to-3d-*.md`
  — frozen historical records; leave the "default path" wording there.
- Defects D1 (options semantics + guard), D2 (degraded-result warning), D3
  (registry truthfulness) — their own design slice later.

## Verification

- `python -m pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q` → green
  (17 tests), including the updated required-set + no-`default`-in-description
  assertions.
- No C# touched → no C# suite needed.
- Spot-check: schema `required` includes `model_id`; description matches the new
  one-liner.
