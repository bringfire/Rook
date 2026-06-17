# RookLLM Chooser Slice 2.1 — Secondary Panel Selector Design

## Status

Design for review. This is Slice 2.1 of the Model Control phase: a quiet, secondary
visual model selector in the RookChat panel. It builds on Slice 2 (agent-mediated
per-conversation model setting, PR #258) and Slice 1 (model visibility, PR #257).

The agent-mediated path ("use my local Qwen for this chat" → `set_chat_model`) remains
the **primary** UX. This slice adds a fallback control for users who prefer to point and
click. It is deliberately understated: it must not read as a primary toolbar.

## Goal

Let a user switch the current conversation's model from the chat panel using a small
`Model: [dropdown] [Apply]` control, consuming only the existing backend surface. Selecting
a model stages intent locally; clicking **Apply** performs the switch via the existing
`POST /agent/chat/model` endpoint. The switch is per-conversation and applies to the next
turn, exactly as the agent-mediated path does.

## Non-Goals

- No Python/backend changes. All required endpoints and payload fields already exist.
- No process-wide profile switching, no writes to persistent profile/config files.
- No DSPy reconfiguration, no Guardian/planner/worker routing changes.
- No client-supplied `api_base`. Routing is bound server-side only.
- No online model-name discovery, provider-doc scraping, or dynamic cloud catalog. The
  panel displays only backend-provided `allowed_model_overrides`. A future chooser
  catalog / knowledge-store slice owns online discovery.
- No replacement of the agent-mediated `set_chat_model` path. This selector is secondary.
- The selector is not exposed in `ClaudeCodeTab`; that tab has no per-conversation model
  concept and must remain visually and behaviorally unchanged.

## Existing Ground Truth (Reuse, Do Not Rebuild)

Backend (verified on `main`, HEAD = commit 26019a0 / PR #258):

- `GET /agent/chat/models` returns a payload with top-level `allowed_model_overrides`
  (`model_status.build_models_payload`, model_status.py:489). With an optional
  `?conversation_id=...` it adds a `conversation` section with `active_model`,
  `active_routing`, `pending_model`, `pending_routing`, `pending_applies_to`,
  `api_base_source` (server.py:148, `build_conversation_model_status`).
- `POST /agent/chat/model` (server.py:262) validates the override server-side and applies
  it. Status codes:
  - `200` — applied; body is the conversation model payload (the result of
    `conv.apply_model_override(...)` plus `conversation_id` and `persona`). It is **not**
    guaranteed to be a `{ "success": true }` envelope.
  - `409` with `{ "code": "conversation_processing", "error": ... }` when
    `conv.active_run_id is not None`.
  - `400` with `{ "code": "model_override_unavailable", "error": ..., "model_override": ...,
    "allowed_model_overrides": [...] }` for a disallowed/stale override.
  - `404` `{ "error": "Conversation not found" }` for an unknown conversation id.
  - All mutating routes are nonce-gated.

C# (already present):

- `AgentChatClient.GetModelsAsync(baseUri, conversationId?, ct)` (AgentChatClient.cs:200)
  with the session nonce auto-attached via `_client` default headers.
- `ChatModelsInfo` / `ChatConversationModelInfo` deserialize the `conversation` section but
  **not** `allowed_model_overrides`.
- `AgentChatTab.RefreshModelStatusAsync(...)` (AgentChatTab.cs:168) already refreshes model
  status on conversation start, on `model_update` events, and on `done`. It writes a
  transient `"Model: X; next turn: Y"` string to the shared status label.

Panel chrome: `ChatTab` (abstract base) builds a 4-row Eto `TableLayout` in a private
`LayoutControls()` and assigns `Content` in the base constructor: WebView → status label →
input → buttons (ChatTab.cs:140). `AgentChatTab` and `ClaudeCodeTab` both derive from it.
Eto `DropDown` is already used elsewhere (e.g. `SettingsDialog`), so no new dependency.

## Design Decision: C#-Only, Consumer-Only Slice

Because the backend is complete, Slice 2.1 is a pure C# slice that consumes the existing
HTTP surface. It adds a narrow, model-agnostic seam in the base `ChatTab` for layout, and
keeps all model logic inside `AgentChatTab`.

## Apply Interaction

Explicit, staged-then-confirm:

- The dropdown shows the appliable model list and the current selection. Changing the
  selection **never** calls the server.
- A small **Apply** button next to the dropdown performs the switch via
  `POST /agent/chat/model`.
- Apply is disabled when any of: no conversation exists, a turn is processing, the model
  list is unavailable, the selection is empty, or the selection equals the active model.

This keeps a routing mutation deliberate, gives a clean disable target during processing,
and reinforces the secondary feel.

## Base-Class Seam (`ChatTab`)

Two additions, both generic and free of any model concept. Neither is invoked during base
construction, avoiding C# constructor virtual-dispatch hazards.

### Auxiliary row host (layout slot)

- A **private** host field in `ChatTab` (an Eto container, e.g. `Panel`), inserted by
  `LayoutControls()` as a new row positioned **between the status label and the input
  area**. Final row order: WebView → status label → auxiliary row → input → buttons.
- The host is **hidden by default** (`Visible = false`) — not merely empty. An empty `Panel`
  can still leave spacing/a sliver in Eto, so default `ClaudeCodeTab` rendering must be made
  visually identical by hiding the host outright.
- Exposed only through a method, not a property:

  ```csharp
  protected void SetAuxiliaryRow(Control? row);
  ```

  - `SetAuxiliaryRow(row)` sets the host content to `row` and makes the host visible.
  - `SetAuxiliaryRow(null)` clears the host content and hides it.

  No `protected` field/property is exposed unless a concrete need appears; the subclass does
  not get direct handle access to the host.

### UI-state notification hook

- `protected virtual void OnUIStateUpdated() { }` — default no-op.
- Called **only** at the end of the existing runtime `UpdateUIState()` method (which itself
  is never called from the constructor). This delivers every processing transition —
  including the base-owned **Stop** button — to subclasses so they can re-evaluate dependent
  controls.
- The base passes no model-specific information and makes no `AgentChatTab` assumptions.

`ClaudeCodeTab` overrides neither hook → unchanged.

## `AgentChatTab` — The Selector

### Construction and wiring

- After base construction completes (in the `AgentChatTab` constructor body), build the
  selector control — an Eto `DropDown` plus an **Apply** `Button`, laid out as
  `Model: [dropdown] [Apply]` — and register it via `SetAuxiliaryRow(selectorRow)`.
- Subscribe `DropDown.SelectedValueChanged` to a handler that only re-evaluates Apply's
  enabled state (never calls the server).
- Subscribe the Apply button click to the apply flow below.

### Populating the dropdown

Done inside the existing `RefreshModelStatusAsync(...)`, which already runs on start /
`model_update` / `done`:

- Items = the backend `allowed_model_overrides`, with the **active model guaranteed
  present** (prepended if the backend's allowed set does not already include it) so the
  control always reflects the true active model.
- Selection = the active model.
- All programmatic item/selection updates happen under a `_suppressSelectionEvents` guard so
  refreshes never run apply/enable side effects or create feedback loops.

### Pending-model handling

- The dropdown represents the **active / appliable** model list only.
- If `/agent/chat/models` reports a `pending_model`, it stays in the **status label** as
  today (`"Model: X; next turn: Y"`). It is display/status only for this selector.
- The dropdown does **not** select a pending model. It selects pending only once that model
  has actually become active (i.e. surfaces through `active_model` on a later refresh).
- During processing Apply is disabled, so an agent-mediated pending switch remains feedback,
  never a competing panel action.

### Apply-enabled decision (pure, testable)

Extracted to a pure static method, free of Eto:

```csharp
internal static bool ShouldEnableApply(
    bool hasConversation,
    bool isProcessing,
    bool listAvailable,
    string? selectedModel,
    string? activeModel);
```

Returns `true` only when `hasConversation && !isProcessing && listAvailable &&
!string.IsNullOrEmpty(selectedModel) && selectedModel != activeModel`. Pending model is not
an input: panel Apply uses `/agent/chat/model` only while the conversation is inactive and
applies immediately to the next turn, so "selected equals active" is the sole disqualifier
beyond the gating booleans.

Recomputed from: `OnUIStateUpdated()` (processing transitions incl. Stop), the end of
`RefreshModelStatusAsync`, and `DropDown.SelectedValueChanged`.

## Client Additions (`AgentChatClient`)

### `ChatModelsInfo.AllowedModelOverrides`

Add:

```csharp
[JsonPropertyName("allowed_model_overrides")]
public List<string> AllowedModelOverrides { get; set; } = new();
```

### `SetModelAsync` + `SetModelResult`

```csharp
public class SetModelResult
{
    public bool Success { get; set; }            // based on HTTP 2xx, NOT a body field
    public int StatusCode { get; set; }
    public string? ErrorCode { get; set; }       // body "code", when present
    public string? Message { get; set; }         // body "error", when present
    public List<string>? AllowedModelOverrides { get; set; } // body field, when present
}

public async Task<SetModelResult> SetModelAsync(
    Uri baseUri,
    string conversationId,
    string modelOverride,
    string reason,
    CancellationToken ct = default);
```

- POSTs `{ conversation_id, model_override, reason }` to `/agent/chat/model`. The session
  nonce is auto-attached via the existing `_client` default headers (same as
  `GetModelsAsync`).
- It does **not** call `EnsureSuccessStatusCode`. `Success` is derived from
  `response.IsSuccessStatusCode` (HTTP 2xx), independent of any body envelope.
- Known fields (`code`, `error`, `allowed_model_overrides`) are parsed **opportunistically**;
  absent fields leave the corresponding result properties null. Body parsing is isolated in a
  pure helper, e.g.:

  ```csharp
  internal static SetModelResult ParseSetModelResult(int statusCode, bool isSuccess, string body);
  ```

  so it can be unit-tested without an HTTP round trip.

## Interaction Flows (Apply click)

1. Read the selected model and current conversation/baseUri. If Apply's preconditions no
   longer hold, do nothing.
2. Call `SetModelAsync(...)`.
3. Branch on the result, all UI updates marshaled via `Application.Instance.Invoke`:
   - **`Success` (2xx):** refresh `/agent/chat/models?conversation_id=...` (single source of
     truth), update the status label, re-disable Apply (selection now equals active).
   - **`409` / `conversation_processing`:** keep the dropdown selection intact, set status
     `"Finish the current reply before changing models."`
   - **`400` / `model_override_unavailable`:** the list went stale — refresh
     `/agent/chat/models`, set status `"That model is no longer available — list refreshed."`
   - **`404`:** set status `"Conversation not found — restart chat."`
   - **Other non-2xx:** set status with `Message` if present, else a generic failure note.
4. During processing Apply is already disabled via `OnUIStateUpdated`; the server `409`
   remains the backstop if a race occurs.

## Testing

C# unit tests (xUnit, net48) under `src/Rook.Tests/UI/Chat/`, targeting pure helpers only —
no Eto harness:

- `ShouldEnableApply(...)` truth table: every gating boolean false/true, empty selection,
  selection equal vs different from active.
- `ParseSetModelResult(...)`: 2xx success payload (conversation model body, no `success`
  field) → `Success == true`; `409` body → `ErrorCode == "conversation_processing"`; `400`
  body → `ErrorCode == "model_override_unavailable"` with `AllowedModelOverrides` populated;
  `404` body → `Success == false`, message parsed; malformed/empty body → no throw, success
  follows the HTTP status.

Verification commands:

- `dotnet test src/Rook.Tests/Rook.Tests.csproj`
- and/or `dotnet build src/Rook/Rook.csproj -p:Configuration=Debug`

Do **not** claim native (C++) build verification; this slice does not touch native code.

Manual verification in Rhino (focused, optional):

- Idle conversation: pick a different model, click Apply → status reflects the switch; the
  next message uses it.
- During a streaming turn: Apply is disabled; if forced, the `409` path shows the
  "finish the current reply" message and the selection is preserved.
- Stale model: applying a model that has since disappeared shows the refreshed-list message.

Regression:

- Existing 31 Python chat/model tests remain green (unchanged code).
- `ClaudeCodeTab` layout is visually unchanged (auxiliary host hidden by default).

## Files Touched

- `src/Rook/UI/Chat/ChatTab.cs` — private auxiliary row host, `SetAuxiliaryRow(Control?)`,
  `OnUIStateUpdated()` hook at the end of `UpdateUIState()`.
- `src/Rook/UI/Chat/AgentChatTab.cs` — selector build/registration, dropdown population in
  `RefreshModelStatusAsync`, `_suppressSelectionEvents` guard, Apply flow, pure
  `ShouldEnableApply`.
- `src/Rook/UI/Chat/AgentChatClient.cs` — `ChatModelsInfo.AllowedModelOverrides`,
  `SetModelAsync`, `SetModelResult`, pure `ParseSetModelResult`.
- `src/Rook.Tests/UI/Chat/` — new unit tests for the two pure helpers.

Avoid changes to: native routes, Python backend, model-profile persistence, DSPy
startup/reconfigure, `ClaudeCodeTab` behavior.

## Follow-Ups

- A later chooser catalog / knowledge-store slice owns online model discovery; the panel
  stays a consumer of backend-provided `allowed_model_overrides`.
- Slice 3 handles process-wide profile writes, config security, local-detection cache
  invalidation after profile writes, and DSPy reconfiguration/liveness.
