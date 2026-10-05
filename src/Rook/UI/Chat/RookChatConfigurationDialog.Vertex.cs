using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Eto.Forms;

namespace Rook.UI.Chat
{
    internal sealed partial class RookChatConfigurationDialog
    {
        internal const string VertexSharedSettingWarning = "Changing this project or location also changes Vertex text and Chirp routing and interrupts active Vertex media jobs.";
        internal const string FirmMediaOnlyWarning = "Firm sign-in enables Google images and videos. Activating it replaces the current Google connection and interrupts its media jobs. Vertex text and Vertex Chirp require another connection; other providers remain available.";
        internal readonly TextBox VertexProject = new(), VertexLocation = new(), VertexClientFile = new(), FirmSettingsFile = new();
        internal readonly DropDown VertexConnectionChoice = new();
        internal readonly Panel VertexGoogleFields = new(), VertexFirmFields = new();
        internal readonly Label VertexStatus = new() { Text = "Google settings have not been read.", Wrap = WrapMode.Word };
        internal readonly Label FirmPendingStatus = new() { Text = "Pending firm settings: not read.", Wrap = WrapMode.Word };
        internal readonly Label FirmActiveStatus = new() { Text = "Active firm settings: not read.", Wrap = WrapMode.Word };
        private readonly Dictionary<Button, string> _vertexActions = new();
        private FirmConfigurationStatus? _firmStatus;
        private long _vertexViewEpoch;
        private bool _vertexOwnedOperation;

