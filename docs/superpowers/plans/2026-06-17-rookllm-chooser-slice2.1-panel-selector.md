# RookLLM Chooser Slice 2.1 — Secondary Panel Selector Implementation Plan

> **Execution:** Inline, task-by-task in the main session, with verification after each task (this slice is small and UI-lifecycle-sensitive; subagents risk drifting from the approved seam). Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Commits:** Do NOT commit unless the user explicitly asks. Each task ends with a checkpoint (`git status --short` + a changed-file summary), not a commit.

**Goal:** Add a quiet, secondary `Model: [dropdown] [Apply]` selector to the RookChat panel that switches the current conversation's model via the existing `POST /agent/chat/model` endpoint.

**Architecture:** C#-only, consumer-only slice. A neutral, model-agnostic layout seam is added to base `ChatTab`; all model logic lives in `AgentChatTab`. The selector consumes the already-shipped backend (`GET /agent/chat/models` with `allowed_model_overrides`, and `POST /agent/chat/model`). Two pure helpers (`AgentChatClient.ParseSetModelResult`, `AgentChatTab.ShouldEnableApply`) carry the testable logic.

**Tech Stack:** C# (net48 + net7.0 dual-target), Eto.Forms (DropDown/Button/StackLayout — already in use), System.Text.Json, xUnit (`src/Rook.Tests`, `InternalsVisibleTo` already set).

---

## Constraints (preserve throughout)

- No Python/backend changes. No new endpoint. No online model discovery.
- No client-supplied `api_base`.
- `SetModelResult.Success` is derived from HTTP 2xx, never a body field.
- Pending model is status-label-only; the dropdown selects the **active** model only.
- The `ChatTab` seam stays neutral (no model concept) and visually inert for `ClaudeCodeTab`.
- `internal static` helpers are test-visible via existing `InternalsVisibleTo="Rook.Tests"`.
- Eto snippets are the **intended shape**, not sacred text. Verify exact Eto API names while coding (`StackLayoutItem(...)` constructors, `DropDown.SelectedKey`, alignment properties). If this Eto version differs, use the closest existing Eto idiom and keep the behavior unchanged; `dotnet build` is the backstop.

## File Structure

- `src/Rook/UI/Chat/AgentChatClient.cs` — add `ChatModelsInfo.AllowedModelOverrides`, `SetModelResult`, pure `ParseSetModelResult`, `SetModelAsync`. (Data + HTTP; no UI.)
- `src/Rook/UI/Chat/ChatTab.cs` — status cell becomes a vertical `StackLayout`; add `SetAuxiliaryRow(Control?)` and `OnUIStateUpdated()`. (Neutral layout seam only.)
- `src/Rook/UI/Chat/AgentChatTab.cs` — build/register selector, populate from refresh, pure `ShouldEnableApply`, Apply flow. (All model logic.)
- `src/Rook.Tests/UI/Chat/AgentChatClientParseTests.cs` — new; `ParseSetModelResult` tests.
- `src/Rook.Tests/UI/Chat/AgentChatApplyEnableTests.cs` — new; `ShouldEnableApply` tests.

All commands run from repo root `C:\UDEV\Rook`.

---

### Task 1: Client — `SetModelResult`, `ParseSetModelResult`, `AllowedModelOverrides`, `SetModelAsync`

**Files:**
- Modify: `src/Rook/UI/Chat/AgentChatClient.cs`
- Test: `src/Rook.Tests/UI/Chat/AgentChatClientParseTests.cs` (create)

- [ ] **Step 1: Write the failing tests**

Create `src/Rook.Tests/UI/Chat/AgentChatClientParseTests.cs`:

