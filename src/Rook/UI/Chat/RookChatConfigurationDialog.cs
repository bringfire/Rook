using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Eto.Drawing;
using Eto.Forms;

namespace Rook.UI.Chat
{
    internal sealed class RookChatConfigurationDialog : Dialog
    {
        private readonly AgentChatClient _client;
        private readonly Action<Action> _post;
        private readonly Action<string> _openBrowser;
        private readonly Dictionary<string, JsonElement> _providers = new();
        private readonly Dictionary<string, JsonElement> _models = new();
        private readonly List<JsonElement> _endpointModels = new();
        private readonly Dictionary<string, string> _headers = new();
        private readonly Dictionary<string, Button> _actions = new();
        private readonly Panel _editor;
        private readonly DropDown _provider = new();
        internal readonly TextBox ProviderId = new();
        internal readonly PasswordBox ApiKey = new();
        internal readonly DropDown Model = new(), Reasoning = new(), Api = new();
        internal readonly TextBox EndpointUrl = new();
        internal readonly CheckBox AuthHeader = new() { Text = "Authorization header", Checked = true };
        internal readonly CheckBox DeveloperRole = new() { Text = "Developer role", ThreeState = true };
        internal readonly CheckBox ReasoningEffort = new() { Text = "Reasoning effort", ThreeState = true };
        internal readonly CheckBox ReplaceHeaders = new() { Text = "Replace saved headers", Checked = false };
        internal readonly TextBox HeaderName = new();
        internal readonly PasswordBox HeaderValue = new();
        private readonly ListBox _headerNames = new() { Height = 64 };
        private readonly ListBox _modelList = new() { Height = 70 };
        internal readonly TextBox EndpointModelId = new(), EndpointModelName = new();
        internal readonly CheckBox ModelReasoning = new() { Text = "Reasoning", Checked = false };
        internal readonly CheckBox ImageInput = new() { Text = "Image input", Checked = false };
        internal readonly NumericStepper ContextWindow = new() { MinValue = 1, MaxValue = 9007199254740991, DecimalPlaces = 0, Value = 32768 };
        internal readonly NumericStepper MaxTokens = new() { MinValue = 1, MaxValue = 9007199254740991, DecimalPlaces = 0, Value = 4096 };
        internal readonly TextArea Instructions = new() { ReadOnly = true, Wrap = true, Height = 64 };
        internal readonly Label Status = new() { Text = "Loading configuration...", Wrap = WrapMode.Character };
        internal readonly Label Persistence = new() { Text = "No change requested.", Wrap = WrapMode.Character };
        internal readonly Label Cleanup = new() { Text = "No configuration operation.", Wrap = WrapMode.Character };
        internal readonly Label SavedDefaults = new() { Text = "Saved defaults: unknown", Wrap = WrapMode.Character };
        internal readonly Label AccountRoute = new() { Text = "Account route: unknown", Wrap = WrapMode.Character };
        private readonly TextArea _inputLabel = new() { ReadOnly = true, Wrap = true, Height = 40, Visible = false };
        internal readonly PasswordBox SecretReply = new();
        internal readonly TextBox TextReply = new();
        internal readonly DropDown ChoiceReply = new();
        private readonly Button _reply = new() { Text = "Continue", Enabled = false };
        private readonly Button _browser = new() { Text = "Open authorization page", Enabled = false };
        private readonly Button _cancel = new() { Text = "Cancel operation", Enabled = false };
        private CancellationTokenSource? _operationCancellation;
        private ConfigurationBegin? _begin;
        private ConfigurationEvent? _input;
        private string? _authorizationUrl;
        private string? _requestedDefaults;
        private bool _disposed, _cancelRequested, _available;
        internal bool Busy { get; private set; }
        internal ConfigurationResult? KnownResult { get; private set; }
        internal ConfigurationSettlement? LastSettlement { get; private set; }
        internal Task PendingOperation { get; private set; } = Task.CompletedTask;
        private bool _cleanupConfirmed = true;
        private bool _canAttemptConfiguration = true;
        internal bool CanAttemptConfiguration => !Busy && _canAttemptConfiguration;
        internal bool CanRefreshGuidance => !Busy && _cleanupConfirmed;