        private Button VertexButton(string text, string operation)
        {
            var button = new Button { Text = text };
            button.Click += async (_, _) => await RunVertexActionAsync(operation);
            _vertexActions.Add(button, operation);
            return button;
        }
        private TabPage CreateVertexTab()
        {
            VertexConnectionChoice.Items.Add(new ListItem { Text = "Google account", Key = "google" });
            VertexConnectionChoice.Items.Add(new ListItem { Text = "Firm sign-in (Microsoft 365)", Key = "firm" });
            VertexGoogleFields.Content = Rows(
                new TableRow(new Label { Text = "Use a Google account authorized for the firm's billed Cloud project. Image location: global. Video requires us-central1.", Wrap = WrapMode.Word }),
                new TableRow(VertexButton("Read local Google settings", "status")),
                new TableRow("Firm's project ID", VertexProject),
                new TableRow("Vertex text and video location", VertexLocation),
                new TableRow(new Label { Text = VertexSharedSettingWarning, Wrap = WrapMode.Word }),
                new TableRow("Desktop OAuth JSON file", VertexClientFile),
                new TableRow(new Label { Text = "Your administrator supplies a Google Desktop app client JSON file. Your browser opens for consent; Rook protects authorization under your Windows account.", Wrap = WrapMode.Word }),
                new TableRow(VertexButton("Connect Google account", "connect")),
                new TableRow(VertexButton("Save shared project and location", "save")),
                new TableRow(VertexButton("Disconnect Google account", "disconnect")));
            VertexFirmFields.Content = Rows(
                new TableRow(new Label { Text = "Your administrator supplies firm settings for Microsoft 365 sign-in and the firm's billed Google Cloud project. Employees use their existing work identity.", Wrap = WrapMode.Word }),
                new TableRow(new Label { Text = FirmMediaOnlyWarning, Wrap = WrapMode.Word }),
                new TableRow(VertexButton("Read local firm settings", "firm_status")),
                new TableRow(FirmActiveStatus), new TableRow(FirmPendingStatus),
                new TableRow("Firm settings JSON file", FirmSettingsFile),
                new TableRow(VertexButton("Import firm settings", "import_firm")),
                new TableRow(VertexButton("Discard pending settings", "discard_firm")),
                new TableRow(VertexButton("Prepare reconnect with active settings", "prepare_firm_reconnect")),
                new TableRow(VertexButton("Sign in with your firm", "connect_firm")),
                new TableRow(VertexButton("Check sign-in", "check_firm_sign_in")),
                new TableRow(new Label { Text = "Check sign-in verifies identity and Google exchange. Image/video access, billing and quota remain unverified until separate live tests. Disconnect stops local access; Google operations already submitted may continue and incur charges.", Wrap = WrapMode.Word }),
                new TableRow(VertexButton("Disconnect from Rook", "disconnect_firm")));
            VertexConnectionChoice.SelectedValueChanged += (_, _) => {
                VertexGoogleFields.Visible = VertexConnectionChoice.SelectedIndex == 0;
                VertexFirmFields.Visible = VertexConnectionChoice.SelectedIndex == 1;
                UpdateVertexEnabled();
            };
            VertexConnectionChoice.SelectedIndex = 0;
            VertexFirmFields.Visible = false;
            return new TabPage { Text = "Enterprise Google", Content = VerticalScroll(Rows(
                new TableRow("Connection", VertexConnectionChoice), new TableRow(VertexStatus),
                new TableRow(VertexGoogleFields), new TableRow(VertexFirmFields))) };
        }
        private void UpdateVertexEnabled()
        {
            VertexConnectionChoice.Enabled = !Busy;
            foreach (var pair in _vertexActions) {
                var operation = pair.Value;
                pair.Key.Enabled = !Busy || _vertexOwnedOperation && operation is "disconnect" or "disconnect_firm";
                if (!Busy && operation == "connect_firm") pair.Key.Enabled &= _firmStatus?.PendingRevision is not null;
                if (!Busy && operation is "check_firm_sign_in" or "prepare_firm_reconnect") pair.Key.Enabled &= _firmStatus?.ActiveGeneration is not null;
                if (!Busy && operation == "save") pair.Key.Enabled &= _firmStatus?.Active is null;
            }
        }
        private static string FirmSummaryText(FirmSettingsSummary summary) => summary.Label + "; generation project " + summary.ProjectId + "; image " + summary.ImageLocation + "; video " + summary.VideoLocation + "; workforce user project " + summary.WorkforcePoolUserProject + "; API quota project " + (summary.QuotaProjectId ?? "not configured") + ".";
        private void ShowFirmStatus(FirmConfigurationStatus status)
        {
            _firmStatus = status;
            FirmActiveStatus.Text = status.Active is not null ? "Active local firm session: " + FirmSummaryText(status.Active) + (status.RetirementPending ? " Restart required; media authorization is blocked until retirement is confirmed." : " Model access, billing and quota are unverified.") : "No active firm session." + (status.LegacyMode is not null ? " The existing Google " + status.LegacyMode + " connection remains active." : "");
            FirmPendingStatus.Text = status.Pending is not null ? "Pending settings: " + FirmSummaryText(status.Pending) + " These settings become active only after successful firm sign-in and exchange." : "No pending firm settings.";
        }
        private Task<FirmConfigurationResult> RunFirmActionAsync(string operation, FirmConfigurationStatus? shown, string path, CancellationToken ct) => operation switch {
            "firm_status" => _client.ReadFirmConfigurationAsync(ct),
            "import_firm" => _client.ImportFirmSettingsAsync(path, ct),
            "discard_firm" => _client.DiscardPendingFirmSettingsAsync(ct),
            "prepare_firm_reconnect" when shown?.ActiveGeneration is not null => _client.PrepareFirmReconnectAsync(shown.ActiveGeneration, ct),
            "connect_firm" when shown?.PendingRevision is not null && shown.AuthorizationEpoch is not null => _client.ConnectFirmAccountAsync(shown.PendingRevision, shown.AuthorizationEpoch, ct),
            "disconnect_firm" => _client.DisconnectFirmAccountAsync(ct),
            _ => Task.FromResult(new FirmConfigurationResult(false, null, "Read local firm settings before this action.")),
        };
        internal async Task RunVertexActionAsync(string operation)
        {
            var disconnect = operation is "disconnect" or "disconnect_firm";
            if (_disposed || Busy && !(disconnect && _vertexOwnedOperation)) return;
            if (Busy) _operationCancellation?.Cancel();
            var epoch = ++_vertexViewEpoch;
            Busy = true; _vertexOwnedOperation = true; _cancelRequested = false;
            using var cancellation = new CancellationTokenSource();
            _operationCancellation = cancellation;
            var shown = _firmStatus;
            var firmPath = FirmSettingsFile.Text ?? "";
            var project = VertexProject.Text ?? ""; var location = VertexLocation.Text ?? ""; var path = VertexClientFile.Text ?? "";
            VertexStatus.Text = operation == "connect_firm" ? "Complete Microsoft firm sign-in in your browser. Pending settings have not yet replaced the active connection." : operation == "check_firm_sign_in" ? "Checking sign-in and Google exchange. Image/video access, billing and quota remain unverified." : operation == "connect" ? "Complete Google consent in your browser. Cancel operation stops this sign-in." : "Reading or changing local Google settings...";
            UpdateEnabled();
            try {
                if (operation == "check_firm_sign_in") {
                    var result = shown?.ActiveGeneration is not null ? await _client.CheckFirmSignInAsync(shown.ActiveGeneration, cancellation.Token).ConfigureAwait(false) : new FirmSignInResult(false, null, "Read local firm settings before checking sign-in.");
                    await PresentAsync(() => { if (epoch == _vertexViewEpoch) VertexStatus.Text = result.Message; }).ConfigureAwait(false);
                }
                else if (operation is "firm_status" or "import_firm" or "discard_firm" or "prepare_firm_reconnect" or "connect_firm" or "disconnect_firm") {
                    var result = await RunFirmActionAsync(operation, shown, firmPath, cancellation.Token).ConfigureAwait(false);
                    await PresentAsync(() => { if (epoch != _vertexViewEpoch) return; VertexStatus.Text = result.Message; if (result.Status is not null) ShowFirmStatus(result.Status); }).ConfigureAwait(false);
                }
                else {
                    var result = await (operation switch {
                        "status" => _client.ReadVertexConfigurationAsync(cancellation.Token),
                        "connect" => _client.ConnectVertexAccountAsync(path, project, location, cancellation.Token),
                        "save" => _client.SaveVertexMediaConfigurationAsync(project, location, cancellation.Token),
                        "disconnect" => _client.DisconnectVertexAccountAsync(cancellation.Token),
                        _ => Task.FromResult(new VertexConfigurationResult(false, null, "Unknown Google action.")),
                    }).ConfigureAwait(false);
                    await PresentAsync(() => {
                        if (epoch != _vertexViewEpoch) return;
                        VertexStatus.Text = result.Message;
                        if (result.Status is not { } status) return;
                        VertexProject.Text = status.ProjectId; VertexLocation.Text = status.VideoLocation;
                        VertexStatus.Text = status.Mode == "workforce" ? "A firm connection is active. Use Firm sign-in to read or change it. Model access, billing and quota remain unverified." : status.Configured ? "Configured using " + status.Mode + (status.VideoAvailable ? ". Video location is supported." : ". Video is unavailable in this location. Existing text location was preserved; choose us-central1 and save explicitly to enable video.") : "Google account is disconnected.";
                    }).ConfigureAwait(false);
                }
            }
            catch (OperationCanceledException) {
                await PresentAsync(() => { if (epoch == _vertexViewEpoch) VertexStatus.Text = disconnect ? "Disconnect cancelled. Read local settings to confirm local deletion and process retirement." : "Google action cancelled. Read local settings after the owned worker settles. Image/video access, billing and quota remain unverified."; }).ConfigureAwait(false);
            }
            catch { await PresentAsync(() => { if (epoch == _vertexViewEpoch) VertexStatus.Text = "Google configuration is unavailable. Read local settings."; }).ConfigureAwait(false); }
            finally { await PresentAsync(() => { if (epoch == _vertexViewEpoch) { _operationCancellation = null; Busy = false; _vertexOwnedOperation = false; UpdateEnabled(); } }).ConfigureAwait(false); }
        }
    }
}
