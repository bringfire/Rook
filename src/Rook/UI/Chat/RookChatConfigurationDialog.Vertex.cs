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
        internal readonly TextBox VertexProject = new(), VertexLocation = new(), VertexClientFile = new();
        internal readonly Label VertexStatus = new() { Text = "Google settings have not been read.", Wrap = WrapMode.Word };
        private readonly List<Button> _vertexActions = new();
        private Button VertexButton(string text, string operation)
        {
            var button = new Button { Text = text };
            button.Click += async (_, _) => await RunVertexActionAsync(operation);
            _vertexActions.Add(button);
            return button;
        }
        private TabPage CreateVertexTab() => new()
        {
            Text = "Enterprise Google",
            Content = VerticalScroll(Rows(
                new TableRow(new Label { Text = "Use a Google account authorized for the firm's billed Cloud project. Image location: global. Video requires us-central1.", Wrap = WrapMode.Word }),
                new TableRow(VertexStatus),
                new TableRow(VertexButton("Read local Google settings", "status")),
                new TableRow("Firm's project ID", VertexProject),
                new TableRow("Vertex text and video location", VertexLocation),
                new TableRow(new Label { Text = VertexSharedSettingWarning, Wrap = WrapMode.Word }),
                new TableRow("Desktop OAuth JSON file", VertexClientFile),
                new TableRow(new Label { Text = "The Rook maintainer or firm administrator creates a Desktop app client in Google Auth Platform and supplies its downloaded JSON file. Your browser opens for consent; Rook protects authorization under your Windows account.", Wrap = WrapMode.Word }),
                new TableRow(VertexButton("Connect Google account", "connect")),
                new TableRow(VertexButton("Save shared project and location", "save")),
                new TableRow(VertexButton("Disconnect Google account", "disconnect"))))
        };
        private void UpdateVertexEnabled()
        {
            foreach (var action in _vertexActions) action.Enabled = !Busy;
        }
        internal async Task RunVertexActionAsync(string operation)
        {
            if (_disposed || Busy) return;
            Busy = true;
            _cancelRequested = false;
            using var cancellation = new CancellationTokenSource();
            _operationCancellation = cancellation;
            var project = VertexProject.Text ?? "";
            var location = VertexLocation.Text ?? "";
            var path = VertexClientFile.Text ?? "";
            VertexStatus.Text = operation == "connect" ? "Complete Google consent in your browser. Cancel operation stops this sign-in." : "Reading or changing local Google settings...";
            UpdateEnabled();
            try
            {
                var result = await (operation switch
                {
                    "status" => _client.ReadVertexConfigurationAsync(cancellation.Token),
                    "connect" => _client.ConnectVertexAccountAsync(path, project, location, cancellation.Token),
                    "save" => _client.SaveVertexMediaConfigurationAsync(project, location, cancellation.Token),
                    "disconnect" => _client.DisconnectVertexAccountAsync(cancellation.Token),
                    _ => Task.FromResult(new VertexConfigurationResult(false, null, "Unknown Google action.")),
                }).ConfigureAwait(false);
                await PresentAsync(() =>
                {
                    VertexStatus.Text = result.Message;
                    if (result.Status is not { } status) return;
                    VertexProject.Text = status.ProjectId;
                    VertexLocation.Text = status.VideoLocation;
                    VertexStatus.Text = status.Configured ?
                        "Configured using " + status.Mode + (status.VideoAvailable ? ". Video location is supported." : ". Video is unavailable in this location. Existing text location was preserved; choose us-central1 and save explicitly to enable video.") : "Google account is disconnected.";
                }).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                await PresentAsync(() => VertexStatus.Text = "Google action cancelled. Refresh local settings after the owned service finishes cleanup.").ConfigureAwait(false);
            }
            catch { await PresentAsync(() => VertexStatus.Text = "Google configuration is unavailable.").ConfigureAwait(false); }
            finally
            {
                await PresentAsync(() => { _operationCancellation = null; Busy = false; UpdateEnabled(); }).ConfigureAwait(false);
            }
        }
    }
}