        internal RookChatConfigurationDialog(AgentChatClient client, Action<Action>? post = null, Action<string>? openBrowser = null)
        {
            _client = client;
            _post = post ?? (action => Application.Instance.AsyncInvoke(action));
            _openBrowser = openBrowser ?? (url => Process.Start(new ProcessStartInfo(url) { UseShellExecute = true }));
            Title = "RookChat Settings";
            ClientSize = new Size(650, 720);
            MinimumSize = new Size(480, 420);
            Padding = new Padding(12);
            _provider.SelectedValueChanged += (_, _) => { if (_provider.SelectedKey != null) ProviderId.Text = _provider.SelectedKey; };
            ProviderId.TextChanged += (_, _) => ResetProviderPresentation();
            Model.SelectedValueChanged += (_, _) => UpdateReasoning();
            _modelList.SelectedValueChanged += (_, _) => LoadEndpointModel();
            ReplaceHeaders.CheckedChanged += (_, _) => { if (ReplaceHeaders.Checked != true) { _headers.Clear(); HeaderValue.Text = ""; _headerNames.Items.Clear(); } };
            var account = Rows(
                new TableRow("Provider", _provider), new TableRow("Provider ID", ProviderId),
                new TableRow(AccountRoute),
                new TableRow(new Label { Text = "Account and endpoint changes can affect open conversations.\nOther processes may still hold earlier values." }),
                new TableRow(ActionButton("Connect account", "oauth.connect"), ActionButton("Disconnect account", "oauth.disconnect")),
                new TableRow("API key", ApiKey),
                new TableRow(ActionButton("Save API key", "apiKey.set"), ActionButton("Remove API key", "apiKey.remove")));
            var defaults = Rows(new TableRow(SavedDefaults),
                new TableRow(ActionButton("Load models", "models")),
                new TableRow("Model", Model), new TableRow("Reasoning", Reasoning),
                new TableRow(ActionButton("Save defaults for new conversations", "defaults.save")),
                new TableRow(new Label { Text = "Requested initial choices are set when opening a conversation.\nEffective conversation settings: unknown." }));
            var addModel = LocalButton("Add / update model", AddEndpointModel);
            var removeModel = LocalButton("Remove model", () =>
            {
                if (_modelList.SelectedIndex >= 0) _endpointModels.RemoveAt(_modelList.SelectedIndex);
                RefreshEndpointModels();
            });
            var endpoint = Rows(new TableRow(ActionButton("Read saved endpoint", "endpoint.read")),
                new TableRow("Endpoint URL", EndpointUrl), new TableRow("API", Api), new TableRow(AuthHeader),
                new TableRow(_modelList), new TableRow("Model ID", EndpointModelId), new TableRow("Model name", EndpointModelName),
                new TableRow(ModelReasoning, ImageInput), new TableRow("Context window", ContextWindow), new TableRow("Maximum output tokens", MaxTokens),
                new TableRow(addModel, removeModel), new TableRow(DeveloperRole, ReasoningEffort),
                new TableRow(ReplaceHeaders), new TableRow(_headerNames),
                new TableRow("Header name", HeaderName), new TableRow("Header value", HeaderValue),
                new TableRow(LocalButton("Add / update header", AddHeader), LocalButton("Remove header", () =>
                {
                    if (_headerNames.SelectedKey != null) _headers.Remove(_headerNames.SelectedKey);
                    RefreshHeaderNames();
                })), new TableRow(ActionButton("Save endpoint", "endpoint.save")));
            _editor = new Panel { Content = new TabControl { Pages =
            {
                new TabPage { Text = "Account", Content = new Scrollable { Content = account } },
                new TabPage { Text = "Defaults", Content = new Scrollable { Content = defaults } },
                new TabPage { Text = "Local / custom endpoint", Content = new Scrollable { Content = endpoint } },
            } } };
            _browser.Click += (_, _) => OpenAuthorization();
            _reply.Click += async (_, _) => await SubmitReplyAsync();
            _cancel.Click += (_, _) => CancelCurrent();
            var close = new Button { Text = "Close" };
            close.Click += (_, _) => Close();
            Closing += (_, args) => { if (Busy) { args.Cancel = true; CancelCurrent(); } else ClearSensitive(); };
            Content = Rows(new TableRow(ActionButton("Refresh status", "status")),
                new TableRow(_editor) { ScaleHeight = true },
                new TableRow(Status), new TableRow(Persistence), new TableRow(Cleanup),
                new TableRow(Instructions), new TableRow(_browser), new TableRow(_inputLabel),
                new TableRow(SecretReply, TextReply, ChoiceReply, _reply), new TableRow(_cancel, null, close));
            ClearInteraction();
            UpdateEnabled();
        }