```csharp
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public class AgentChatClientParseTests
    {
        [Fact]
        public void Success_from_2xx_without_success_field()
        {
            var body = "{\"conversation_id\":\"c1\",\"model\":\"m\",\"routing\":\"local\"}";
            var r = AgentChatClient.ParseSetModelResult(200, true, body);
            Assert.True(r.Success);
            Assert.Equal(200, r.StatusCode);
            Assert.Null(r.ErrorCode);
        }

        [Fact]
        public void Conversation_processing_409()
        {
            var body = "{\"code\":\"conversation_processing\",\"error\":\"busy\"}";
            var r = AgentChatClient.ParseSetModelResult(409, false, body);
            Assert.False(r.Success);
            Assert.Equal("conversation_processing", r.ErrorCode);
            Assert.Equal("busy", r.Message);
        }

        [Fact]
        public void Model_unavailable_400_with_allowed_list()
        {
            var body = "{\"code\":\"model_override_unavailable\",\"error\":\"nope\",\"allowed_model_overrides\":[\"a\",\"b\"]}";
            var r = AgentChatClient.ParseSetModelResult(400, false, body);
            Assert.False(r.Success);
            Assert.Equal("model_override_unavailable", r.ErrorCode);
            Assert.NotNull(r.AllowedModelOverrides);
            Assert.Equal(2, r.AllowedModelOverrides!.Count);
        }

        [Fact]
        public void Not_found_404()
        {
            var body = "{\"error\":\"Conversation not found\"}";
            var r = AgentChatClient.ParseSetModelResult(404, false, body);
            Assert.False(r.Success);
            Assert.Equal("Conversation not found", r.Message);
            Assert.Null(r.ErrorCode);
        }

        [Fact]
        public void Malformed_body_does_not_throw()
        {
            var r = AgentChatClient.ParseSetModelResult(200, true, "not json");
            Assert.True(r.Success);
            Assert.Null(r.ErrorCode);
        }

        [Fact]
        public void Empty_body_follows_http_status()
        {
            var r = AgentChatClient.ParseSetModelResult(500, false, "");
            Assert.False(r.Success);
        }
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~AgentChatClientParseTests"`
Expected: build/compile failure — `AgentChatClient` does not contain a definition for `ParseSetModelResult` (red).

- [ ] **Step 3: Add the data type, parser, field, and method**

In `src/Rook/UI/Chat/AgentChatClient.cs`, add `AllowedModelOverrides` to `ChatModelsInfo` (the class currently containing only `Conversation`):

```csharp
    public class ChatModelsInfo
    {
        [JsonPropertyName("conversation")]
        public ChatConversationModelInfo? Conversation { get; set; }

        [JsonPropertyName("allowed_model_overrides")]
        public List<string> AllowedModelOverrides { get; set; } = new();
    }
```

Add a new result type near `ChatModelsInfo`:

```csharp
    /// <summary>
    /// Outcome of POST /agent/chat/model. Success reflects HTTP 2xx, not any body
    /// envelope; known error fields are parsed opportunistically.
    /// </summary>
    public class SetModelResult
    {
        public bool Success { get; set; }
        public int StatusCode { get; set; }
        public string? ErrorCode { get; set; }
        public string? Message { get; set; }
        public List<string>? AllowedModelOverrides { get; set; }
    }
```

Inside the `AgentChatClient` class, add the pure parser and the HTTP method (place them next to `GetModelsAsync`):

