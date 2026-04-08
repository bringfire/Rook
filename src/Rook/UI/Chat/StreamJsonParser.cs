using System;
using System.Text.Json;
using Rhino;

namespace Rook.UI.Chat
{
    /// <summary>
    /// Parses Claude Code CLI's stream-json output format.
    /// Each line is a complete JSON object (JSONL format).
    ///
    /// Event types from Claude Code CLI:
    /// - system: System messages (session start, etc.)
    /// - assistant: Text content from Claude
    /// - user: Echoed user messages (if --replay-user-messages)
    /// - result: Final result with session_id and cost info
    ///
    /// Message structure varies by type - we extract what we need for UI.
    /// </summary>
    public class StreamJsonParser
    {
        // Events for different content types
        public event Action<string>? OnTextDelta;
        public event Action<string>? OnToolStart;
        public event Action<string, string>? OnToolComplete;
        public event Action<string>? OnSessionId;
        public event Action? OnMessageComplete;
        public event Action<string>? OnError;

        // State tracking
        private string? _currentToolName;
        private string _accumulatedText = "";

        /// <summary>
        /// Parse a single line of stream-json output.
        /// </summary>
        public void ParseLine(string jsonLine)
        {
            if (string.IsNullOrWhiteSpace(jsonLine))
                return;

            try
            {
                using var doc = JsonDocument.Parse(jsonLine);
                var root = doc.RootElement;

                // Get the event type
                var eventType = GetStringProperty(root, "type");

                switch (eventType)
                {
                    case "system":
                        HandleSystemEvent(root);
                        break;

                    case "assistant":
                        HandleAssistantEvent(root);
                        break;

                    case "user":
                        // User message echo - we can ignore this
                        break;

                    case "result":
                        HandleResultEvent(root);
                        break;

                    default:
                        // Unknown event type - log for debugging
                        RhinoApp.WriteLine($"[StreamJsonParser] Unknown event type: {eventType}");
                        break;
                }
            }
            catch (JsonException ex)
            {
                // Not valid JSON - might be plain text or partial
                RhinoApp.WriteLine($"[StreamJsonParser] JSON parse error: {ex.Message}");
                RhinoApp.WriteLine($"[StreamJsonParser] Line: {jsonLine.Substring(0, Math.Min(100, jsonLine.Length))}...");
            }
            catch (Exception ex)
            {
                OnError?.Invoke($"Parser error: {ex.Message}");
            }
        }

        /// <summary>
        /// Handle system events (session info, etc.)
        /// </summary>
        private void HandleSystemEvent(JsonElement root)
        {
            // System events may contain session_id
            var sessionId = GetStringProperty(root, "session_id");
            if (!string.IsNullOrEmpty(sessionId))
            {
                OnSessionId?.Invoke(sessionId);
            }

            // Check for subtype
            var subtype = GetStringProperty(root, "subtype");
            if (subtype == "init")
            {
                // Session initialization
                RhinoApp.WriteLine("[StreamJsonParser] Session initialized");
            }
        }

        /// <summary>
        /// Handle assistant message events.
        /// </summary>
        private void HandleAssistantEvent(JsonElement root)
        {
            // Check for message content
            if (root.TryGetProperty("message", out var message))
            {
                HandleMessageContent(message);
            }

            // Direct content property
            if (root.TryGetProperty("content", out var content))
            {
                if (content.ValueKind == JsonValueKind.String)
                {
                    var text = content.GetString() ?? "";
                    if (!string.IsNullOrEmpty(text) && text != _accumulatedText)
                    {
                        // Emit the delta (new text since last update)
                        var delta = text.Substring(_accumulatedText.Length);
                        _accumulatedText = text;
                        OnTextDelta?.Invoke(delta);
                    }
                }
                else if (content.ValueKind == JsonValueKind.Array)
                {
                    HandleContentArray(content);
                }
            }
        }

        /// <summary>
        /// Handle message object with content array.
        /// </summary>
        private void HandleMessageContent(JsonElement message)
        {
            if (message.TryGetProperty("content", out var content) &&
                content.ValueKind == JsonValueKind.Array)
            {
                HandleContentArray(content);
            }
        }

        /// <summary>
        /// Handle content array (may contain text and tool_use blocks).
        /// </summary>
        private void HandleContentArray(JsonElement content)
        {
            foreach (var block in content.EnumerateArray())
            {
                var blockType = GetStringProperty(block, "type");

                switch (blockType)
                {
                    case "text":
                        var text = GetStringProperty(block, "text");
                        if (!string.IsNullOrEmpty(text))
                        {
                            // Full text replacement (not delta)
                            if (text != _accumulatedText)
                            {
                                if (text.StartsWith(_accumulatedText))
                                {
                                    var delta = text.Substring(_accumulatedText.Length);
                                    _accumulatedText = text;
                                    OnTextDelta?.Invoke(delta);
                                }
                                else
                                {
                                    _accumulatedText = text;
                                    OnTextDelta?.Invoke(text);
                                }
                            }
                        }
                        break;

                    case "tool_use":
                        var toolName = GetStringProperty(block, "name");
                        var toolId = GetStringProperty(block, "id");
                        if (!string.IsNullOrEmpty(toolName))
                        {
                            _currentToolName = toolName;
                            OnToolStart?.Invoke(toolName);
                        }
                        break;

                    case "tool_result":
                        var resultToolId = GetStringProperty(block, "tool_use_id");
                        var resultContent = "";
                        if (block.TryGetProperty("content", out var resultEl))
                        {
                            if (resultEl.ValueKind == JsonValueKind.String)
                            {
                                resultContent = resultEl.GetString() ?? "";
                            }
                            else
                            {
                                resultContent = resultEl.GetRawText();
                            }
                        }

                        if (!string.IsNullOrEmpty(_currentToolName))
                        {
                            OnToolComplete?.Invoke(_currentToolName, resultContent);
                            _currentToolName = null;
                        }
                        break;
                }
            }
        }

        /// <summary>
        /// Handle result event (final message with session info).
        /// </summary>
        private void HandleResultEvent(JsonElement root)
        {
            // Extract session_id for future resume
            var sessionId = GetStringProperty(root, "session_id");
            if (!string.IsNullOrEmpty(sessionId))
            {
                OnSessionId?.Invoke(sessionId);
            }

            // Extract cost info if present (for logging)
            if (root.TryGetProperty("cost_usd", out var cost))
            {
                RhinoApp.WriteLine($"[StreamJsonParser] Cost: ${cost.GetDouble():F4}");
            }

            // Check for any final tool completion
            if (!string.IsNullOrEmpty(_currentToolName))
            {
                OnToolComplete?.Invoke(_currentToolName, "");
                _currentToolName = null;
            }

            // Reset accumulated text for next message
            _accumulatedText = "";

            OnMessageComplete?.Invoke();
        }

        /// <summary>
        /// Helper to safely get a string property.
        /// </summary>
        private static string GetStringProperty(JsonElement element, string propertyName)
        {
            if (element.TryGetProperty(propertyName, out var prop) &&
                prop.ValueKind == JsonValueKind.String)
            {
                return prop.GetString() ?? "";
            }
            return "";
        }

        /// <summary>
        /// Reset parser state (call when starting new conversation).
        /// </summary>
        public void Reset()
        {
            _currentToolName = null;
            _accumulatedText = "";
        }
    }
}
