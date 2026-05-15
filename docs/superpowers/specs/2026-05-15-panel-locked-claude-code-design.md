# Panel-Locked Claude Code Tab Design

Date: 2026-05-15

## Problem

Rook now has two chat surfaces with different routing guarantees.

The Rook agent chat tab is already scoped to the Rhino process and document that own the panel. Each chat-service turn runs inside `rhino_request_context(process_id=..., document_serial_number=...)`, so direct bridge calls are pinned to the owning Rhino.

The embedded Claude Code tab is different. It launches a persistent `claude` subprocess that uses MCP tools through Claude's MCP config. The current tab passes `documentSerialNumber` only as system-prompt text. That helps Claude choose arguments, but it is not a hard routing boundary. If the MCP server's process-local active binding points at another Rhino, the embedded tab can follow that state and read or mutate the wrong process.

Because the Claude Code tab is visually embedded in a specific Rhino panel, user intent is local to that panel. A chat visible inside Rhino A must not route Rhino-dependent work to Rhino B.

## Goals

- Hard-lock embedded Claude Code tabs to the Rhino process that owns the panel.
- Preserve normal external Claude Desktop / Claude CLI behavior.
- Use a strict, generated, Rook-only MCP config for embedded Claude Code tabs.
- Enforce the lock in both MCP dispatcher routing and direct bridge paths.
- Fail closed for invalid lock configuration, stale owning processes, and conflicting explicit targets.
- Keep Phase 1 narrow by disabling background worker launch tools under a panel lock.

## Non-Goals

- Do not merge arbitrary user MCP servers into the embedded panel config.
- Do not support an advanced merged-MCP mode in Phase 1.
- Do not propagate panel locks into background agents in Phase 1.
- Do not rely on prompt instructions for safety.
- Do not change external Claude Desktop / Claude CLI routing semantics.

## Safety Model

The embedded Claude Code tab runs in `panel_locked` mode. The lock uses the owning Rhino process id as the authoritative process identity and the panel's `documentSerialNumber` as the authoritative document context. Process identity prevents cross-Rhino routing. Document serial context prevents same-process tool calls from falling back to whatever document Rhino considers active.

The lock applies to all Rhino-dependent tools before active binding and before read-only auto-pick. Read-only auto-pick is not allowed under `panel_locked`, because reading another Rhino from a visually embedded panel is still misleading.

The panel lock is separate from the process-local active binding. Under lock, `rhino_set_active_instance` may update the active binding only to the canonical same-process target. It must not unlock the session or change the lock target.

Error priority is:

1. If the locked owning process is not live, return `panel_target_stale` with current live instances.
2. If the lock is live and the caller targets a different live process, return `panel_target_locked`.
3. If the caller targets the same process through another same-process server record, canonicalize to the appropriate same-process target.

When both stale-owner and conflicting-target conditions are present, `panel_target_stale` wins. Once the panel owner is gone, no routing is valid.

## Claude Code Launch

`ClaudeCodeWrapper` should generate a temporary Claude MCP config for each embedded tab. The generated config contains exactly one MCP server: `rook`.

Claude should be launched with:

```text
--mcp-config <temp-config-path> --strict-mcp-config
```

The strict config is a safety boundary. It prevents:

- a second, unlocked user-level `rook` MCP entry from bypassing the panel lock;
- unrelated MCP servers from acting outside the Rhino-panel context in ways the UI does not communicate.

External Claude Desktop and external Claude CLI sessions keep using the normal user config.

The generated Rook MCP entry must preserve the runtime information needed by the normal Rook MCP config:

- command, typically the configured Python executable;
- args, typically `["-m", "rook"]`;
- cwd, typically the Rook MCP server directory;
- required environment such as `PYTHONPATH`, `PYTHONHOME`, `ROOK_INSTALL_ROOT`, `ROOK_DATA_DIR`, and `ROOK_MODE`;
- optional existing runtime env such as `CHIRP_HOME` when available.

The generated config then adds panel-lock env:

```text
ROOK_MCP_TARGET_MODE=panel_locked
ROOK_MCP_TARGET_PROCESS_ID=<owning Rhino pid>
ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER=<panel document serial>
```

The appended Claude system prompt should explain the constrained environment, but it is not part of enforcement:

```text
You are running inside the Rook Rhino panel and only have access to the panel-locked Rook MCP server.
```

Temporary config cleanup is best-effort and not security-critical. Safety comes from strict config plus server-side lock enforcement, not file deletion.

## Target Lock State

`targeting.py` should own the lock state because it already owns MCP active target resolution.

Represent the lock explicitly, for example:

```python
PanelTargetLock(
    mode="panel_locked",
    process_id=1234,
    document_serial_number=42,
    reason="rook_chat_panel",
)
```