        private static TableLayout Rows(params TableRow[] rows)
        {
            var layout = new TableLayout { Spacing = new Size(6, 6), Padding = new Padding(4) };
            foreach (var row in rows) layout.Rows.Add(row);
            return layout;
        }
        private Button ActionButton(string title, string operation)
        {
            var button = new Button { Text = title };
            button.Click += async (_, _) => await RunActionAsync(operation);
            _actions.Add(operation, button);
            return button;
        }
        private Button LocalButton(string title, Action action)
        {
            var button = new Button { Text = title };
            button.Click += (_, _) => { try { action(); } catch { Status.Text = "Check the configuration fields."; } };
            return button;
        }
        private Task PresentAsync(Action action)
        {
            if (_disposed) return Task.CompletedTask;
            var done = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            try { _post(() => { try { if (!_disposed) action(); done.TrySetResult(true); } catch { done.TrySetException(new InvalidOperationException("Configuration presentation failed.")); } }); }
            catch { done.TrySetException(new InvalidOperationException("Configuration presentation failed.")); }
            return done.Task;
        }

        internal Task InitializeAsync() => RunActionAsync("status");
        internal Task RunActionAsync(string operation)
        {
            if (_disposed || !CanAttemptConfiguration) return Task.CompletedTask;
            try
            {
                if (operation != "status" && (!_available || !Supports(operation)))
                {
                    Status.Text = "This configuration action is unavailable. Refresh status after adding an endpoint.";
                    ClearSensitive(); return Task.CompletedTask;
                }
                var begin = BuildOperation(operation);
                _cleanupConfirmed = false;
                _canAttemptConfiguration = false;
                Busy = true; _cancelRequested = false; _begin = begin;
                _operationCancellation = new CancellationTokenSource();
                LastSettlement = null;
                _requestedDefaults = operation == "defaults.save" ? "Saved defaults: " + ProviderId.Text + "/" + Model.SelectedKey + "; reasoning: " + Reasoning.SelectedKey : null;
                ClearSensitive();
                Status.Text = "Preparing configuration...";
                Persistence.Text = "Awaiting result; no rollback is implied by cancellation.";
                Cleanup.Text = "Configuration process: pending";
                UpdateEnabled();
                PendingOperation = RunAsync(begin, _operationCancellation.Token);
                return PendingOperation;
            }
            catch { Status.Text = "Check the configuration fields."; ClearSensitive(); return Task.CompletedTask; }
        }

        private async Task RunAsync(ConfigurationBegin begin, CancellationToken token)
        {
            try
            {
                var settlement = await _client.RunConfigurationAsync(begin, evt =>
                {
                    if (evt.Result != null) KnownResult = evt.Result;
                    return PresentAsync(() => HandleEvent(evt));
                }, token).ConfigureAwait(false);
                LastSettlement = settlement;
                _cleanupConfirmed = settlement.Cleanup == "exited";
                _canAttemptConfiguration = _cleanupConfirmed || settlement.ConfirmedNotAdmitted;
                if (settlement.Result != null) KnownResult = settlement.Result;
                await PresentAsync(() =>
                {
                    if (settlement.FailureCode == "configuration_unavailable" || settlement.FailureCode == "configuration_refused") _available = false;
                    if (settlement.Result != null) ShowResult(begin.Operation, settlement.Result);
                    else Persistence.Text = "Outcome unknown. Status may not identify a replaced key or account.";
                    Cleanup.Text = "Configuration process: " + settlement.Cleanup + "; exit: " + (settlement.ExitCode?.ToString() ?? "unknown");
                    Status.Text = settlement.Successful ? "Configuration operation completed." :
                        settlement.FailureCode == "configuration_unavailable" ? "Configuration unavailable for this runtime. Existing conversations remain available." :
                        "Configuration incomplete: " + (settlement.DeliveryFailure ?? settlement.FailureCode ?? settlement.Result?.Code ?? "unknown");
                    if (settlement.FailureCode == "configuration_storage_refused")
                    {
                        Status.Text = "Configuration storage protection could not be verified. Existing storage preserved.";
                        Persistence.Text = "Operation not started; no configuration change was attempted.";
                        Cleanup.Text = "Configuration process: not started.";
                    }
                    else if (settlement.ConfirmedNotAdmitted)
                    {
                        if (settlement.FailureCode != "configuration_unavailable")
                            Status.Text = "Configuration did not start. You can try again.";
                        Persistence.Text = "No configuration change was attempted by this operation.";
                        Cleanup.Text = "Configuration process: not started.";
                    }
                    ClearSensitive();
                }).ConfigureAwait(false);
            }
            catch
            {
                // The owner may already have reported persistence; never replace it with a save-failure claim.
                try { await PresentAsync(() => Status.Text = "Configuration presentation interrupted; the saved outcome, if received, is retained.").ConfigureAwait(false); }
                catch { }
            }
            finally
            {
                var cancellation = _operationCancellation;
                try
                {
                    await PresentAsync(() => { Busy = false; _begin = null; _operationCancellation = null; UpdateEnabled(); }).ConfigureAwait(false);
                }
                catch { }
                finally
                {
                    // Disposal skips presentation, but must still retire the dialog's input state.
                    if (ReferenceEquals(_begin, begin)) { Busy = false; _begin = null; _operationCancellation = null; }
                    cancellation?.Dispose();
                }
            }
        }

