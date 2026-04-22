using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;

namespace Rook.UI.Web
{
    /// <summary>
    /// Pure-logic JS↔C# bridge dispatcher. Owns the handler registry and the
    /// invoke/response wire format. Knows nothing about WebView2 — the
    /// surface adapter feeds raw JSON in and posts the returned JSON back.
    ///
    /// Wire format (JS → C#):
    ///   { "type": "invoke", "method": "...", "requestId": "...", "args": ... }
    ///
    /// Wire format (C# → JS, returned as a string from <see cref="DispatchAsync"/>):
    ///   { "type": "response", "requestId": "...", "ok": true,  "result": ... }
    ///   { "type": "response", "requestId": "...", "ok": false, "error":  "..." }
    ///
    /// Error contract is generic by substrate policy — handler exception
    /// messages never reach JS. Full exception detail goes to the configured
    /// log callback.
    /// </summary>
    internal sealed class BridgeDispatcher
    {
        private readonly Dictionary<string, Func<JsonNode?, Task<JsonNode?>>> _handlers
            = new(StringComparer.Ordinal);
        private readonly Action<string>? _log;

        public BridgeDispatcher(Action<string>? log = null)
        {
            _log = log;
        }

        public int HandlerCount => _handlers.Count;

        public bool HasHandler(string method)
            => method != null && _handlers.ContainsKey(method);

        public void Register(string method, Func<JsonNode?, Task<JsonNode?>> handler)
        {
            if (method is null) throw new ArgumentNullException(nameof(method));
            if (string.IsNullOrWhiteSpace(method))
                throw new ArgumentException(
                    "Bridge handler method name must be non-empty.", nameof(method));
            if (handler is null) throw new ArgumentNullException(nameof(handler));
            if (_handlers.ContainsKey(method))
                throw new ArgumentException(
                    $"Bridge handler for method '{method}' already registered.", nameof(method));

            _handlers[method] = handler;
        }

        /// <summary>
        /// Parse incoming bridge JSON, dispatch to the registered handler,
        /// and return the response JSON to post back to JS. Returns null
        /// when no response is possible (malformed, missing requestId, or
        /// not an invoke message).
        /// </summary>
        public async Task<string?> DispatchAsync(string? incomingJson)
        {
            if (string.IsNullOrEmpty(incomingJson))
            {
                _log?.Invoke("Bridge dispatcher: empty incoming message");
                return null;
            }

            JsonObject? root;
            try { root = JsonNode.Parse(incomingJson) as JsonObject; }
            catch (Exception ex)
            {
                _log?.Invoke($"Bridge dispatcher: JSON parse failed: {ex.Message}");
                return null;
            }
            if (root is null)
            {
                _log?.Invoke("Bridge dispatcher: root is not a JSON object");
                return null;
            }

            string? type;
            try { type = root["type"]?.GetValue<string>(); }
            catch
            {
                _log?.Invoke("Bridge dispatcher: type field is not a string");
                return null;
            }
            // Non-invoke messages (e.g. event-only payloads from page scripts)
            // are silently ignored without a log entry — they may be intended
            // for a future event channel, not a bridge protocol violation.
            if (type != "invoke") return null;

            string? requestId;
            try { requestId = root["requestId"]?.GetValue<string>(); }
            catch
            {
                _log?.Invoke("Bridge dispatcher: invoke message has non-string requestId");
                return null;
            }
            if (string.IsNullOrEmpty(requestId))
            {
                _log?.Invoke("Bridge dispatcher: invoke message missing requestId");
                return null;
            }

            string? method;
            try { method = root["method"]?.GetValue<string>(); }
            catch { return BuildError(requestId!, "invalid request"); }
            if (string.IsNullOrWhiteSpace(method))
                return BuildError(requestId!, "invalid request");

            if (!_handlers.TryGetValue(method, out var handler))
                return BuildError(requestId!, "unknown method");

            var args = root["args"];

            JsonNode? result;
            try
            {
                result = await handler(args);
            }
            catch (Exception ex)
            {
                _log?.Invoke($"Bridge handler '{method}' threw: {ex}");
                return BuildError(requestId!, "handler failed");
            }

            return BuildSuccess(requestId!, result);
        }

        private static string BuildSuccess(string requestId, JsonNode? result)
        {
            var resp = new JsonObject
            {
                ["type"] = "response",
                ["requestId"] = requestId,
                ["ok"] = true,
                ["result"] = result?.DeepClone(),
            };
            return resp.ToJsonString();
        }

        private static string BuildError(string requestId, string error)
        {
            var resp = new JsonObject
            {
                ["type"] = "response",
                ["requestId"] = requestId,
                ["ok"] = false,
                ["error"] = error,
            };
            return resp.ToJsonString();
        }
    }
}