```csharp
        /// <summary>
        /// Pure parse of a /agent/chat/model response. Success is HTTP-2xx-derived;
        /// body is parsed opportunistically and never throws on malformed JSON.
        /// </summary>
        internal static SetModelResult ParseSetModelResult(int statusCode, bool isSuccess, string body)
        {
            var result = new SetModelResult
            {
                Success = isSuccess,
                StatusCode = statusCode,
            };

            if (string.IsNullOrWhiteSpace(body))
                return result;

            try
            {
                using var doc = JsonDocument.Parse(body);
                var root = doc.RootElement;
                if (root.ValueKind == JsonValueKind.Object)
                {
                    if (root.TryGetProperty("code", out var code) && code.ValueKind == JsonValueKind.String)
                        result.ErrorCode = code.GetString();
                    if (root.TryGetProperty("error", out var err) && err.ValueKind == JsonValueKind.String)
                        result.Message = err.GetString();
                    if (root.TryGetProperty("allowed_model_overrides", out var allowed)
                        && allowed.ValueKind == JsonValueKind.Array)
                    {
                        var list = new List<string>();
                        foreach (var item in allowed.EnumerateArray())
                        {
                            if (item.ValueKind == JsonValueKind.String)
                            {
                                var s = item.GetString();
                                if (!string.IsNullOrEmpty(s))
                                    list.Add(s!);
                            }
                        }
                        result.AllowedModelOverrides = list;
                    }
                }
            }
            catch (JsonException)
            {
                // Malformed body — keep HTTP-derived success/status, no error fields.
            }

            return result;
        }

        /// <summary>
        /// Apply a per-conversation model override via POST /agent/chat/model.
        /// The session nonce is auto-attached via the shared HttpClient headers.
        /// </summary>
        public async Task<SetModelResult> SetModelAsync(
            Uri baseUri,
            string conversationId,
            string modelOverride,
            string reason,
            CancellationToken ct = default)
        {
            var body = JsonSerializer.Serialize(new
            {
                conversation_id = conversationId,
                model_override = modelOverride,
                reason = reason,
            });
            var content = new StringContent(body, Encoding.UTF8, "application/json");
            var resp = await _client.PostAsync(new Uri(baseUri, "/agent/chat/model"), content, ct);
            var respBody = await resp.Content.ReadAsStringAsync();
            return ParseSetModelResult((int)resp.StatusCode, resp.IsSuccessStatusCode, respBody);
        }
```