        internal ConfigurationBegin BuildOperation(string operation)
        {
            var provider = ProviderId.Text ?? "";
            object input;
            switch (operation)
            {
                case "status": input = new { }; break;
                case "apiKey.set": input = new { provider, key = ApiKey.Text }; break;
                case "defaults.save": input = new { provider, model = Model.SelectedKey, reasoning = Reasoning.SelectedKey }; break;
                case "endpoint.save":
                    var compat = new Dictionary<string, bool>();
                    if (DeveloperRole.Checked.HasValue) compat["supportsDeveloperRole"] = DeveloperRole.Checked.Value;
                    if (ReasoningEffort.Checked.HasValue) compat["supportsReasoningEffort"] = ReasoningEffort.Checked.Value;
                    input = new { provider, baseUrl = EndpointUrl.Text, api = Api.SelectedKey, authHeader = AuthHeader.Checked == true,
                        headers = ReplaceHeaders.Checked == true ? (object)new { action = "replace", values = new Dictionary<string, string>(_headers) } : new { action = "keep" },
                        models = _endpointModels.ToArray(), compat };
                    break;
                default: input = new { provider }; break;
            }
            var begin = new ConfigurationBegin(operation, input);
            _ = ConfigurationJson.Begin(begin);
            return begin;
        }

        private void HandleEvent(ConfigurationEvent evt)
        {
            if (_begin?.OperationId != evt.Record.GetProperty("operationId").GetString()) return;
            if (evt.Result != null) { ShowResult(_begin.Operation, evt.Result); ClearInteraction(); return; }
            if (_cancelRequested) return;
            if (evt.Type == "progress") Status.Text = "Configuration: " + evt.Record.GetProperty("stage").GetString();
            else if (evt.Type == "authorize")
            {
                _authorizationUrl = evt.Record.GetProperty("url").GetString();
                Instructions.Text = evt.Record.TryGetProperty("instructions", out var text) ? text.GetString() : "";
                _browser.Enabled = true;
            }
            else if (evt.Type == "input")
            {
                ClearReply(); _input = evt;
                var record = evt.Record;
                _inputLabel.Text = record.GetProperty("label").GetString();
                _inputLabel.Visible = true;
                var select = record.GetProperty("kind").GetString() == "select";
                ChoiceReply.Visible = select;
                SecretReply.Visible = !select && record.GetProperty("secret").GetBoolean();
                TextReply.Visible = !select && !SecretReply.Visible;
                if (select) { foreach (var item in record.GetProperty("choices").EnumerateArray()) ChoiceReply.Items.Add(new ListItem { Key = item.GetProperty("id").GetString(), Text = item.GetProperty("label").GetString() }); ChoiceReply.SelectedIndex = 0; }
                _reply.Enabled = true;
            }
        }