The lock may also be represented as a nullable object with an explicit `mode`; do not overload `reason` as the mode.

`initialize_from_environment()` should run exactly once during MCP server startup/import before any tool call. Tests need helpers to reset and reinitialize lock state without relying on process-wide env leakage.

Startup behavior:

- no `ROOK_MCP_TARGET_MODE`: no lock, external behavior unchanged;
- `ROOK_MCP_TARGET_MODE=panel_locked` with valid integer `ROOK_MCP_TARGET_PROCESS_ID`: install panel lock;
- `ROOK_MCP_TARGET_MODE=panel_locked` with missing or non-integer process id: install a fail-closed configuration-error state.
- unknown `ROOK_MCP_TARGET_MODE`: install a fail-closed configuration-error state.

Invalid lock configuration must not silently behave like external Claude. Rhino-dependent tools should fail with `panel_target_config_error`.

The lock stores only identity. It must not cache port, document name, window title, object count, or other display metadata. Display metadata should be resolved fresh when reporting state.

## Resolver Behavior

`resolve_tool_route()` should enforce the panel lock before active binding and before read-only auto-pick for every Rhino-dependent tool.

Under a valid live lock:

- no explicit target: route within the locked process;
- explicit same-process native port: allow and canonicalize according to the requested tool endpoint;
- explicit same-process RoadCreator port: allow for `/rc/*` routes and canonicalize for native/GH routes as the existing endpoint selection requires;
- explicit different-process port: fail with `panel_target_locked`;
- active binding to same process: allowed;
- active binding to different process: ignored for routing because the lock has higher precedence; it may be reported by introspection, but it must not route outside the locked process;
- read-only tools do not auto-pick another process;
- mutating tools do not auto-pick another process.

Every successful locked route must install both `process_id` and `document_serial_number` into `rhino_request_context` for the duration of the tool call. If the lock has no positive document serial number, process locking still applies, but there is no document context to install.

Under a stale lock:

- all Rhino-dependent tools fail with `panel_target_stale`;
- failures include current live instances;
- no auto-pick, no silent clear, no auto-bind.

Under invalid lock config:

- all Rhino-dependent tools fail with `panel_target_config_error`;
- failures include the invalid lock details that are safe to report;
- no auto-pick or fallback behavior.

## Meta Tools

Lock-related meta behavior should be explicit.

`rhino_get_active_instance` reports active binding and lock state, including:

- `locked: true`;
- `lockMode: "panel_locked"`;
- `lockReason: "rook_chat_panel"`;
- lock target process id and document serial number;
- whether the lock is live, stale, or configuration-invalid.

`rhino_instances` also reports lock state for diagnosis from inside the embedded tab.

`rhino_set_active_instance` under a live lock:

- same process: succeeds and updates `_ACTIVE_TARGET` to the canonical same-process target;
- `match`: enrich and search same-process instances first; if same-process matches collapse to one canonical target, succeed; if no same-process match exists but another process matches, fail with `panel_target_locked`; if no process matches, fail with the normal not-found error;
- different process: fails with `panel_target_locked`;
- stale lock: fails with `panel_target_stale`;
- invalid lock config: fails with `panel_target_config_error`.

`rhino_clear_active_instance` under `panel_locked` fails. It must not be a successful no-op, because "clear" implies returning to normal auto-routing.

Expected clear failure:

```json
{
  "success": false,
  "data": {
    "error": "panel_target_locked",
    "message": "This Claude Code tab is locked to the Rhino document that owns the panel.",
    "locked": true,
    "lockMode": "panel_locked",
    "lockReason": "rook_chat_panel",
    "target": {
      "processId": 1234,
      "documentSerialNumber": 42
    }
  }
}
```

`spawn_agent` and `plan_and_execute` fail under `panel_locked` in Phase 1 before background work starts. Although bridge-level enforcement also exists, users should receive a clear explanation at launch time.

`agent_status`, `agent_abort`, and `agent_answer` may remain resolver-exempt; they do not start new Rhino work.

`rhino_launch` under `panel_locked` must not be an escape hatch. It must not auto-bind, clear the lock, or replace the lock with a newly launched process. If the lock is live, return the normal launcher result without modifying lock or active binding state. If the owner is stale, return structured `panel_target_stale`. If the lock configuration is invalid, return structured `panel_target_config_error`.

## Direct Bridge Enforcement

The MCP dispatcher is not the only execution path. Background agents and chat agents can use `ToolDispatcher`, which calls `call_rhino()` directly.

`call_rhino()` or the shared bridge selection path must enforce the panel lock too.

Under a live lock:

