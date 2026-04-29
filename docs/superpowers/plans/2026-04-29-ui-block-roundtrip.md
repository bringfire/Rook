# UI-Block Round-Trip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the user submits a UI block (slider/buttons/text/confirmation) in the Rook chat panel, the agent receives the response and reacts in real time — no follow-up prompt required.

**Architecture:** Promote `/agent/chat/ui-response` from fire-and-forget to a streaming endpoint that mirrors `/agent/chat/message`. Route the WebView's Apply click through the existing `BridgeDispatcher` (`window.rookBridge.invoke`) so the C# `AgentChatClient` opens the streaming connection and dispatches events through the existing `HandleChatEvent` pipeline. Pass the user's UI submission to `runner.run_turn` as a serialized JSON `user_message` — no runner refactor.

**Tech Stack:** Python aiohttp (chat server), C# WinForms / WebView2 (chat panel), JavaScript (chat.html), pytest (server tests).

---

## Background

A user-driven Architect agent created a slider for a box dimension. Clicking Apply showed a "processing" spinner indefinitely; the agent never reacted unless the user typed a follow-up message. Triage (full diagnosis in conversation) found:

1. `handle_ui_response` at [`server.py:287-326`](mcp_server/src/rook/agent/chat/server.py#L287-L326) only appends `{role:"user", content:"{type:ui_response,...}"}` to `conv.messages` and returns `{accepted:true}`. Its own docstring documents the bug as a known unfinished feature.
2. The agent loop is **request-scoped, not conversation-scoped** — `runner.run_turn` runs only while an HTTP request is active. The fire-and-forget endpoint has no live agent loop to deliver to.
3. The WebView's `chat.html:538` `sendUIResponse` calls bare `fetch()` and ignores the response — so even if the endpoint streamed events, JS has no consumer for them. The `'executing'` CSS class added at line 572 is never cleared.

The existing `/agent/chat/message` flow is the correct pattern: `web.StreamResponse` + NDJSON + concurrency guard + `runner.run_turn` driven by the request lifetime. C# `AgentChatClient.SendMessageStreamingAsync` consumes the stream and dispatches events to the WebView via `ExecuteScript("window.chatAPI.X(...)")`. `chatAPI.updateUIBlock(blockId, {state:'done'})` already exists at `chat.html:502` to clear the spinner — it's just never called.

## File Structure

| File | Role after fix |
|---|---|
| `mcp_server/src/rook/agent/chat/server.py` | `/ui-response` becomes streaming, mirrors `/message` |
| `mcp_server/tests/test_chat_server.py` | Existing 3 ui-response tests rewritten for streaming; new tests for run_turn invocation + 409 guard |
| `src/Rook/UI/Chat/AgentChatClient.cs` | New `SendUIResponseStreamingAsync` mirroring `SendMessageStreamingAsync` |
| `src/Rook/UI/Chat/ChatTab.cs` | New virtual hook `OnUIBlockSubmitAsync(blockId, value)` returning `Task` (default: `Task.CompletedTask`); `ChatWebSurface` registers the bridge handler via `RegisterBridgeHandler` and awaits the hook |
| `src/Rook/UI/Chat/AgentChatTab.cs` | Overrides `OnUIBlockSubmitAsync` — opens streaming connection, dispatches events via existing `HandleChatEvent`, clears the active block on `done`, `error`, cancel, and HTTP failure |
| `src/Rook/UI/Chat/Resources/chat.html` | `sendUIResponse` replaces direct `fetch` with `window.rookBridge.invoke('ui_block_submit', ...)` |

`run_turn` in `chat_runner.py:403` is **unchanged** — its existing `(conversation, user_message: str, system_prompt: str)` signature already appends `user_message` itself, so passing a serialized JSON UI-response as `user_message` Just Works.

---

## Task 1: Rewrite `/ui-response` Server Tests for Streaming Behavior

**Files:**
- Modify: `mcp_server/tests/test_chat_server.py:101-151` (the three existing tests assert the old `{accepted:true}` behavior — they will fail after Task 2 unless rewritten now)

- [ ] **Step 1: Replace the three existing tests with streaming-aware versions using AioHTTPTestCase**

In `mcp_server/tests/test_chat_server.py`, replace the existing `test_ui_response_accepted`, `test_ui_response_missing_fields`, and `test_ui_response_not_found` tests with the block below. The streaming test injects a `CapturingRunner` directly onto the live `AioHTTPTestCase` app via `self.app[chat_server._RUNNER_KEY]` — no `httpx.ASGITransport` (which is incompatible with aiohttp).

```python
    async def test_ui_response_streams_turn_with_serialized_payload(self):
        """POST /agent/chat/ui-response runs an agent turn with the UI response as user_message."""
        captured: list[dict] = []

        class CapturingRunner:
            async def run_turn(self, conv, message, system_prompt):
                captured.append({"message": message, "conv_id": conv.id})
                yield ChatEvent("done", usage={})

        # Inject the capturing runner onto the running test app
        self.app[chat_server._RUNNER_KEY] = CapturingRunner()

        resp = await self.client.post("/agent/chat/start", json={"persona": "worker"})
        conv_id = (await resp.json())["conversation_id"]

        resp = await self.client.post(
            "/agent/chat/ui-response",
            json={
                "conversation_id": conv_id,
                "block_id": "blk_test1234",
                "value": {"height": 10},
            },
        )
        assert resp.status == 200
        assert resp.headers["Content-Type"].startswith("application/x-ndjson")
        body = await resp.text()
        assert '"type": "done"' in body or '"type":"done"' in body

        assert len(captured) == 1
        payload = json.loads(captured[0]["message"])
        assert payload == {
            "type": "ui_response",
            "block_id": "blk_test1234",
            "value": {"height": 10},
        }

    async def test_ui_response_missing_fields(self):
        """POST /agent/chat/ui-response rejects missing conversation_id or block_id."""
        resp = await self.client.post(
            "/agent/chat/ui-response",
            json={"conversation_id": "conv_x"},
        )
        assert resp.status == 400

        resp = await self.client.post(
            "/agent/chat/ui-response",
            json={"block_id": "blk_x"},
        )
        assert resp.status == 400

    async def test_ui_response_not_found(self):
        """POST /agent/chat/ui-response returns 404 for unknown conversation."""
        resp = await self.client.post(
            "/agent/chat/ui-response",
            json={
                "conversation_id": "conv_nonexistent",
                "block_id": "blk_test",
                "value": "confirm",
            },
        )
        assert resp.status == 404

    async def test_ui_response_rejects_when_conversation_active(self):
        """POST /agent/chat/ui-response returns 409 if a turn is already running."""
        resp = await self.client.post("/agent/chat/start", json={"persona": "worker"})
        conv_id = (await resp.json())["conversation_id"]

        # Mark the conversation as actively running
        conv = self.store.get(conv_id)
        conv.active_run_id = "run_in_flight"

        resp = await self.client.post(
            "/agent/chat/ui-response",
            json={
                "conversation_id": conv_id,
                "block_id": "blk_x",
                "value": "confirm",
            },
        )
        assert resp.status == 409

    async def test_ui_response_runs_turn_with_scoped_rhino_context(self):
        """POST /agent/chat/ui-response propagates documentSerialNumber into rhino_request_context.

        Mirrors the /message context test — agent reactions to UI submissions
        must use the same Rhino document scope as typed messages.
        """
        captured: list[dict] = []

        class ContextCapturingRunner:
            async def run_turn(self, conv, message, system_prompt):
                captured.append({
                    "conversation_document": conv.document_serial_number,
                    **bridge.get_rhino_request_context(),
                })
                yield ChatEvent("done", usage={})

        self.app[chat_server._RUNNER_KEY] = ContextCapturingRunner()

        resp = await self.client.post(
            "/agent/chat/start",
            json={"persona": "worker", "documentSerialNumber": 42},
        )
        conv_id = (await resp.json())["conversation_id"]

        resp = await self.client.post(
            "/agent/chat/ui-response",
            json={
                "conversation_id": conv_id,
                "block_id": "blk_ctx",
                "value": "ok",
                "documentSerialNumber": 99,
            },
        )
        assert resp.status == 200
        # Drain the stream
        await resp.text()

        assert len(captured) == 1
        # Latest documentSerialNumber from the request body wins (matches /message)
        assert captured[0]["conversation_document"] == 99
        assert captured[0].get("document_serial_number") == 99
```

- [ ] **Step 2: Run tests to confirm they fail in the right way**

```bash
cd mcp_server
.venv/Scripts/python.exe -m pytest tests/test_chat_server.py -v -k ui_response 2>&1 | Select-Object -Last 20
```

Expected failures (server still fire-and-forget):
- `test_ui_response_streams_turn_with_serialized_payload` — content type is `application/json`, not `application/x-ndjson`; injected runner is never called.
- `test_ui_response_rejects_when_conversation_active` — old handler returns 200 OK regardless of `active_run_id`.
- `test_ui_response_runs_turn_with_scoped_rhino_context` — old handler doesn't invoke any runner; `captured` stays empty.

The two negative tests (`missing_fields`, `not_found`) still PASS because those guards are unchanged.

- [ ] **Step 3: Commit**

```bash
git add mcp_server/tests/test_chat_server.py
git commit -m "test(chat): rewrite /ui-response tests for streaming behavior"
```

---

## Task 2: Promote `handle_ui_response` to NDJSON Streaming

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/server.py:287-326`

- [ ] **Step 1: Replace `handle_ui_response` with the streaming version**

In `mcp_server/src/rook/agent/chat/server.py`, replace the entire `handle_ui_response` function (lines 287-326) with:

```python
async def handle_ui_response(request: web.Request) -> web.StreamResponse:
    """POST /agent/chat/ui-response — receive structured input from a UI block
    and run an agent turn so the agent reacts to it in real time.

    Mirrors `handle_message`'s streaming shape: NDJSON events for the duration
    of `runner.run_turn`. The user's submission is serialized as
    `{type: ui_response, block_id, value}` and passed as the user_message to
    run_turn, which appends it to conversation history and runs the loop.
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    conv_id = body.get("conversation_id")
    block_id = body.get("block_id")
    value = body.get("value")
    raw_document_serial_number = body.get("documentSerialNumber", 0) or 0

    if not conv_id or not block_id:
        return web.json_response(
            {"error": "Missing conversation_id or block_id"}, status=400
        )

    try:
        document_serial_number = int(raw_document_serial_number)
    except (TypeError, ValueError):
        return web.json_response(
            {"error": "documentSerialNumber must be an integer"},
            status=400,
        )

    store = request.app.get(_STORE_KEY) or _get_store()
    conv = store.get(conv_id)
    if conv is None:
        return web.json_response({"error": "Conversation not found"}, status=404)

    # Same concurrency guard as /message — reject if a turn is already running
    if conv.active_run_id is not None:
        return web.json_response(
            {"error": "Conversation already processing"}, status=409
        )

    if document_serial_number > 0:
        conv.document_serial_number = document_serial_number

    # Serialize the structured UI response as the user_message for run_turn.
    # run_turn appends it to conv.messages itself.
    user_message = json.dumps({
        "type": "ui_response",
        "block_id": block_id,
        "value": value,
    })

    builder = request.app.get(_BUILDER_KEY) or _get_builder()
    runner = request.app.get(_RUNNER_KEY) or _get_runner()
    system_prompt = builder.build_system(conv.persona)

    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "application/x-ndjson",
            "Cache-Control": "no-cache",
        },
    )
    await response.prepare(request)

    try:
        with rhino_request_context(
            process_id=request.app.get(_RHINO_PROCESS_ID_KEY, 0),
            document_serial_number=conv.document_serial_number,
        ):
            async for event in runner.run_turn(conv, user_message, system_prompt):
                line = json.dumps(event.to_dict()) + "\n"
                await response.write(line.encode("utf-8"))
    except (ConnectionResetError, ConnectionError, asyncio.CancelledError):
        logger.info(
            f"Client disconnected during ui-response streaming for conversation {conv_id}"
        )
        conv.abort_event.set()

    try:
        await response.write_eof()
    except (ConnectionResetError, ConnectionError):
        pass
    return response
```

- [ ] **Step 2: Run the ui_response tests — all five should pass**

```bash
cd mcp_server
.venv/Scripts/python.exe -m pytest tests/test_chat_server.py -v -k ui_response 2>&1 | Select-Object -Last 15
```

Expected: 5/5 PASS (`streams_turn_with_serialized_payload`, `missing_fields`, `not_found`, `rejects_when_conversation_active`, `runs_turn_with_scoped_rhino_context`).

- [ ] **Step 3: Run the full chat-server test suite to confirm no regressions**

```bash
.venv/Scripts/python.exe -m pytest tests/test_chat_server.py -v 2>&1 | Select-Object -Last 15
```

Expected: all tests pass. (The CORS preflight test for `/ui-response` at line 153-159 is unaffected — middleware runs before the handler.)

- [ ] **Step 4: Commit**

```bash
git add mcp_server/src/rook/agent/chat/server.py
git commit -m "feat(chat): make /ui-response a streaming endpoint that runs an agent turn

The endpoint now mirrors /message: builds a StreamResponse, serializes the
UI submission as a user_message, and runs runner.run_turn under
rhino_request_context so the agent reacts to the user's slider/button/text
input in real time. Concurrency guard returns 409 if a turn is already in
flight, matching /message semantics."
```

---

## Task 3: Add `SendUIResponseStreamingAsync` to `AgentChatClient`

**Files:**
- Modify: `src/Rook/UI/Chat/AgentChatClient.cs:212` (insert new method after `SendMessageStreamingAsync`)

- [ ] **Step 1: Insert the new method**

Open `src/Rook/UI/Chat/AgentChatClient.cs`. After the closing `}` of `SendMessageStreamingAsync` (around line 212, before `StopAsync`), add:

```csharp
        /// <summary>
        /// Submit a UI block response and stream the agent's reaction events.
        /// Mirrors SendMessageStreamingAsync but POSTs to /agent/chat/ui-response.
        /// Includes documentSerialNumber so Rhino tool calls in the agent's
        /// reaction stay in the correct document scope.
        /// </summary>
        public async Task SendUIResponseStreamingAsync(
            Uri baseUri,
            string conversationId,
            string blockId,
            object value,
            uint documentSerialNumber,
            Action<ChatEvent> onEvent,
            CancellationToken ct = default)
        {
            var body = JsonSerializer.Serialize(new
            {
                conversation_id = conversationId,
                block_id = blockId,
                value = value,
                documentSerialNumber = documentSerialNumber,
            });
            var request = new HttpRequestMessage(HttpMethod.Post, new Uri(baseUri, "/agent/chat/ui-response"))
            {
                Content = new StringContent(body, Encoding.UTF8, "application/json")
            };

            using var resp = await _client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
            resp.EnsureSuccessStatusCode();

            using var stream = await resp.Content.ReadAsStreamAsync();
            using var reader = new StreamReader(stream, Encoding.UTF8);

            string? line;
            while ((line = await reader.ReadLineAsync()) != null)
            {
                if (ct.IsCancellationRequested) break;
                if (string.IsNullOrWhiteSpace(line)) continue;

                try
                {
                    var evt = JsonSerializer.Deserialize<ChatEvent>(line, JsonOptions);
                    if (evt != null)
                    {
                        onEvent(evt);
                    }
                }
                catch (JsonException)
                {
                    // Skip malformed lines
                }
            }
        }
```

- [ ] **Step 2: Build to verify the method compiles**

```bash
dotnet build src/Rook -c Release 2>&1 | Select-Object -Last 5
```

Expected: `Build succeeded` with no new errors. (Existing 319 nullable warnings unchanged.)

- [ ] **Step 3: Commit**

```bash
git add src/Rook/UI/Chat/AgentChatClient.cs
git commit -m "feat(chat): add SendUIResponseStreamingAsync mirroring SendMessageStreamingAsync"
```

---

## Task 4: Add `OnUIBlockSubmitAsync` Virtual Hook in `ChatTab`; Register Bridge Handler in `ChatWebSurface`

**Files:**
- Modify: `src/Rook/UI/Chat/ChatTab.cs` — add a virtual `Task`-returning hook on `ChatTab`, and register `'ui_block_submit'` via `RegisterBridgeHandler(...)` (the actual API on `RookWebSurface:275`) inside the nested `ChatWebSurface` constructor.

- [ ] **Step 1: Add the virtual hook to `ChatTab`**

In `src/Rook/UI/Chat/ChatTab.cs`, find the `ChatTab` class declaration (line 18 — `public abstract class ChatTab : Panel`). Inside it (placement: near the other protected members; if no obvious section, at the end of the class body but before the nested `ChatWebSurface` class), add:

```csharp
        /// <summary>
        /// Called when the WebView's UI block submits a value (Apply click,
        /// button choice, text input, confirmation). Default is no-op so
        /// non-agent ChatTab subclasses don't need to handle it. AgentChatTab
        /// overrides to run a streaming agent turn. Returns a Task so the
        /// bridge handler can await completion (or fire-and-forget with
        /// observed exceptions); avoids the brittle `async void` pattern.
        /// </summary>
        protected virtual Task OnUIBlockSubmitAsync(string blockId, JsonNode? value)
            => Task.CompletedTask;
```

You'll also need `using System.Text.Json.Nodes;` at the top of the file if it isn't already imported.

- [ ] **Step 2: Register the bridge handler in `ChatWebSurface`'s constructor**

The actual API is `RegisterBridgeHandler` (singular) at `RookWebSurface.cs:275`. There is no `RegisterBridgeHandlers()` virtual hook to override. Register from the constructor.

Locate `ChatWebSurface` (private nested class at `ChatTab.cs:372`). Replace its existing constructor:

```csharp
            public ChatWebSurface(ChatTab owner) => _owner = owner;
```

With:

```csharp
            public ChatWebSurface(ChatTab owner)
            {
                _owner = owner;
                RegisterBridgeHandler("ui_block_submit", HandleUIBlockSubmit);
            }

            private async Task<JsonNode?> HandleUIBlockSubmit(JsonNode? args)
            {
                // Bridge invokes are RPC-shaped, but UI block submission triggers
                // a long-running streaming agent turn. We await OnUIBlockSubmitAsync
                // so exceptions surface to the dispatcher's logger; the streaming
                // events themselves flow back to the WebView via ExecuteScript
                // inside HandleChatEvent — not through this return value.
                if (args is JsonObject obj)
                {
                    var blockId = obj["blockId"]?.GetValue<string>();
                    var value = obj["value"];
                    if (!string.IsNullOrEmpty(blockId))
                    {
                        await _owner.OnUIBlockSubmitAsync(blockId!, value);
                    }
                }
                return null;
            }
```

- [ ] **Step 3: Build and confirm no errors**

```powershell
dotnet build src/Rook -c Release 2>&1 | Select-Object -Last 5
```

Expected: `Build succeeded`. The handler is registered but `OnUIBlockSubmitAsync` is a no-op until Task 5 overrides it.

- [ ] **Step 4: Commit**

```bash
git add src/Rook/UI/Chat/ChatTab.cs
git commit -m "feat(chat): add OnUIBlockSubmitAsync hook and ui_block_submit bridge handler"
```

---

## Task 5: Override `OnUIBlockSubmitAsync` in `AgentChatTab`; Wire Stale Path Through `case "error"`

**Files:**
- Modify: `src/Rook/UI/Chat/AgentChatTab.cs` — add field for active block, override the `Task`-returning hook, dispatch events through existing `HandleChatEvent`, clear block on `done` / `error` / cancel / HTTP failure.

- [ ] **Step 1: Add an active-block field to `AgentChatTab`**

In `src/Rook/UI/Chat/AgentChatTab.cs`, near the existing private fields (e.g. `_cts`, `_conversationId`), add:

```csharp
        private string? _activeUIBlockId;
```

- [ ] **Step 2: Override `OnUIBlockSubmitAsync` (returns Task; no `_cts.Cancel()` of in-flight stream)**

Add the following method to `AgentChatTab` (placement: near the existing message-send method around line 200, before `HandleChatEvent`):

```csharp
        protected override async Task OnUIBlockSubmitAsync(string blockId, JsonNode? value)
        {
            if (_conversationBaseUri == null || string.IsNullOrEmpty(_conversationId))
            {
                return;
            }

            // Concurrency guard: if a UI block submission is already streaming,
            // ignore the new click rather than canceling the in-flight stream.
            // The server's 409 guard catches the race where two clicks both reach
            // the endpoint, but local short-circuit avoids opening a second
            // doomed HTTP request and prevents accidental cancel of the first
            // turn from a double-click.
            if (_activeUIBlockId != null)
            {
                return;
            }

            _activeUIBlockId = blockId;
            _cts = new CancellationTokenSource();
            var textBuffer = new StringBuilder();
            SetProcessing(true);

            // Pass the raw JsonNode as the value payload — JsonSerializer
            // round-trips JsonNode correctly into the request body.
            object valuePayload = (object?)value ?? new { };

            try
            {
                var currentDocument = GetCurrentDocumentSerialNumber();
                await _client.SendUIResponseStreamingAsync(
                    _conversationBaseUri,
                    _conversationId,
                    blockId,
                    valuePayload,
                    currentDocument,
                    evt => HandleChatEvent(evt, textBuffer),
                    _cts.Token);
            }
            catch (OperationCanceledException)
            {
                MarkActiveUIBlockStale();
                SetProcessing(false);
            }
            catch (HttpRequestException ex)
            {
                AddMessageToChat("error", $"UI block submission failed: {ex.Message}");
                MarkActiveUIBlockStale();
                SetProcessing(false);
            }
            catch (InvalidOperationException ex)
            {
                AddMessageToChat("error", ex.Message);
                MarkActiveUIBlockStale();
                SetProcessing(false);
            }
        }

        private void MarkActiveUIBlockStale()
        {
            if (_activeUIBlockId == null) return;
            var blockId = _activeUIBlockId;
            _activeUIBlockId = null;
            Application.Instance.Invoke(() =>
            {
                ExecuteScript(
                    $"window.chatAPI.updateUIBlock('{EscapeForJavaScript(blockId)}', {{state:'stale'}})");
            });
        }
```

- [ ] **Step 3: Hook the `done` event to clear the active block (state:'done')**

Find the `case "done":` arm in `HandleChatEvent` (around line 301). Modify it to clear the active UI block before the existing finalization logic:

```csharp
                    case "done":
                        if (_activeUIBlockId != null)
                        {
                            var doneBlockId = _activeUIBlockId;
                            _activeUIBlockId = null;
                            ExecuteScript(
                                $"window.chatAPI.updateUIBlock('{EscapeForJavaScript(doneBlockId)}', {{state:'done', result_text:'Submitted'}})");
                        }
                        FinalizeStreaming();
                        if (_lastHealth != null)
                        {
                            ApplyHealthStatus(_lastHealth);
                        }
                        else
                        {
                            SetStatus("Ready", Colors.Green);
                        }
                        SetProcessing(false);
                        break;
```

(Keep the existing `SetProcessing(false)` and the rest of the case body intact — only insert the `_activeUIBlockId` clear at the top.)

- [ ] **Step 4: Hook the `error` event to mark the active block stale**

Find the `case "error":` arm in `HandleChatEvent` (currently at lines 314-319). Insert a `MarkActiveUIBlockStale()` call before the existing logic so a streamed error from the runner / server clears the spinner instead of leaving it hanging:

```csharp
                    case "error":
                        MarkActiveUIBlockStale();
                        FinalizeStreaming();
                        AddMessageToChat("error", evt.Content ?? "Unknown error");
                        SetStatus("Error", Colors.Red);
                        SetProcessing(false);
                        break;
```

- [ ] **Step 5: Build**

```powershell
dotnet build src/Rook -c Release 2>&1 | Select-Object -Last 5
```

Expected: `Build succeeded`.

- [ ] **Step 6: Commit**

```bash
git add src/Rook/UI/Chat/AgentChatTab.cs
git commit -m "feat(chat): override OnUIBlockSubmitAsync — stream reaction + clear block

Tracks the in-flight blockId, opens the streaming connection via
SendUIResponseStreamingAsync, dispatches events through the existing
HandleChatEvent pipeline, and clears the block (state:'done') when the
agent's turn finishes. Marks block stale on cancel / HTTP failure /
InvalidOperationException AND on streamed 'error' events from the runner.
Concurrency guard early-returns if a submission is already in flight
rather than canceling the in-flight stream — server 409 catches the rest."
```

---

## Task 6: Replace Direct `fetch` in `chat.html` with `rookBridge.invoke`; Reorder Optimistic-State Updates

**Files:**
- Modify: `src/Rook/UI/Chat/Resources/chat.html:538-557` (`sendUIResponse`) and the three caller sites at lines 559-587 (`handleBlockSubmit`, `handleBlockAction`, `handleBlockTextSubmit`).

The `executing` CSS class is added *after* `sendUIResponse(...)` today. Once `sendUIResponse` synchronously calls `updateUIBlock(blockId, {state:'stale'})` on bridge absence/failure, the post-call `executing` add would leave the block both stale and executing. Fix order: add `executing` first (the optimistic state), then dispatch — stale/error/done handlers can then transition the block reliably.

- [ ] **Step 1: Rewrite `sendUIResponse` and attach failure handling on the bridge promise**

In `src/Rook/UI/Chat/Resources/chat.html`, replace the existing `sendUIResponse` function (lines 538-557) with:

```javascript
        function sendUIResponse(blockId, value) {
            // Route through the C# bridge so the streaming agent reaction
            // can flow back through the existing chatAPI dispatch path.
            // (Direct fetch was fire-and-forget and had no consumer for
            // streamed events — see 2026-04-29 round-trip plan.)
            try {
                if (!window.rookBridge || typeof window.rookBridge.invoke !== 'function') {
                    // No bridge — mark the block stale so the spinner clears.
                    updateUIBlock(blockId, { state: 'stale' });
                    return;
                }
                var result = window.rookBridge.invoke('ui_block_submit', { blockId: blockId, value: value });
                // rookBridge.invoke returns a Promise. The bridge handler
                // intentionally returns null (streaming events flow back
                // separately), but we still attach .catch so unknown
                // handler / dispatch errors don't become silent unhandled
                // promise rejections while the optimistic spinner remains.
                if (result && typeof result.catch === 'function') {
                    result.catch(function(_err) {
                        updateUIBlock(blockId, { state: 'stale' });
                    });
                }
            } catch (e) {
                updateUIBlock(blockId, { state: 'stale' });
            }
        }
```

The unused `_serviceHost`, `_servicePort`, `_conversationId` references and the `__rookSessionNonce` header forwarding are no longer needed here — the C# bridge handler has all that context already.

- [ ] **Step 2: Move `executing` class addition before `sendUIResponse` in the three caller sites**

In `src/Rook/UI/Chat/Resources/chat.html`, replace the existing `handleBlockSubmit`, `handleBlockAction`, and `handleBlockTextSubmit` functions (lines 559-587) with:

```javascript
        function handleBlockSubmit(blockId, blockType) {
            var block = document.getElementById('ui-block-' + blockId);
            if (!block) return;
            var value = {};

            if (blockType === 'slider' || blockType === 'composite') {
                var sliders = block.querySelectorAll('input[type="range"]');
                sliders.forEach(function(s) { value[s.id] = parseFloat(s.value); });
                var inputs = block.querySelectorAll('.ui-text-input');
                inputs.forEach(function(inp) { value[inp.id] = inp.value; });
            }

            // Add optimistic 'executing' BEFORE dispatch so a synchronous
            // bridge failure inside sendUIResponse can transition the block
            // to 'stale' from a known-good baseline.
            block.classList.add('executing');
            sendUIResponse(blockId, value);
        }

        function handleBlockAction(blockId, actionValue) {
            var block = document.getElementById('ui-block-' + blockId);
            if (block) block.classList.add('executing');
            sendUIResponse(blockId, actionValue);
        }

        function handleBlockTextSubmit(blockId) {
            var input = document.getElementById(blockId + '-input');
            var value = input ? input.value : '';
            var block = document.getElementById('ui-block-' + blockId);
            if (block) block.classList.add('executing');
            sendUIResponse(blockId, value);
        }
```

(`handleBlockCancel` is unchanged — it adds `'ui-block--stale'`, not `'executing'`, and doesn't have the ordering bug.)

- [ ] **Step 3: Build the C# project to embed the updated resource**

The HTML file is loaded as an embedded resource by `ChatWebSurface.ResourceRoot = "Rook.UI.Chat.Resources"`. Building the C# project re-embeds it:

```powershell
dotnet build src/Rook -c Release 2>&1 | Select-Object -Last 5
```

Expected: `Build succeeded`.

- [ ] **Step 4: Commit**

```bash
git add src/Rook/UI/Chat/Resources/chat.html
git commit -m "feat(chat): route UI block submissions through rookBridge.invoke

Replace direct fetch with rookBridge.invoke('ui_block_submit', ...) so the
streaming agent reaction can flow back through the existing chatAPI dispatch
path. Attach .catch on the invoke promise to mark the block stale on bridge
failure. Reorder caller-site state mutations so 'executing' is added BEFORE
sendUIResponse — synchronous stale transitions inside the dispatch path can
then transition cleanly without leaving the block both executing and stale."
```

---

## Task 7: Manual Integration Smoke Test

**Files:** Live Rhino + chat panel; no code changes.

- [ ] **Step 1: Restart Rhino so the patched plugin loads**

The C# changes require a fresh Rook plugin load. Close and reopen Rhino. The chat server (spawned by the C# plugin) will pick up the patched `server.py` automatically since it's in the editable-installed venv.

- [ ] **Step 2: Drive the original failure case**

Open the Rook chat panel. To the Architect agent, ask:

```
Create a box with sliders for length, width, and height.
```

Wait for the slider UI block to render.

- [ ] **Step 3: Verify the round-trip works**

Move each slider to a new value. Click Apply.

Expected behavior:
- The block briefly shows the `'executing'` style (existing optimistic UI).
- The agent's reaction streams in below — text response and/or a `gh_edit` / `rhino_create` tool call updating the box dimensions in Rhino.
- The block transitions to `'done'` state with text `Submitted` once the agent's turn ends.
- The Stop button is active during the streaming and cancels cleanly if pressed.

If any of those fail, capture the error in the chat panel and the chat-server log (`%TEMP%/rook/chat-service-*.log` or stderr if running interactively) and stop here — return to Phase 1.

- [ ] **Step 4: Verify concurrency guard**

Once `SetProcessing(true)` runs, the typed-message input is disabled, so the typed-message route can't be exercised through the UI. Use one of these instead:

**Primary — rapid double-Apply (exercises the C# early-return guard at Task 5 step 2):**

Submit a UI block. While the agent's reaction is still streaming (you'll see `Receiving...` or tool cards rendering), click Apply on the same block again, or move a slider and click Apply.

Expected: the second click is silently ignored at the C# layer — no second HTTP request opens, the in-flight stream is *not* canceled, and the agent's first reaction completes normally.

**Secondary — direct POST (exercises the server 409 guard at Task 2 step 1):**

While a UI block stream is active, run this from a separate PowerShell window (substitute the live conversation_id and the chat-server port from `%TEMP%/rook/chat-service-*.json`):

```powershell
$body = @{
    conversation_id = '<live-conv-id>'
    message         = 'should be rejected'
} | ConvertTo-Json
Invoke-WebRequest -Method Post -Uri "http://127.0.0.1:<port>/agent/chat/message" `
    -ContentType 'application/json' `
    -Headers @{ 'X-Rook-Session' = $env:ROOK_SESSION_NONCE } `
    -Body $body -SkipHttpErrorCheck | Select-Object StatusCode, Content
```

Expected: `StatusCode: 409` with body `{"error":"Conversation already processing"}`. The UI-block streaming continues uninterrupted.

- [ ] **Step 5: Verify cancel path**

Submit a UI block. Press Stop while the agent is still streaming.

Expected: the streaming cancels, the block transitions to `'stale'` (handled by `MarkActiveUIBlockStale`), and `SetProcessing(false)` clears the spinner.

- [ ] **Step 6: Final verification — full server test suite**

```bash
cd mcp_server
.venv/Scripts/python.exe -m pytest tests/test_chat_server.py -v 2>&1 | Select-Object -Last 15
```

Expected: all tests pass.

---

## Self-Review Notes

- **Spec coverage:** Every original reviewer note plus every blocking-fix correction is addressed.
  - Round-trip itself: Tasks 2 (server streaming), 3 (C# client), 4 (bridge handler), 5 (override + event wiring), 6 (chat.html), 7 (smoke test).
  - Reviewer fix #1 (no `httpx.ASGITransport` for aiohttp): Task 1 step 1 uses `AioHTTPTestCase` + `self.app[chat_server._RUNNER_KEY] = CapturingRunner()`.
  - Reviewer fix #2 (API is `RegisterBridgeHandler`, no `RegisterBridgeHandlers()` hook): Task 4 step 2 uses the constructor path with `RegisterBridgeHandler(...)`.
  - Reviewer fix #3 (no `async void`): Task 4 step 1 declares `protected virtual Task OnUIBlockSubmitAsync(...)`; Task 5 step 2's override returns `Task`; Task 4 step 2's bridge handler awaits it.
  - Reviewer fix #4 (don't cancel in-flight stream on Apply): Task 5 step 2 early-returns when `_activeUIBlockId != null` instead of calling `_cts.Cancel()`. Server 409 catches the network-race case.
  - Reviewer fix #5 (clear block on streamed `"error"` events): Task 5 step 4 inserts `MarkActiveUIBlockStale()` at the top of `case "error":`.
  - Reviewer tweak: documentSerialNumber → `rhino_request_context` propagation test added — Task 1 step 1 includes `test_ui_response_runs_turn_with_scoped_rhino_context`.
  - Reviewer tweak: `.catch(...)` on `rookBridge.invoke` promise — Task 6 step 1 attaches it and falls back to `updateUIBlock(blockId, {state:'stale'})` on bridge failure or absence.
  - Reviewer tweak: PowerShell-friendly verification commands — all `tail -N` replaced with `Select-Object -Last N`.
- **Placeholder check:** Every step shows the actual code or command. No conditional branches left in the implementation steps — Task 4 step 2 commits to the constructor-registration path now that the API has been verified.
- **Type/method consistency:** `SendUIResponseStreamingAsync(baseUri, conversationId, blockId, value, documentSerialNumber, onEvent, ct)` declared in Task 3 matches the call site in Task 5 step 2. `OnUIBlockSubmitAsync(string blockId, JsonNode? value) -> Task` declared in Task 4 step 1 matches the override in Task 5 step 2 and the awaiter in Task 4 step 2's `HandleUIBlockSubmit`. `_activeUIBlockId` introduced in Task 5 step 1 and used in steps 2, 3, 4 (and inside `MarkActiveUIBlockStale`).
- **Concurrency model:** Three guards in series. (1) C# early-return when `_activeUIBlockId != null` (prevents same-process double-click from opening a redundant request). (2) Server 409 when `conv.active_run_id` is set (catches racy multi-source submissions or anything that slipped past guard 1). (3) Streamed `"error"` from the runner can still arrive asynchronously and clears the block via Task 5 step 4. The Stop button cancels the active stream via the existing `_cts` mechanism, surfacing as `OperationCanceledException` and routing to `MarkActiveUIBlockStale()`.
- **Out of scope:** Changing `run_turn`'s signature to support a no-message continuation path. Reviewer explicitly rejected; Task 2 serializes the UI response as `user_message`. The serialized JSON is parseable by the LLM in the user-message slot.
- **Out of scope:** Disabling Apply in the WebView while a turn is active. Today the C# guard early-returns and the spinner stays in `'executing'` until `done`/`error`/cancel transitions it. A future refinement could grey out the Apply button optimistically; deferred.
