# RookVisionDirector Preview Loop Design

> **PARTIALLY SUPERSEDED — Director MCP retirement (2026-07-13):** The general
> non-Director architecture and dated evidence in this document remain available.
> All `rhino_director_*`, `/director`, VisionDirector, and Director-domain examples,
> allowlist entries, count assumptions, acceptance criteria, and positive dispatch
> tests are superseded as of 2026-07-13. Replace those examples with
> non-Director fixtures when maintaining or replaying this work. This document must
> not be used to restore a Director MCP tool. See the
> [Director MCP Surface Retirement Design][director-mcp-retirement].

[director-mcp-retirement]: 2026-07-13-director-mcp-surface-retirement-design.md

Date: 2026-06-25
Status: ready for user review

## Purpose

PR4 added `rhino_director_compile_motion`, which compiles a high-level
object-motion authoring spec into replay-ready `{track, provenance}`. PR2/PR3
already provide native live replay through `rhino_director_replay`.

PR5 adds the smallest useful agent workflow layer above those primitives:
compile an authored motion spec, replay the compiled track, return a compact
preview outcome, and expose deterministic hooks for the next edit. It does not
add motion semantics, persistence, camera shot vocabulary, native replay
features, or async job state.

## Scope

Add a Python-only orchestration module and one MCP tool:

- `mcp_server/src/rook/director_preview.py`
- `rhino_director_preview_motion`

The orchestration composes the existing compiler and replay helpers:

```text
authoring spec + preview controls
  -> director_compiler.compile_motion(authoring spec)
  -> director.run_replay(track + preview controls)
  -> compact preview outcome
```

Native C++, managed C#, persistent artifacts, capture/video assembly, and new
Director semantics are out of scope.

## Input Contract

`rhino_director_preview_motion` accepts the PR4 compiler authoring spec plus an
optional nested `preview` block:

```json
{
  "timeline": {"fps": 24, "frame_count": 48},
  "groups": {"parts": ["11111111-1111-1111-1111-111111111111"]},
  "motion": [
    {
      "target": "parts",
      "keyframes": [{"t": 1.0, "translate": [0, 0, 10]}]
    }
  ],
  "resolution": {"width": 1920, "height": 1080},
  "default_easing": "linear",
  "preview": {
    "replay_session_id": "optional-id",
    "restore_on_finish": true,
    "fps": 24,
    "loop": false,
    "include_track": false
  }
}
```

Rules:

- `preview` is removed before calling `compile_motion`.
- The input dictionary is not mutated in place.
- `preview.restore_on_finish` defaults to `true`.
- `preview.include_track` defaults to `false`.
- `preview.fps` is optional. If omitted, replay uses `track.fps`.
- `preview.replay_session_id` is optional and passes through to replay.
- `preview.loop: true` is rejected before compile or replay with
  `unsupported_preview_option` and `option: "loop"`.
- Preview shallow-validates the wrapper controls before compile or replay:
  `include_track` must be boolean if present; `restore_on_finish` must be
  boolean if present; `fps` must be a positive number if present;
  `replay_session_id` must be a string if present. Replay remains authoritative
  for exact session-id character and length rules.

Replay options remain execution controls, not authored animation semantics. The
nested block keeps the PR4 compiler contract clean and lets PR6 persist the
authoring spec separately from preview/run state.

## Output Contract

Default output is compact and omits the full baked track:

```json
{
  "state": "completed",
  "compile": {
    "provenance": {},
    "track_summary": {
      "frame_count": 48,
      "fps": 24,
      "duration_ms": 2000.0,
      "animated_object_ids": ["11111111-1111-1111-1111-111111111111"],
      "camera_frame_count": 48,
      "object_frame_count": 48
    }
  },
  "replay": {
    "status": "completed",
    "frames_played": 48,
    "restored": true,
    "replay_session_id": "optional-id"
  },
  "next_edit_hooks": {
    "motion_targets": ["parts"],
    "animated_object_ids": ["11111111-1111-1111-1111-111111111111"],
    "timeline": {"fps": 24, "frame_count": 48, "duration_ms": 2000.0},
    "preview_controls": ["restore_on_finish", "fps", "replay_session_id"]
  }
}
```

If `preview.include_track` is `true`, add the full compiled track at
`compile.track` beside `compile.provenance` and `compile.track_summary`.

The track is opt-in because replay tracks grow as objects times frames times
nested 4x4 matrices. Normal preview/iterate loops need outcome, provenance, and
summary rather than the full payload.

## State And Error Mapping

The top-level `state` is one of:

- `completed`
- `compile_failed`
- `replay_failed`
- `cancelled`

Preview validation failure:

- `preview.loop: true` returns `state: "compile_failed"` with
  `compile.error = {"code": "unsupported_preview_option", "option": "loop", "message": "preview.loop is not supported"}`.
- Invalid preview-control shape returns `state: "compile_failed"` with
  `compile.error.code: "invalid_preview"` before compile or replay.
- No compile or replay is attempted for unsupported or invalid preview controls.

Compile failure:

- Catch `director_compiler.DirectorCompileError`.
- Return `state: "compile_failed"`.
- Include `compile.error = exc.to_data()`.
- Do not call replay.

Replay failure:

- Exceptions from `director.run_replay` return `state: "replay_failed"` with
  `replay.error`.