(`System.Collections.Generic`, `System.Text`, `System.Text.Json`, `System.Text.Json.Serialization` are already imported at the top of this file.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~AgentChatClientParseTests"`
Expected: PASS (6 tests).

- [ ] **Step 5: Checkpoint (no commit)**

Run: `git status --short`
Summarize the changed files (`AgentChatClient.cs`, `AgentChatClientParseTests.cs`). Do not commit unless the user explicitly asks.

---

### Task 2: `AgentChatTab.ShouldEnableApply` pure helper

**Files:**
- Modify: `src/Rook/UI/Chat/AgentChatTab.cs`
- Test: `src/Rook.Tests/UI/Chat/AgentChatApplyEnableTests.cs` (create)

- [ ] **Step 1: Write the failing tests**

Create `src/Rook.Tests/UI/Chat/AgentChatApplyEnableTests.cs`:

```csharp
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public class AgentChatApplyEnableTests
    {
        [Fact]
        public void Disabled_when_no_conversation() =>
            Assert.False(AgentChatTab.ShouldEnableApply(false, false, true, "b", "a"));

        [Fact]
        public void Disabled_when_processing() =>
            Assert.False(AgentChatTab.ShouldEnableApply(true, true, true, "b", "a"));

        [Fact]
        public void Disabled_when_list_unavailable() =>
            Assert.False(AgentChatTab.ShouldEnableApply(true, false, false, "b", "a"));

        [Fact]
        public void Disabled_when_selection_empty() =>
            Assert.False(AgentChatTab.ShouldEnableApply(true, false, true, "", "a"));

        [Fact]
        public void Disabled_when_selection_equals_active() =>
            Assert.False(AgentChatTab.ShouldEnableApply(true, false, true, "a", "a"));

        [Fact]
        public void Enabled_when_selection_differs() =>
            Assert.True(AgentChatTab.ShouldEnableApply(true, false, true, "b", "a"));

        [Fact]
        public void Enabled_when_active_null_and_selection_present() =>
            Assert.True(AgentChatTab.ShouldEnableApply(true, false, true, "b", null));
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~AgentChatApplyEnableTests"`
Expected: build/compile failure — `AgentChatTab` does not contain a definition for `ShouldEnableApply` (red).

- [ ] **Step 3: Add the pure helper**

In `src/Rook/UI/Chat/AgentChatTab.cs`, add this static method inside the `AgentChatTab` class (place it near the bottom, e.g. just before `OnTabClosed`):

```csharp
        /// <summary>
        /// Pure decision for whether the panel Apply button should be enabled.
        /// Pending model is intentionally not an input: panel Apply uses
        /// /agent/chat/model only while inactive and applies to the next turn,
        /// so "selected equals active" is the sole disqualifier beyond gating.
        /// </summary>
        internal static bool ShouldEnableApply(
            bool hasConversation,
            bool isProcessing,
            bool listAvailable,
            string? selectedModel,
            string? activeModel)
        {
            if (!hasConversation || isProcessing || !listAvailable)
                return false;
            if (string.IsNullOrEmpty(selectedModel))
                return false;
            return !string.Equals(selectedModel, activeModel, StringComparison.Ordinal);
        }
```

(`System` is already imported.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~AgentChatApplyEnableTests"`
Expected: PASS (7 tests).

- [ ] **Step 5: Checkpoint (no commit)**

Run: `git status --short`
Summarize the changed files (`AgentChatTab.cs`, `AgentChatApplyEnableTests.cs`). Do not commit unless the user explicitly asks.

---

### Task 3: `ChatTab` neutral layout seam

**Files:**
- Modify: `src/Rook/UI/Chat/ChatTab.cs`

No unit test (Eto layout). Verified by build + the `ClaudeCodeTab`-parity manual check in Task 5.

- [ ] **Step 1: Add the status-cell StackLayout field**

In `src/Rook/UI/Chat/ChatTab.cs`, add a field alongside the other Eto control fields (near `private Label _statusLabel = null!;`):

```csharp
        private StackLayout _statusStack = null!;
```

- [ ] **Step 2: Rebuild the status row as a vertical StackLayout**

In `LayoutControls()`, replace the existing status `TableRow` (the nested `TableLayout` whose only row is `new TableRow(_statusLabel, null)`) so the status cell is a vertical `StackLayout`. The method becomes:

```csharp
        private void LayoutControls()
        {
            // Get the WebView (or fallback) from the substrate
            var chatContainer = _webSurface.CreateWebContent();

            // If CreateWebContent returned a TextArea fallback, capture it
            // so AddMessageToChat can append text in degraded mode.
            if (chatContainer is TextArea fallback)
                _fallbackChat = fallback;

            // Status cell is a vertical stack: the status label, plus an
            // optional auxiliary row that subclasses fill via SetAuxiliaryRow.
            // With a single item, StackLayout applies no inter-item spacing, so
            // tabs that never set an auxiliary row (e.g. ClaudeCodeTab) render
            // identically to the original single-label status row.
            _statusStack = new StackLayout
            {
                Orientation = Orientation.Vertical,
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
                Spacing = 5,
            };
            _statusStack.Items.Add(new StackLayoutItem(_statusLabel, HorizontalAlignment.Left));

            var layout = new TableLayout
            {
                Padding = new Padding(5),
                Spacing = new Size(5, 5),
                Rows =
                {
                    new TableRow(chatContainer) { ScaleHeight = true },

                    new TableRow(_statusStack),

                    new TableRow(_inputArea),

                    new TableRow(new TableLayout
                    {
                        Spacing = new Size(5, 0),
                        Rows = { new TableRow(_sendButton, _stopButton, _clearButton, null) }
                    })
                }
            };

            Content = layout;
        }
```

- [ ] **Step 3: Add `SetAuxiliaryRow` and the `OnUIStateUpdated` hook**

Add these members to `ChatTab` (place `SetAuxiliaryRow` near the status helpers, and `OnUIStateUpdated` near the other virtual hooks):

```csharp
        /// <summary>
        /// Set (or clear) an optional control shown directly beneath the status
        /// label. Passing null removes it, restoring the bare status row. The
        /// auxiliary control is only ever parented to the status stack, so this
        /// never re-parents shared controls. Neutral: the base attaches no
        /// meaning to the row's contents.
        /// </summary>
        protected void SetAuxiliaryRow(Control? row)
        {
            // Keep item 0 (the status label); drop any previously-set aux item.
            while (_statusStack.Items.Count > 1)
                _statusStack.Items.RemoveAt(_statusStack.Items.Count - 1);

            if (row != null)
                _statusStack.Items.Add(new StackLayoutItem(row, HorizontalAlignment.Left));
        }

        /// <summary>
        /// Called at the end of UpdateUIState (a runtime method, never invoked
        /// during construction). Subclasses override to re-evaluate their own
        /// controls on processing-state transitions, including the base-owned
        /// Stop button. Default is a no-op.
        /// </summary>
        protected virtual void OnUIStateUpdated()
        {
        }
```

- [ ] **Step 4: Call the hook from `UpdateUIState`**

Replace `UpdateUIState()` so it ends by invoking the hook:

```csharp
        private void UpdateUIState()
        {
            _sendButton.Enabled = !_isProcessing;
            _stopButton.Enabled = _isProcessing;
            _inputArea.Enabled = !_isProcessing;
            OnUIStateUpdated();
        }
```

- [ ] **Step 5: Build to verify it compiles**

Run: `dotnet build src/Rook/Rook.csproj -p:Configuration=Debug`
Expected: Build succeeded, 0 errors. (Pre-existing nullable warnings are expected.)

- [ ] **Step 6: Checkpoint (no commit)**

Run: `git status --short`
Summarize the changed files (`ChatTab.cs`). Do not commit unless the user explicitly asks.

---

### Task 4: `AgentChatTab` selector wiring

**Files:**
- Modify: `src/Rook/UI/Chat/AgentChatTab.cs`

No unit test (Eto wiring). Verified by build + manual checks in Task 5.

- [ ] **Step 1: Add the namespace import and selector fields**

At the top of `src/Rook/UI/Chat/AgentChatTab.cs`, add to the `using` block:

```csharp
using System.Collections.Generic;
```

Add these fields alongside the existing private fields (near `private string? _activeModelLabel;`):

```csharp
        private DropDown? _modelDropDown;
        private Button? _applyModelButton;
        private bool _suppressModelSelectionEvents;
        private bool _modelListAvailable;
```

- [ ] **Step 2: Build and register the selector in the constructor**

At the end of the `AgentChatTab` constructor (immediately after `_client = new AgentChatClient();`), add:

```csharp
            BuildModelSelector();
```

Then add the builder method to the class:

```csharp
        private void BuildModelSelector()
        {
            _modelDropDown = new DropDown();
            _modelDropDown.SelectedValueChanged += (s, e) =>
            {
                if (_suppressModelSelectionEvents)
                    return;
                UpdateApplyEnabled();
            };

            _applyModelButton = new Button { Text = "Apply", Width = 70, Enabled = false };
            _applyModelButton.Click += OnApplyModelClicked;

            var label = new Label
            {
                Text = "Model:",
                VerticalAlignment = VerticalAlignment.Center,
            };

            var row = new StackLayout
            {
                Orientation = Orientation.Horizontal,
                Spacing = 5,
                VerticalContentAlignment = VerticalAlignment.Center,
                Items =
                {
                    new StackLayoutItem(label),
                    new StackLayoutItem(_modelDropDown, expand: true),
                    new StackLayoutItem(_applyModelButton),
                }
            };

            SetAuxiliaryRow(row);
        }
```

- [ ] **Step 3: Add the populate + enable helpers**

Add these methods to the class:

```csharp
        private void PopulateModelSelector(List<string> allowed, string activeModel)
        {
            if (_modelDropDown == null)
                return;

            // Items = allowed overrides, with the active model guaranteed present
            // (prepended) so the control always reflects the true active model.
            var items = new List<string>();
            if (!string.IsNullOrEmpty(activeModel))
                items.Add(activeModel);
            foreach (var m in allowed)
            {
                if (!string.IsNullOrEmpty(m) && !items.Contains(m))
                    items.Add(m);
            }

            _modelListAvailable = items.Count > 0;

            _suppressModelSelectionEvents = true;
            try
            {
                _modelDropDown.Items.Clear();
                foreach (var m in items)
                    _modelDropDown.Items.Add(new ListItem { Text = m, Key = m });
                _modelDropDown.SelectedKey = activeModel;
            }
            finally
            {
                _suppressModelSelectionEvents = false;
            }

            UpdateApplyEnabled();
        }

        private void UpdateApplyEnabled()
        {
            if (_applyModelButton == null || _modelDropDown == null)
                return;

            _applyModelButton.Enabled = ShouldEnableApply(
                hasConversation: !string.IsNullOrEmpty(_conversationId),
                isProcessing: IsProcessing,
                listAvailable: _modelListAvailable,
                selectedModel: _modelDropDown.SelectedKey,
                activeModel: _activeModelLabel);
        }

        protected override void OnUIStateUpdated()
        {
            UpdateApplyEnabled();
        }
```

- [ ] **Step 4: Populate the selector from `RefreshModelStatusAsync`**

Replace the existing `RefreshModelStatusAsync` method body so it also reads the allowed list and populates the selector (additions: the `allowed` local and the `PopulateModelSelector` call inside the UI-thread block):

```csharp
        private async Task RefreshModelStatusAsync(string? expectedConversationId = null, CancellationToken ct = default)
        {
            var baseUri = _conversationBaseUri;
            var conversationId = expectedConversationId ?? _conversationId;
            if (baseUri == null || conversationId == null || conversationId.Length == 0)
            {
                return;
            }
            var currentConversationId = conversationId;

            try
            {
                var models = await _client.GetModelsAsync(baseUri, currentConversationId, ct);
                var conversation = models.Conversation;
                if (conversation == null || string.IsNullOrEmpty(conversation.ActiveModel))
                {
                    return;
                }
                var activeModel = conversation.ActiveModel;
                var allowed = models.AllowedModelOverrides ?? new List<string>();

                if (!IsCurrentConversation(currentConversationId))
                {
                    return;
                }

                var status = string.IsNullOrEmpty(conversation.PendingModel)
                    ? $"Model: {activeModel}"
                    : $"Model: {activeModel}; next turn: {conversation.PendingModel}";

                Application.Instance.Invoke(() =>
                {
                    if (!IsCurrentConversation(currentConversationId))
                    {
                        return;
                    }

                    _activeModelLabel = activeModel;
                    SetStatus(status, Colors.Blue);
                    PopulateModelSelector(allowed, activeModel!);
                });
            }
            catch
            {
                // Model status is best-effort feedback only.
            }
        }
```

- [ ] **Step 5: Add the Apply click handler**

Add to the class:

```csharp
        private async void OnApplyModelClicked(object? sender, EventArgs e)
        {
            var dropDown = _modelDropDown;
            var baseUri = _conversationBaseUri;
            var conversationId = _conversationId;
            if (dropDown == null || baseUri == null || string.IsNullOrEmpty(conversationId))
                return;

            var selected = dropDown.SelectedKey;
            if (string.IsNullOrEmpty(selected) || selected == _activeModelLabel || IsProcessing)
                return;

            if (_applyModelButton != null)
                _applyModelButton.Enabled = false;
            SetStatus($"Switching model to {selected}...", Colors.Blue);

            try
            {
                var result = await _client.SetModelAsync(baseUri, conversationId!, selected!, "panel selector");
                Application.Instance.Invoke(() =>
                {
                    if (!IsCurrentConversation(conversationId!))
                        return;

                    if (result.Success)
                    {
                        _ = RefreshModelStatusAsync(conversationId);
                    }
                    else if (result.StatusCode == 409 || result.ErrorCode == "conversation_processing")
                    {
                        SetStatus("Finish the current reply before changing models.",
                            Color.FromArgb(0xd9, 0x77, 0x06));
                        UpdateApplyEnabled();
                    }
                    else if (result.StatusCode == 400 || result.ErrorCode == "model_override_unavailable")
                    {
                        SetStatus("That model is no longer available — list refreshed.",
                            Color.FromArgb(0xd9, 0x77, 0x06));
                        _ = RefreshModelStatusAsync(conversationId);
                    }
                    else if (result.StatusCode == 404)
                    {
                        SetStatus("Conversation not found — restart chat.", Colors.Red);
                    }
                    else
                    {
                        SetStatus(string.IsNullOrEmpty(result.Message)
                            ? "Model switch failed." : result.Message!, Colors.Red);
                        UpdateApplyEnabled();
                    }
                });
            }
            catch (Exception ex)
            {
                Application.Instance.Invoke(() =>
                {
                    SetStatus($"Model switch failed: {ex.Message}", Colors.Red);
                    UpdateApplyEnabled();
                });
            }
        }
```

- [ ] **Step 6: Build to verify it compiles**

Run: `dotnet build src/Rook/Rook.csproj -p:Configuration=Debug`
Expected: Build succeeded, 0 errors.

- [ ] **Step 7: Checkpoint (no commit)**

Run: `git status --short`
Summarize the changed files (`AgentChatTab.cs`). Do not commit unless the user explicitly asks.

---

### Task 5: Full verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full C# test suite**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj`
Expected: PASS, including the 13 new tests (6 parse + 7 enable). No regressions.

- [ ] **Step 2: Build the plugin (Debug)**

Run: `dotnet build src/Rook/Rook.csproj -p:Configuration=Debug`
Expected: Build succeeded, 0 errors. (Do NOT claim native/C++ build verification — this slice touches no native code.)

- [ ] **Step 3: Manual verification in Rhino (focused)**

Load the plugin in Rhino and open the agent chat panel:
- `ClaudeCodeTab` parity: its layout is unchanged — no extra gap/sliver where the selector would be (the auxiliary row was never set).
- Idle agent conversation: the `Model:` dropdown shows the active model selected; picking a different model enables **Apply**; clicking Apply updates the status to the new model and the next message uses it.
- During a streaming turn: **Apply** is disabled and the selection is preserved; on completion it re-enables.
- 409 path (apply while a turn is mid-flight, if reachable): status shows "Finish the current reply before changing models." and the selection is preserved.

- [ ] **Step 4: Final state**

Run: `git status --short` and summarize all changed files across the slice. Do NOT commit — wait for the user to explicitly authorize a commit.

---

## Self-Review

**1. Spec coverage** (each spec section → task):
- C#-only / consumer-only, no Python / no new endpoint → enforced by Constraints; no backend tasks. ✓
- Explicit Apply, staged-then-confirm → Task 4 Step 5 (selection never calls server; only Apply does). ✓
- Base seam: private host, `SetAuxiliaryRow(Control?)` with null→clear, visually inert default, no ctor virtual dispatch → Task 3 (StackLayout-item mechanism; `OnUIStateUpdated` called only from runtime `UpdateUIState`). ✓
- Row between status and input → Task 3 (nested directly under the status label in the status cell). ✓
- `ShouldEnableApply(hasConversation, isProcessing, listAvailable, selectedModel, activeModel)`, pending excluded → Task 2. ✓
- Dropdown population = allowed + active guaranteed present, active selected, suppress guard → Task 4 Steps 3-4. ✓
- Pending = status-only, never selected → Task 4 Step 4 (status string uses pending; `SelectedKey = activeModel`). ✓
- `ChatModelsInfo.AllowedModelOverrides`, `SetModelAsync`, `SetModelResult`, Success from 2xx, opportunistic `code`/`error`/`allowed_model_overrides` → Task 1. ✓
- Interaction flows (200/409/400/404/other, processing) → Task 4 Step 5. ✓
- Tests: pure helpers only, no Eto harness; verify via `dotnet test` / `dotnet build`, no native claim → Tasks 1, 2, 5. ✓
- `ClaudeCodeTab` unchanged → Task 3 mechanism + Task 5 Step 3 parity check. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code; every command has expected output. ✓

**3. Type consistency:** `ParseSetModelResult(int, bool, string)` defined Task 1, used Task 1 (`SetModelAsync`); `SetModelResult` fields (`Success`/`StatusCode`/`ErrorCode`/`Message`/`AllowedModelOverrides`) defined Task 1, consumed Task 4 Step 5. `ShouldEnableApply(bool,bool,bool,string?,string?)` defined Task 2, called Task 4 Step 3 (`UpdateApplyEnabled`). `SetAuxiliaryRow(Control?)`/`OnUIStateUpdated()` defined Task 3, used Task 4 (`BuildModelSelector`/override). `_modelDropDown`/`_applyModelButton`/`_suppressModelSelectionEvents`/`_modelListAvailable` declared Task 4 Step 1, used Steps 2-5. `_activeModelLabel`/`_conversationId`/`_conversationBaseUri`/`IsCurrentConversation`/`IsProcessing` are existing members. ✓