- if no explicit port/process is supplied, default selection is scoped to the locked process id and locked document serial number;
- if an explicit port belongs to another process, reject before HTTP dispatch with `panel_target_locked`;
- if an explicit process id conflicts with the lock, reject before HTTP dispatch with `panel_target_locked`;
- if no explicit document serial number is supplied, install the locked document serial number into bridge request context;
- same-process endpoint routing remains allowed and should select the capable peer for the endpoint.

Endpoint examples:

- locked to PID `P`, `/rc/*` selects the RoadCreator peer for `P`;
- locked to PID `P`, native routes select the native peer for `P`;
- locked to PID `P`, GH routes select the same-process capable peer according to existing route capabilities.

Under stale or invalid lock state, direct bridge calls fail closed just like MCP tool routing.

## Error Envelopes

Failure metadata must be nested under structured `data` so the existing MCP formatter preserves it.

Locked conflict:

```json
{
  "success": false,
  "data": {
    "error": "panel_target_locked",
    "message": "This Claude Code tab is locked to the Rhino document that owns the panel.",
    "locked": true,
    "lockMode": "panel_locked",
    "lockReason": "rook_chat_panel",
    "target": {
      "processId": 1234,
      "documentSerialNumber": 42
    },
    "instances": []
  }
}
```

Stale panel owner:

```json
{
  "success": false,
  "data": {
    "error": "panel_target_stale",
    "message": "The Rhino process that owns this Claude Code tab is no longer available.",
    "locked": true,
    "lockMode": "panel_locked",
    "lockReason": "rook_chat_panel",
    "target": {
      "processId": 1234,
      "documentSerialNumber": 42
    },
    "instances": []
  }
}
```

Invalid lock config:

```json
{
  "success": false,
  "data": {
    "error": "panel_target_config_error",
    "message": "This Rook MCP server was started in panel-locked mode without a valid Rhino process id.",
    "locked": true,
    "lockMode": "panel_locked",
    "lockReason": "rook_chat_panel"
  }
}
```

## Test Surface

Python targeting and bridge tests:

- no env lock preserves external Claude behavior;
- valid env initializes a panel lock once;
- tests can reset and reinitialize lock state without process env leakage;
- invalid env values fail closed with `panel_target_config_error`;
- unknown `ROOK_MCP_TARGET_MODE` fails closed with `panel_target_config_error`;
- locked resolver refuses read-only auto-pick to another process;
- locked resolver refuses mutating route to another process;
- locked MCP routes install both locked process id and locked document serial number in `rhino_request_context`;
- explicit same-process native port routes successfully;
- explicit same-process RoadCreator peer port canonicalizes correctly;
- explicit different-process port returns `panel_target_locked`;
- stale owning process returns `panel_target_stale` with live instances;
- stale lock wins over conflicting explicit target;
- `rhino_set_active_instance` same process updates only `_ACTIVE_TARGET`, not the lock;
- `rhino_set_active_instance(match=...)` searches same-process matches first and fails with `panel_target_locked` when only other-process matches exist;
- `rhino_set_active_instance` different process fails;
- `rhino_clear_active_instance` fails under lock;
- `rhino_get_active_instance` reports lock state;
- `rhino_instances` reports lock state;
- `spawn_agent` and `plan_and_execute` fail under lock before starting background work;
- `rhino_launch` under lock does not auto-bind, clear, or replace the lock;
- direct `ToolDispatcher` / `call_rhino()` path defaults to locked process and locked document serial number when no explicit target is supplied;
- direct path rejects conflicting explicit port/process;
- direct path installs locked document serial number into bridge request context;
- direct path routes `/rc/*` to the same-process RoadCreator peer;
- direct path routes native/GH endpoints to the correct same-process peer.

C# launcher tests:

- generated config contains only the `rook` MCP server;
- generated config preserves required runtime command, args, cwd, and env;
- generated config includes `ROOK_MCP_TARGET_MODE=panel_locked`;
- generated config includes owning Rhino process id;
- generated config includes panel document serial number;
- Claude launch args include `--mcp-config <temp-config-path>`;
- Claude launch args include `--strict-mcp-config`;
- appended system prompt honestly states that the tab is inside the Rook Rhino panel and only has panel-locked Rook MCP access;
- temp config cleanup is best-effort and does not affect safety.

## Phase 2 Options

If embedded Claude Code later needs background workers, implement lock propagation into spawned agents as a separate design slice. That work should snapshot the panel lock at agent launch and enforce it through worker tool execution, rather than relying on process-local active binding at call time.

If embedded Claude Code later needs non-Rook MCP servers, add an explicit advanced mode. It must prevent duplicate or unlocked `rook` entries and clearly communicate the broader capability surface in the UI.