        internal void OpenAuthorization()
        {
            if (_disposed || _cancelRequested || _begin?.Operation != "oauth.connect" || _authorizationUrl == null) return;
            try { _openBrowser(_authorizationUrl); }
            catch { Status.Text = "Could not open the authorization page."; }
        }
        internal async Task SubmitReplyAsync()
        {
            if (_disposed || _cancelRequested || _begin == null || _input == null) return;
            var operationId = _begin.OperationId;
            var requestId = _input.Record.GetProperty("requestId").GetInt64();
            var value = ChoiceReply.Visible ? ChoiceReply.SelectedKey : SecretReply.Visible ? SecretReply.Text : TextReply.Text;
            ClearReply();
            try { await _client.ReplyConfigurationAsync(operationId, requestId, value ?? "", CancellationToken.None).ConfigureAwait(false); }
            catch { await PresentAsync(() => Status.Text = "Configuration reply was not accepted.").ConfigureAwait(false); }
        }
        internal void CancelCurrent()
        {
            if (_disposed || !Busy || _cancelRequested) return;
            _cancelRequested = true; ClearSensitive(); _cancel.Enabled = false;
            Status.Text = "Cancelling; awaiting result and cleanup.";
            _operationCancellation?.Cancel();
        }
        private void ShowResult(string operation, ConfigurationResult result)
        {
            Persistence.Text = result.Persistence == "saved" ? "Configuration saved." : result.Persistence == "unknown" ?
                "Persistence unknown. Status cannot prove an indistinguishable replacement." : "Persistence: " + result.Persistence;
            Cleanup.Text = "Awaiting configuration-process cleanup.";
            if (operation == "defaults.save" && result.Persistence == "saved" && _requestedDefaults != null) SavedDefaults.Text = _requestedDefaults;
            if (result.Outcome != "completed" || !result.Data.HasValue) return;
            var data = result.Data.Value;
            if (operation == "status")
            {
                _available = true; _providers.Clear(); _provider.Items.Clear();
                foreach (var p in data.GetProperty("providers").EnumerateArray()) { var id = p.GetProperty("id").GetString()!; _providers[id] = p.Clone(); _provider.Items.Add(new ListItem { Key = id, Text = p.GetProperty("name").GetString() }); }
                Api.Items.Clear(); foreach (var api in data.GetProperty("apis").EnumerateArray()) Api.Items.Add(new ListItem { Key = api.GetString(), Text = api.GetString() });
                if (Api.Items.Count > 0) Api.SelectedIndex = 0;
                var d = data.GetProperty("defaults");
                SavedDefaults.Text = "Saved defaults: " + (d.GetProperty("provider").GetString() ?? "unset") + "/" + (d.GetProperty("model").GetString() ?? "unset") + "; reasoning: " + (d.GetProperty("reasoning").GetString() ?? "unset");
                if (string.IsNullOrEmpty(ProviderId.Text)) ProviderId.Text = d.GetProperty("provider").GetString() ?? "";
                ResetProviderPresentation();
            }
            else if (operation == "models")
            {
                _models.Clear(); Model.Items.Clear();
                foreach (var m in data.GetProperty("models").EnumerateArray()) { var id = m.GetProperty("id").GetString()!; _models[id] = m.Clone(); Model.Items.Add(new ListItem { Key = id, Text = m.GetProperty("name").GetString() }); }
                if (Model.Items.Count > 0) Model.SelectedIndex = 0;
                UpdateReasoning();
            }
            else if (operation == "endpoint.read")
            {
                ClearEndpoint();
                var entry = data.GetProperty("entry");
                if (entry.ValueKind == JsonValueKind.Null) return;
                EndpointUrl.Text = entry.GetProperty("baseUrl").GetString(); Api.SelectedKey = entry.GetProperty("api").GetString(); AuthHeader.Checked = entry.GetProperty("authHeader").GetBoolean();
                foreach (var m in entry.GetProperty("models").EnumerateArray()) _endpointModels.Add(m.Clone());
                foreach (var name in entry.GetProperty("headerNames").EnumerateArray()) _headerNames.Items.Add(new ListItem { Key = name.GetString(), Text = name.GetString() });
                var c = entry.GetProperty("compat");
                DeveloperRole.Checked = c.TryGetProperty("supportsDeveloperRole", out var dr) ? dr.GetBoolean() : (bool?)null;
                ReasoningEffort.Checked = c.TryGetProperty("supportsReasoningEffort", out var re) ? re.GetBoolean() : (bool?)null;
                RefreshEndpointModels();
            }
        }
        private void ResetProviderPresentation()
        {
            ClearSensitive();
            _models.Clear(); Model.Items.Clear(); Reasoning.Items.Clear(); ClearEndpoint();
            AccountRoute.Text = _providers.TryGetValue(ProviderId.Text ?? "", out var p)
                ? "Account route: " + p.GetProperty("route").GetString() + "; credential: " + p.GetProperty("credentialType").GetString() + "; access unverified"
                : "Custom provider; access unverified. Ollama requires no cloud account.";
            UpdateEnabled();
        }
        private void UpdateReasoning()
        {
            Reasoning.Items.Clear();
            if (Model.SelectedKey != null && _models.TryGetValue(Model.SelectedKey, out var m))
                foreach (var value in m.GetProperty("reasoningLevels").EnumerateArray()) Reasoning.Items.Add(new ListItem { Key = value.GetString(), Text = value.GetString() });
            if (Reasoning.Items.Count > 0) Reasoning.SelectedIndex = 0;
        }
        private void UpdateEnabled()
        {
            if (_disposed) return;
            if (_editor != null) _editor.Enabled = _available && CanAttemptConfiguration;
            foreach (var pair in _actions)
            {
                pair.Value.Enabled = CanAttemptConfiguration && (pair.Key == "status" || _available && Supports(pair.Key));
            }
            _cancel.Enabled = Busy && !_cancelRequested;
        }
        private bool Supports(string operation)
            => _providers.TryGetValue(ProviderId.Text ?? "", out var p)
                ? p.GetProperty("methods").EnumerateArray().Any(m => m.GetString() == operation)
                : operation == "endpoint.read" || operation == "endpoint.save";
        internal void AddEndpointModel()
        {
            var id = EndpointModelId.Text ?? "";
            var raw = ConfigurationJson.Encode(new { id, name = EndpointModelName.Text, reasoning = ModelReasoning.Checked == true,
                input = ImageInput.Checked == true ? new[] { "text", "image" } : new[] { "text" }, contextWindow = (long)ContextWindow.Value, maxTokens = (long)MaxTokens.Value }, ConfigurationJson.InputLimit);
            var model = ConfigurationJson.Parse(raw, ConfigurationJson.InputLimit);
            var index = _endpointModels.FindIndex(m => m.GetProperty("id").GetString() == id);
            if (index < 0) { ConfigurationJson.Need(_endpointModels.Count < 64); _endpointModels.Add(model); } else _endpointModels[index] = model;
            RefreshEndpointModels();
        }
        private void RefreshEndpointModels()
        {
            _modelList.Items.Clear(); foreach (var m in _endpointModels) _modelList.Items.Add(new ListItem { Key = m.GetProperty("id").GetString(), Text = m.GetProperty("name").GetString() });
        }
        private void LoadEndpointModel()
        {
            if (_modelList.SelectedIndex < 0) return;
            var m = _endpointModels[_modelList.SelectedIndex];
            EndpointModelId.Text = m.GetProperty("id").GetString(); EndpointModelName.Text = m.GetProperty("name").GetString();
            ModelReasoning.Checked = m.GetProperty("reasoning").GetBoolean(); ImageInput.Checked = m.GetProperty("input").EnumerateArray().Any(i => i.GetString() == "image");
            ContextWindow.Value = m.GetProperty("contextWindow").GetDouble(); MaxTokens.Value = m.GetProperty("maxTokens").GetDouble();
        }
        internal void AddHeader()
        {
            ConfigurationJson.Need(ReplaceHeaders.Checked == true && !string.IsNullOrEmpty(HeaderName.Text) && (_headers.ContainsKey(HeaderName.Text) || _headers.Count < 32));
            _headers[HeaderName.Text] = HeaderValue.Text ?? ""; HeaderValue.Text = ""; RefreshHeaderNames();
        }
        private void RefreshHeaderNames() { _headerNames.Items.Clear(); foreach (var name in _headers.Keys) _headerNames.Items.Add(new ListItem { Key = name, Text = name }); }
        private void ClearEndpoint()
        {
            EndpointUrl.Text = ""; _endpointModels.Clear(); _modelList.Items.Clear(); EndpointModelId.Text = ""; EndpointModelName.Text = "";
            DeveloperRole.Checked = null; ReasoningEffort.Checked = null; ReplaceHeaders.Checked = false; _headers.Clear(); _headerNames.Items.Clear(); HeaderValue.Text = "";
        }
        private void ClearReply()
        {
            _input = null; _inputLabel.Text = ""; _inputLabel.Visible = false; SecretReply.Text = ""; TextReply.Text = ""; ChoiceReply.Items.Clear();
            SecretReply.Visible = TextReply.Visible = ChoiceReply.Visible = false; _reply.Enabled = false;
        }
        private void ClearInteraction() { ClearReply(); Instructions.Text = ""; _authorizationUrl = null; _browser.Enabled = false; }
        private void ClearSensitive()
        {
            ApiKey.Text = ""; HeaderValue.Text = ""; _headers.Clear();
            if (ReplaceHeaders.Checked == true) { ReplaceHeaders.Checked = false; _headerNames.Items.Clear(); }
            ClearInteraction();
        }
        protected override void Dispose(bool disposing)
        {
            if (_disposed) return;
            if (disposing && !_disposed) { CancelCurrent(); ClearSensitive(); _disposed = true; }
            base.Dispose(disposing);
        }
    }
}