- A returned replay payload with `status: "cancelled"` returns
  `state: "cancelled"` and includes the replay payload.
- A returned replay payload with `status: "completed"` returns
  `state: "completed"` and includes the replay payload.
- A returned replay payload with any other or missing status returns
  `state: "replay_failed"` with the raw payload included for diagnosis.

Replay failures still include compile provenance and `track_summary` so the
agent can tell whether the issue is source drift/runtime replay or compilation.

## Track Summary

`track_summary` is derived from the compiled `track` and compile provenance:

- `frame_count`: `track.frame_count`
- `fps`: `track.fps`
- `duration_ms`: prefer `provenance.duration_ms`; otherwise derive from
  `frame_count * (1000 / fps)` when possible
- `animated_object_ids`: `track.animated_object_ids`
- `camera_frame_count`: `len(track.camera_frames)`
- `object_frame_count`: `len(track.object_frames)`

The summary is deterministic and contains no LLM prose.

## Next Edit Hooks

`next_edit_hooks` is small deterministic metadata for agents. It is not a
critique engine and does not invent suggested edits.

Fields:

- `motion_targets`: the authored `motion[].target` values, preserving order.
- `animated_object_ids`: copied from `track_summary`.
- `timeline`: compact `fps`, `frame_count`, and `duration_ms`.
- `preview_controls`: supported execution controls:
  `restore_on_finish`, `fps`, `replay_session_id`.

No natural-language critique, visual analysis, persistence reference, or
revision history is added in PR5.

## MCP Tool

Add `rhino_director_preview_motion` near the existing Director compile/replay
tools in `server.py`.

Schema requirements:

- top-level `timeline` and `motion` are required.
- `preview` is an optional object.
- The schema must avoid OpenAI-rejected keywords already guarded in
  `test_director_mcp_tools.py`: `oneOf`, `anyOf`, `allOf`, `not`.
- The schema should not expose capture, export, artifact, or persistence fields.

Dispatch:

```python
case "rhino_director_preview_motion":
    result = {
        "success": True,
        "data": await director_preview.preview_motion(arguments, port=port),
    }
```

Preview failures are returned as normal data with `state` rather than MCP
transport errors unless an unexpected exception escapes.

## Tool Discovery

Add `rhino_director_preview_motion` to `TOOL_GROUPS["director"]`.

Also verify whether the already-merged PR2/PR4 Director tools are missing from
that group:

- `rhino_director_replay`
- `rhino_director_replay_cancel`
- `rhino_director_compile_motion`

If missing, include them as a focused discovery fix with tests. Do not perform a
broad registry cleanup.

## Implementation Boundaries

`director_preview.preview_motion` should use injectable seams:

```python
async def preview_motion(
    arguments: dict,
    *,
    compile_motion=director_compiler.compile_motion,
    run_replay=director.run_replay,
    port: int | None = None,
) -> dict
```

This keeps unit tests free of Rhino and avoids mocking global imports.

The replay request is built from:

- `track`: compiled track
- `replay_session_id`: `preview.replay_session_id` when present
- `restore_on_finish`: `preview.restore_on_finish`, default `true`
- `fps`: `preview.fps` when present
- no `loop` when false or absent

The compiler request is created with `copy.deepcopy(arguments)` and then
`preview` is removed from that copied dictionary, so the caller's dictionary and
nested values are unchanged.

## Tests

Add focused Python tests:

- compact success calls compile then replay and omits `compile.track`;
- `preview.include_track: true` includes `compile.track`;
- compile failure returns `compile_failed` and does not call replay;
- `preview.loop: true` returns `unsupported_preview_option` before compile or
  replay;
- invalid preview-control types return `invalid_preview` before compile or
  replay;
- replay exception maps to `replay_failed` and keeps compile provenance/summary;
- replay payload with `status: "cancelled"` maps to `cancelled`;
- replay payload with unexpected status maps to `replay_failed` with raw payload;
- nested preview controls pass through to replay;
- input spec is not mutated in place;
- MCP tool registration has a clean schema and dispatches to
  `director_preview.preview_motion`;
- Director tool group includes the preview tool and the focused missing
  compile/replay tools if confirmed absent.

Run the focused baseline:

```powershell
python -m pytest `
  mcp_server\tests\test_director_motion.py `
  mcp_server\tests\test_director_compiler.py `
  mcp_server\tests\test_director_replay.py `
  mcp_server\tests\test_director_mcp_tools.py `
  mcp_server\tests\test_director_preview.py `
  -q
```

## Non-Goals

PR5 does not add:

- native C++ or managed C# changes;
- new motion, camera, material, layer, visibility, or display semantics;
- capture, video assembly, or artifact publishing;
- persistent animation artifacts or saved plans;
- preview jobs, polling, background lifecycle state, or a new cancellation tool;
- LLM-generated critique prose;
- broad tool registry cleanup.

## Acceptance

PR5 is complete when:

- agents can call one MCP tool to compile and preview a PR4 motion spec;
- output is compact by default and includes the full track only when requested;
- compile failures skip replay;
- replay completion, cancellation, and failure are distinguishable;
- replay cancellation remains out-of-band via `rhino_director_replay_cancel`;
- the focused Director Python suite passes;
- no native, C#, persistence, or replay semantic changes are introduced.
