using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.UI.Chat
{
    public sealed class ConfigurationBegin
    {
        public string OperationId { get; }
        public string Operation { get; }
        public JsonElement Input { get; private set; }
        public ConfigurationBegin(string operation, object input, string? operationId = null)
        {
            Operation = operation;
            OperationId = operationId ?? Guid.NewGuid().ToString("N");
            using var document = JsonDocument.Parse(JsonSerializer.Serialize(input));
            Input = document.RootElement.Clone();
        }
        internal object Wire() => new { v = 1, type = "begin", operationId = OperationId, operation = Operation, input = Input };
        internal void Clear() => Input = default;
    }

    public sealed class ConfigurationResult
    {
        internal ConfigurationResult(JsonElement record) => Record = record.Clone();
        internal JsonElement Record { get; }
        public string Outcome => Record.GetProperty("outcome").GetString()!;
        public string Persistence => Record.GetProperty("persistence").GetString()!;
        public string Code => Record.GetProperty("code").GetString()!;
        public JsonElement? Data => Record.TryGetProperty("data", out var data) ? data : (JsonElement?)null;
    }

    public sealed class ConfigurationEvent
    {
        internal ConfigurationEvent(JsonElement record, ConfigurationResult? result = null) { Record = record.Clone(); Result = result; }
        public JsonElement Record { get; }
        public string Type => Record.GetProperty("type").GetString()!;
        public ConfigurationResult? Result { get; }
    }

    public sealed class ConfigurationSettlement
    {
        public ConfigurationResult? Result { get; internal set; }
        public int? ExitCode { get; internal set; }
        public string Cleanup { get; internal set; } = "unconfirmed";
        public string? FailureCode { get; internal set; }
        public string? DeliveryFailure { get; internal set; }
        public bool Successful => Result?.Outcome == "completed" && Result.Code == "ok" && Cleanup == "exited" && ExitCode == 0 && FailureCode == null && DeliveryFailure == null;
    }

    // Closed configuration-v1 shapes only. Provider semantics remain in Prime.
    internal static class ConfigurationJson
    {
        internal const int InputLimit = 256 * 1024, EventLimit = 2 * 1024 * 1024, TotalLimit = 4 * 1024 * 1024;
        internal static readonly string[] Operations = { "status", "models", "oauth.connect", "oauth.disconnect", "apiKey.set", "apiKey.remove", "endpoint.read", "endpoint.save", "defaults.save" };
        private static readonly UTF8Encoding Utf8 = new(false, true);
        internal static void Need(bool condition) { if (!condition) throw new InvalidDataException("Invalid configuration response."); }
        internal static bool ReadOnly(string op) => op == "status" || op == "models" || op == "endpoint.read";
        internal static string Text(JsonElement v, int max = 256, bool empty = false)
        {
            Need(v.ValueKind == JsonValueKind.String);
            var s = v.GetString()!;
            Need((empty || s.Length > 0) && !s.Contains('\0') && Utf8.GetByteCount(s) <= max);
            return s;
        }
        internal static void Shape(JsonElement v, string required, string optional = "")
        {
            Need(v.ValueKind == JsonValueKind.Object);
            var keys = new HashSet<string>(StringComparer.Ordinal);
            var allowed = (required + " " + optional).Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
            foreach (var p in v.EnumerateObject()) Need(keys.Add(p.Name) && allowed.Contains(p.Name));
            foreach (var key in required.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries)) Need(keys.Contains(key));
        }
        internal static void Array(JsonElement v, int max) => Need(v.ValueKind == JsonValueKind.Array && v.GetArrayLength() <= max);
        private static void Bool(JsonElement v) => Need(v.ValueKind == JsonValueKind.True || v.ValueKind == JsonValueKind.False);
        private static void Strings(JsonElement v, int max) { Array(v, max); var seen = new HashSet<string>(); foreach (var i in v.EnumerateArray()) Need(seen.Add(Text(i))); }
        private static void Unicode(JsonElement v)
        {
            if (v.ValueKind == JsonValueKind.String) Text(v, EventLimit + 1024, true);
            if (v.ValueKind == JsonValueKind.Object)
            {
                var keys = new HashSet<string>();
                foreach (var p in v.EnumerateObject()) { Need(keys.Add(p.Name) && !p.Name.Contains('\0')); _ = Utf8.GetByteCount(p.Name); Unicode(p.Value); }
            }
            if (v.ValueKind == JsonValueKind.Array) foreach (var i in v.EnumerateArray()) Unicode(i);
        }
        internal static JsonElement Parse(byte[] raw, int limit)
        {
            Need(raw.Length <= limit);
            using var doc = JsonDocument.Parse(Utf8.GetString(raw));
            Unicode(doc.RootElement);
            return doc.RootElement.Clone();
        }
        internal static byte[] Encode(object value, int limit)
        {
            var bytes = Utf8.GetBytes(JsonSerializer.Serialize(value));
            _ = Parse(bytes, limit);
            return bytes;
        }
        private static void Envelope(JsonElement v, string id, string type, string required, string optional = "")
        {
            Shape(v, "v type operationId " + required, optional);
            Need(v.GetProperty("v").GetInt32() == 1 && Text(v.GetProperty("type")) == type && Text(v.GetProperty("operationId")) == id);
        }
        private static void Models(JsonElement value)
        {
            Array(value, 64);
            foreach (var model in value.EnumerateArray())
            {
                Shape(model, "id name reasoning input contextWindow maxTokens");
                Text(model.GetProperty("id")); Text(model.GetProperty("name"), 512); Bool(model.GetProperty("reasoning")); Inputs(model.GetProperty("input"));
                foreach (var k in new[] { "contextWindow", "maxTokens" }) { var n = model.GetProperty(k).GetInt64(); Need(n > 0 && n <= 9007199254740991L); }
            }
        }
        private static void Inputs(JsonElement v) { Strings(v, 2); Need(v.GetArrayLength() > 0); foreach (var i in v.EnumerateArray()) Need(new[] { "text", "image" }.Contains(i.GetString())); }
        private static void Compat(JsonElement v) { Shape(v, "", "supportsDeveloperRole supportsReasoningEffort"); foreach (var p in v.EnumerateObject()) Bool(p.Value); }
        private static void Endpoint(JsonElement v, bool reading)
        {
            Shape(v, reading ? "baseUrl api authHeader models headerNames compat" : "provider baseUrl api authHeader models headers", reading ? "" : "compat");
            Text(v.GetProperty("baseUrl"), 4096); Text(v.GetProperty("api")); Bool(v.GetProperty("authHeader")); Models(v.GetProperty("models"));
            if (v.TryGetProperty("compat", out var compat)) Compat(compat);
            if (reading) Strings(v.GetProperty("headerNames"), 32);
            else
            {
                var h = v.GetProperty("headers"); Shape(h, "action", "values");
                var action = Text(h.GetProperty("action")); Need(action == "keep" || action == "replace");
                Shape(h, action == "keep" ? "action" : "action values");
                if (action == "replace") { var values = h.GetProperty("values"); Need(values.ValueKind == JsonValueKind.Object && values.EnumerateObject().Count() <= 32); foreach (var p in values.EnumerateObject()) { Need(Utf8.GetByteCount(p.Name) <= 256 && p.Name.Length > 0); Text(p.Value, 8192, true); } }
            }
        }
        internal static byte[] Begin(ConfigurationBegin begin)
        {
            Need(begin.OperationId.Length == 32 && begin.OperationId.All(c => "0123456789abcdef".Contains(c)) && Operations.Contains(begin.Operation));
            var raw = Encode(begin.Wire(), InputLimit);
            var data = begin.Input;
            var fields = begin.Operation == "status" ? "" : "provider";
            if (begin.Operation == "apiKey.set") fields += " key";
            if (begin.Operation == "defaults.save") fields += " model reasoning";
            if (begin.Operation == "endpoint.save") fields += " baseUrl api authHeader headers models";
            Shape(data, fields, begin.Operation == "endpoint.save" ? "compat" : "");
            if (begin.Operation != "status") Text(data.GetProperty("provider"));
            if (begin.Operation == "apiKey.set") Text(data.GetProperty("key"), 16384);
            if (begin.Operation == "defaults.save") { Text(data.GetProperty("model")); Text(data.GetProperty("reasoning")); }
            if (begin.Operation == "endpoint.save") Endpoint(data, false);
            return raw;
        }
        internal static ConfigurationResult Result(JsonElement v, ConfigurationBegin begin)
        {
            Envelope(v, begin.OperationId, "result", "outcome persistence code", "data");
            var outcome = Text(v.GetProperty("outcome")); var persistence = Text(v.GetProperty("persistence"));
            Need(new[] { "completed", "cancelled", "failed" }.Contains(outcome));
            Need(new[] { "not_applicable", "unchanged", "saved", "unknown" }.Contains(persistence));
            Need(new[] { "ok", "invalid_request", "unsupported_configuration", "unsupported_choice", "authentication_failed", "storage_failed", "cancelled", "deadline_exceeded", "bounds_exceeded", "internal_error" }.Contains(Text(v.GetProperty("code"))));
            if (outcome != "completed" || !ReadOnly(begin.Operation)) Need(!v.TryGetProperty("data", out _));
            else
            {
                var d = v.GetProperty("data");
                if (begin.Operation == "status")
                {
                    Shape(d, "providers defaults apis"); Strings(d.GetProperty("apis"), 64);
                    var defaults = d.GetProperty("defaults"); Shape(defaults, "provider model reasoning"); foreach (var p in defaults.EnumerateObject()) if (p.Value.ValueKind != JsonValueKind.Null) Text(p.Value);
                    Array(d.GetProperty("providers"), 256);
                    foreach (var p in d.GetProperty("providers").EnumerateArray())
                    {
                        Shape(p, "id name methods credentialType configured route headerNames", "endpoint"); Text(p.GetProperty("id")); Text(p.GetProperty("name"), 512);
                        Strings(p.GetProperty("methods"), 9); foreach (var m in p.GetProperty("methods").EnumerateArray()) Need(Operations.Contains(m.GetString()));
                        Need(new[] { "none", "oauth", "api_key" }.Contains(Text(p.GetProperty("credentialType")))); Bool(p.GetProperty("configured"));
                        Need(new[] { "none", "dedicated", "local_no_account" }.Contains(Text(p.GetProperty("route")))); Strings(p.GetProperty("headerNames"), 32);
                        if (p.TryGetProperty("endpoint", out var url)) Text(url, 4096);
                    }
                }
                else
                {
                    Shape(d, begin.Operation == "models" ? "provider models access" : "provider entry");
                    Need(Text(d.GetProperty("provider")) == begin.Input.GetProperty("provider").GetString());
                    if (begin.Operation == "endpoint.read") { if (d.GetProperty("entry").ValueKind != JsonValueKind.Null) Endpoint(d.GetProperty("entry"), true); }
                    else
                    {
                        Need(Text(d.GetProperty("access")) == "unverified"); Array(d.GetProperty("models"), 512);
                        foreach (var m in d.GetProperty("models").EnumerateArray()) { Shape(m, "id name input reasoningLevels"); Text(m.GetProperty("id")); Text(m.GetProperty("name"), 512); Inputs(m.GetProperty("input")); Strings(m.GetProperty("reasoningLevels"), 64); }
                    }
                }
            }
            return new ConfigurationResult(v);
        }
        internal static ConfigurationEvent Event(JsonElement v, ConfigurationBegin begin)
        {
            var type = Text(v.GetProperty("type"));
            if (type == "result") return new ConfigurationEvent(v, Result(v, begin));
            if (type == "progress") { Envelope(v, begin.OperationId, type, "stage"); Need(new[] { "loading", "authorizing", "awaiting_input", "validating", "saving", "reading_back" }.Contains(Text(v.GetProperty("stage")))); }
            else if (type == "authorize")
            {
                Envelope(v, begin.OperationId, type, "url instructionCode", "instructions"); Need(begin.Operation == "oauth.connect" && Text(v.GetProperty("instructionCode")) == "open_browser");
                Need(Uri.TryCreate(Text(v.GetProperty("url"), 8192), UriKind.Absolute, out var url) && (url.Scheme == "https" || url.Scheme == "http") && url.UserInfo.Length == 0);
                if (v.TryGetProperty("instructions", out var instructions)) Text(instructions, 8192, true);
            }
            else
            {
                Need(type == "input" && begin.Operation == "oauth.connect"); Envelope(v, begin.OperationId, type, "requestId kind label secret", "choices");
                Need(v.GetProperty("requestId").GetInt64() > 0 && v.GetProperty("requestId").GetInt64() <= 9007199254740991L);
                var kind = Text(v.GetProperty("kind")); Need(new[] { "text", "code", "select" }.Contains(kind)); Text(v.GetProperty("label"), 512); Bool(v.GetProperty("secret"));
                if (kind == "select") { var choices = v.GetProperty("choices"); Array(choices, 32); Need(choices.GetArrayLength() > 0); var seen = new HashSet<string>(); foreach (var c in choices.EnumerateArray()) { Shape(c, "id label"); Need(seen.Add(Text(c.GetProperty("id")))); Text(c.GetProperty("label"), 512); } }
                else Need(!v.TryGetProperty("choices", out _));
            }
            return new ConfigurationEvent(v);
        }
        internal static bool Equal(JsonElement a, JsonElement b)
        {
            if (a.ValueKind != b.ValueKind) return false;
            if (a.ValueKind == JsonValueKind.Object) return a.EnumerateObject().Count() == b.EnumerateObject().Count() && a.EnumerateObject().All(p => b.TryGetProperty(p.Name, out var v) && Equal(p.Value, v));
            if (a.ValueKind == JsonValueKind.Array) return a.GetArrayLength() == b.GetArrayLength() && a.EnumerateArray().Zip(b.EnumerateArray(), Equal).All(x => x);
            return a.ValueKind == JsonValueKind.String ? a.GetString() == b.GetString() : a.GetRawText() == b.GetRawText();
        }
        internal static ConfigurationSettlement Settlement(JsonElement v, ConfigurationBegin begin, ConfigurationResult? earlier)
        {
            Shape(v, "type result exit_code cleanup failure_code"); Need(Text(v.GetProperty("type")) == "configuration_settled");
            var nested = v.GetProperty("result").ValueKind == JsonValueKind.Null ? null : Result(v.GetProperty("result"), begin);
            Need(earlier == null || (nested != null && Equal(earlier.Record, nested.Record)));
            var cleanup = Text(v.GetProperty("cleanup")); Need(cleanup == "exited" || cleanup == "unconfirmed");
            var code = v.GetProperty("exit_code"); int? exit = code.ValueKind == JsonValueKind.Null ? null : code.GetInt32();
            var failure = v.GetProperty("failure_code"); string? fail = failure.ValueKind == JsonValueKind.Null ? null : Text(failure);
            Need(fail == null || new[] { "cancelled", "deadline_exceeded", "bounds_exceeded", "protocol_error", "output_failed", "stderr_failed", "spawn_failed", "process_failed", "stdin_failed", "cleanup_failed", "cleanup_unconfirmed", "child_exit_failed", "missing_result", "invalid_request" }.Contains(fail));
            return new ConfigurationSettlement { Result = earlier ?? nested, Cleanup = cleanup, ExitCode = exit, FailureCode = fail };
        }
    }

    public sealed partial class AgentChatClient
    {
        private readonly object _configurationLock = new();
        private string? _configurationId;
        private Uri? _configurationUri;
        private ConfigurationEvent? _configurationInput;
        private bool _configurationCancelled;
        private bool _configurationTerminal;

        public async Task<ConfigurationSettlement> RunConfigurationAsync(ConfigurationBegin begin, Func<ConfigurationEvent, Task> onEvent, CancellationToken ct)
        {
            var result = new ConfigurationSettlement();
            using var lifetime = new CancellationTokenSource();
            var seconds = ConfigurationJson.ReadOnly(begin.Operation) ? 20 : begin.Operation == "oauth.connect" ? 600 : 30;
            lifetime.CancelAfter(TimeSpan.FromSeconds(seconds + 15));
            var clock = Stopwatch.StartNew();
            Task? cancellation = null;
            CancellationTokenRegistration registration = default;
            bool owns = false, terminal = false, admitted = false, deliver = true;
            double end = seconds + 15;
            void ShortenForCleanup()
            {
                end = Math.Min(end, clock.Elapsed.TotalSeconds + 15);
                lifetime.CancelAfter(TimeSpan.FromSeconds(Math.Max(0, end - clock.Elapsed.TotalSeconds)));
            }
            void CancelOwned()
            {
                lock (_configurationLock)
                {
                    ShortenForCleanup();
                    if (admitted && !_configurationTerminal)
                        cancellation ??= CancelConfigurationAsync(begin.OperationId, CancellationToken.None);
                }
            }
            try
            {
                var raw = ConfigurationJson.Begin(begin);
                ct.ThrowIfCancellationRequested();
                lock (_configurationLock) { ConfigurationJson.Need(_configurationId == null); _configurationId = begin.OperationId; _configurationCancelled = false; _configurationTerminal = false; owns = true; }
                registration = ct.Register(CancelOwned);
                var health = await GetHealthAsync(true, lifetime.Token).ConfigureAwait(false);
                if (!health.ConfigurationAvailable) { result.FailureCode = "configuration_unavailable"; return result; }
                var uri = health.BaseUri ?? await GetBaseUriAsync(false, lifetime.Token).ConfigureAwait(false);
                lock (_configurationLock) _configurationUri = uri;
                using var request = new HttpRequestMessage(HttpMethod.Post, Route(uri, "/agent/chat/configuration")) { Content = new ByteArrayContent(raw) };
                request.Content.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("application/json");
                using var response = await _client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, lifetime.Token).ConfigureAwait(false);
                request.Content.Dispose();
                if (!response.IsSuccessStatusCode) { result.FailureCode = response.StatusCode == System.Net.HttpStatusCode.Conflict ? "configuration_busy" : response.StatusCode == System.Net.HttpStatusCode.ServiceUnavailable ? "configuration_unavailable" : "configuration_refused"; return result; }
                lock (_configurationLock)
                {
                    admitted = true;
                    if (ct.IsCancellationRequested) CancelOwned();
                }
                using var stream = await response.Content.ReadAsStreamAsync().ConfigureAwait(false);
                using var line = new MemoryStream(); var buffer = new byte[4096]; int total = 0, count = 0, eventBytes = 0, eventCount = 0, inputs = 0; long lastInput = 0;
                int read;
                while ((read = await stream.ReadAsync(buffer, 0, buffer.Length, lifetime.Token).ConfigureAwait(false)) > 0)
                {
                    total += read; ConfigurationJson.Need(total <= ConfigurationJson.TotalLimit + ConfigurationJson.EventLimit + 1024);
                    for (int i = 0; i < read; i++)
                    {
                        if (buffer[i] != 10) { line.WriteByte(buffer[i]); ConfigurationJson.Need(line.Length < ConfigurationJson.EventLimit + 1024); continue; }
                        ConfigurationJson.Need(!terminal && ++count <= 257);
                        var row = ConfigurationJson.Parse(line.ToArray(), ConfigurationJson.EventLimit + 1024);
                        if (row.GetProperty("type").GetString() == "configuration_settled")
                        {
                            var settled = ConfigurationJson.Settlement(row, begin, result.Result);
                            settled.DeliveryFailure = result.DeliveryFailure;
                            result = settled; terminal = true;
                            lock (_configurationLock) { _configurationInput = null; _configurationTerminal = true; ShortenForCleanup(); }
                        }
                        else
                        {
                            eventBytes += (int)line.Length + 1; ConfigurationJson.Need(line.Length + 1 <= ConfigurationJson.EventLimit && eventBytes <= ConfigurationJson.TotalLimit && ++eventCount <= 256 && result.Result == null);
                            var evt = ConfigurationJson.Event(row, begin);
                            if (evt.Type == "input")
                            {
                                lock (_configurationLock) { var id = evt.Record.GetProperty("requestId").GetInt64(); ConfigurationJson.Need(_configurationInput == null && id > lastInput && ++inputs <= 16); lastInput = id; if (!_configurationCancelled) _configurationInput = evt; }
                            }
                            if (evt.Result != null) { result.Result = evt.Result; lock (_configurationLock) { _configurationInput = null; _configurationTerminal = true; ShortenForCleanup(); } }
                            if (deliver)
                            {
                                try
                                {
                                    var delivery = onEvent(evt);
                                    if (await Task.WhenAny(delivery, Task.Delay(Timeout.Infinite, lifetime.Token)).ConfigureAwait(false) != delivery)
                                    {
                                        _ = delivery.ContinueWith(t => { _ = t.Exception; }, TaskContinuationOptions.OnlyOnFaulted);
                                        throw new OperationCanceledException();
                                    }
                                    await delivery.ConfigureAwait(false);
                                }
                                catch
                                {
                                    deliver = false;
                                    result.DeliveryFailure = "configuration_delivery_failed";
                                    CancelOwned();
                                }
                            }
                        }
                        line.SetLength(0);
                    }
                }
                ConfigurationJson.Need(terminal && line.Length == 0);
            }
            catch (Exception)
            {
                result.DeliveryFailure ??= ct.IsCancellationRequested ? "cancelled" : "configuration_stream_failed";
                if (owns && !terminal && result.Result == null)
                    CancelOwned();
            }
            finally
            {
                registration.Dispose();
                if (cancellation != null)
                {
                    try
                    {
                        if (await Task.WhenAny(cancellation, Task.Delay(TimeSpan.FromSeconds(Math.Max(0, end - clock.Elapsed.TotalSeconds)))).ConfigureAwait(false) != cancellation)
                        {
                            _ = cancellation.ContinueWith(t => { _ = t.Exception; }, TaskContinuationOptions.OnlyOnFaulted);
                            throw new OperationCanceledException();
                        }
                        await cancellation.ConfigureAwait(false);
                    }
                    catch { result.DeliveryFailure ??= "cancellation_unconfirmed"; }
                }
                if (owns) lock (_configurationLock) { _configurationId = null; _configurationUri = null; _configurationInput = null; _configurationCancelled = false; }
                begin.Clear();
            }
            return result;
        }

        public async Task ReplyConfigurationAsync(string operationId, long requestId, string value, CancellationToken ct = default)
        {
            Uri uri;
            try
            {
                lock (_configurationLock)
                {
                    ConfigurationJson.Need(_configurationId == operationId && !_configurationCancelled && _configurationUri != null && _configurationInput != null && _configurationInput.Record.GetProperty("requestId").GetInt64() == requestId);
                    var pending = _configurationInput!;
                    if (pending.Record.GetProperty("kind").GetString() == "select") ConfigurationJson.Need(pending.Record.GetProperty("choices").EnumerateArray().Any(c => c.GetProperty("id").GetString() == value));
                    ConfigurationJson.Need(new UTF8Encoding(false, true).GetByteCount(value) <= 16384 && !value.Contains('\0'));
                    uri = _configurationUri!; _configurationInput = null;
                }
                await ConfigurationControlAsync(uri, "reply", new { v = 1, type = "reply", operationId, requestId, value }, ct).ConfigureAwait(false);
            }
            catch { throw new InvalidOperationException("Configuration reply was not accepted."); }
        }

        public async Task CancelConfigurationAsync(string operationId, CancellationToken ct = default)
        {
            Uri? uri;
            lock (_configurationLock) { if (_configurationId != operationId || _configurationCancelled || _configurationTerminal) return; _configurationCancelled = true; _configurationInput = null; uri = _configurationUri; }
            if (uri != null) await ConfigurationControlAsync(uri, "cancel", new { v = 1, type = "cancel", operationId }, ct).ConfigureAwait(false);
        }

        private async Task ConfigurationControlAsync(Uri uri, string action, object body, CancellationToken ct)
        {
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
            timeout.CancelAfter(TimeSpan.FromSeconds(15));
            using var request = new HttpRequestMessage(HttpMethod.Post, Route(uri, "/agent/chat/configuration/" + action)) { Content = new ByteArrayContent(ConfigurationJson.Encode(body, ConfigurationJson.InputLimit)) };
            request.Content.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("application/json");
            try { using var response = await _client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, timeout.Token).ConfigureAwait(false); ConfigurationJson.Need(response.StatusCode == System.Net.HttpStatusCode.NoContent); }
            catch { throw new InvalidOperationException("Configuration control was not accepted."); }
        }
    }
}
