using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Rook.UI.Chat;
using Rook.Tests.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    [Collection(Rook.Tests.UI.EtoUiCollection.Name)]
    public sealed class VertexConfigurationDialogTests : IClassFixture<AgentChatProgressTests.PanelThread>
    {
        private readonly AgentChatProgressTests.PanelThread _ui;
        public VertexConfigurationDialogTests(AgentChatProgressTests.PanelThread ui) => _ui = ui;
        [Fact]
        public async Task FirmViewHidesGoogleClientAndUsesDisplayedPendingRevision()
        {
            var active = false; var pendingSettings = true;
            var requests = new List<JsonElement>();
            var summary = new { label = "Synthetic firm", project_id = "synthetic-firm-project", video_location = "us-central1", image_location = "global", workforce_pool_user_project = "synthetic-firm-project", quota_project_id = (string?)null };
            var http = new VertexTestHandler(async (request, _) => {
                var body = JsonDocument.Parse(await request.Content!.ReadAsStringAsync()).RootElement.Clone(); requests.Add(body);
                var operation = body.GetProperty("operation").GetString();
                if (operation == "connect_firm") {
                    Assert.Equal(new string('a', 32), body.GetProperty("pending_revision").GetString());
                    Assert.Equal(new string('b', 32), body.GetProperty("authorization_epoch").GetString());
                    active = true; pendingSettings = false;
                }
                object data = operation == "check_firm_sign_in" ? new {
                    contract_version = 2, check_scope = "identity_exchange", state = "signed_in", code = (string?)null, generation = new string('c', 32), image_access = "unverified", video_access = "unverified", billing = "unverified", quota = "unverified",
                } : (object)new {
                    contract_version = 2, active = active ? summary : null, active_generation = active ? new string('c', 32) : null,
                    retirement_pending = false, pending = pendingSettings ? summary : null,
                    pending_revision = pendingSettings ? new string('a', 32) : null, authorization_epoch = pendingSettings ? new string('b', 32) : null,
                    legacy_mode = (string?)null, state = active ? "signed_in" : "sign_in_required",
                };
                return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(JsonSerializer.Serialize(new { success = true, data })) };
            });
            using var client = AgentChatClient.ForTests(http, new Uri("http://127.0.0.1:1"));
            var queue = new ConcurrentQueue<Action>(); RookChatConfigurationDialog dialog = null!;
            _ui.Run(() => { Rook.Tests.UI.EtoTestPlatform.Ensure(); SynchronizationContext.SetSynchronizationContext(null); dialog = new(client, queue.Enqueue); dialog.VertexConnectionChoice.SelectedIndex = 1; });
            async Task Run(string operation) {
                Task pending = null!; _ui.Run(() => pending = dialog.RunVertexActionAsync(operation));
                while (!pending.IsCompleted) { _ui.Run(() => { while (queue.TryDequeue(out var next)) next(); }); await Task.Delay(1); }
                _ui.Run(() => { while (queue.TryDequeue(out var next)) next(); }); await pending;
            }
            try {
                _ui.Run(() => { Assert.False(dialog.VertexGoogleFields.Visible); Assert.True(dialog.VertexFirmFields.Visible); });
                await Run("firm_status");
                _ui.Run(() => { Assert.Contains("Pending", dialog.FirmPendingStatus.Text); Assert.Contains("images and videos", RookChatConfigurationDialog.FirmMediaOnlyWarning); });
                await Run("connect_firm"); await Run("check_firm_sign_in");
                _ui.Run(() => { Assert.Contains("remain unverified", dialog.VertexStatus.Text); Assert.DoesNotContain("Generation ready", dialog.VertexStatus.Text); });
                Assert.Equal(3, requests.Count);
            }
            finally { _ui.Run(() => dialog.Dispose()); }
        }

        [Fact]
        public async Task DisconnectDuringHeldCheckCannotPublishLateSuccess()
        {
            var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var released = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            var disconnected = false;
            var summary = new { label = "Synthetic firm", project_id = "synthetic-firm-project", video_location = "us-central1", image_location = "global", workforce_pool_user_project = "synthetic-firm-project", quota_project_id = (string?)null };
            var http = new VertexTestHandler(async (request, _) => {
                var body = JsonDocument.Parse(await request.Content!.ReadAsStringAsync()).RootElement;
                var operation = body.GetProperty("operation").GetString();
                object data;
                if (operation == "check_firm_sign_in") {
                    entered.SetResult(true); await released.Task;
                    data = new { contract_version = 2, check_scope = "identity_exchange", state = "signed_in", code = (string?)null, generation = new string('c', 32), image_access = "unverified", video_access = "unverified", billing = "unverified", quota = "unverified" };
                }
                else if (operation == "disconnect") {
                    disconnected = true;
                    data = new { configured = false, mode = (string?)null, project_id = "", video_location = "", image_location = "global", video_available = false };
                }
                else data = new { contract_version = 2, active = disconnected ? null : summary, active_generation = disconnected ? null : new string('c', 32), retirement_pending = false, pending = (object?)null, pending_revision = (string?)null, authorization_epoch = (string?)null, legacy_mode = (string?)null, state = disconnected ? "unconfigured" : "signed_in" };
                return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(JsonSerializer.Serialize(new { success = true, data })) };
            });
            using var client = AgentChatClient.ForTests(http, new Uri("http://127.0.0.1:1"));
            var queue = new ConcurrentQueue<Action>(); RookChatConfigurationDialog dialog = null!;
            _ui.Run(() => { Rook.Tests.UI.EtoTestPlatform.Ensure(); SynchronizationContext.SetSynchronizationContext(null); dialog = new(client, queue.Enqueue); dialog.VertexConnectionChoice.SelectedIndex = 1; });
            async Task Pump(Task pending) {
                var deadline = DateTime.UtcNow.AddSeconds(5);
                while (!pending.IsCompleted && DateTime.UtcNow < deadline) { _ui.Run(() => { while (queue.TryDequeue(out var next)) next(); }); await Task.Delay(1); }
                _ui.Run(() => { while (queue.TryDequeue(out var next)) next(); }); Assert.True(pending.IsCompleted); await pending;
            }
            Task Start(string operation) { Task pending = null!; _ui.Run(() => pending = dialog.RunVertexActionAsync(operation)); return pending; }
            try {
                await Pump(Start("firm_status"));
                var check = Start("check_firm_sign_in"); await entered.Task;
                await Pump(Start("disconnect_firm"));
                released.SetResult(true); await Pump(check);
                _ui.Run(() => { Assert.Contains("No active firm session", dialog.FirmActiveStatus.Text); Assert.DoesNotContain("exchange passed", dialog.VertexStatus.Text); Assert.False(dialog.Busy); });
            }
            finally { released.TrySetResult(true); _ui.Run(() => dialog.Dispose()); }
        }

        [Fact]
        public async Task OpenSettingsPreservesTextRegionAndExplicitSaveExplainsImpact()
        {
            var requests=new List<JsonElement>();
            var region="europe-west4";
            var http=new VertexTestHandler(async (request,_) =>
            {
                var json=JsonDocument.Parse(await request.Content!.ReadAsStringAsync()).RootElement.Clone();
                requests.Add(json);
                if(json.GetProperty("operation").GetString()=="save") region=json.GetProperty("video_location").GetString()!;
                return new HttpResponseMessage(HttpStatusCode.OK) { Content=new StringContent(JsonSerializer.Serialize(new {
                    success=true,data=new {configured=true,mode="oauth",project_id="company-project",video_location=region,image_location="global",video_available=region=="us-central1"}})) };
            });
            using var client=AgentChatClient.ForTests(http,new Uri("http://127.0.0.1:1"));
            var queue=new ConcurrentQueue<Action>();
            RookChatConfigurationDialog dialog=null!;
            _ui.Run(()=>{Rook.Tests.UI.EtoTestPlatform.Ensure();SynchronizationContext.SetSynchronizationContext(null);dialog=new(client,queue.Enqueue);});
            async Task Run(string action)
            {
                Task pending=null!;
                _ui.Run(()=>pending=dialog.RunVertexActionAsync(action));
                while(!pending.IsCompleted) { _ui.Run(()=>{while(queue.TryDequeue(out var next))next();}); await Task.Delay(1); }
                _ui.Run(()=>{while(queue.TryDequeue(out var next))next();});
                await pending;
            }
            try
            {
                await Run("status");
                _ui.Run(()=>{Assert.Equal("europe-west4",dialog.VertexLocation.Text);Assert.Contains("preserved",dialog.VertexStatus.Text);});
                Assert.Single(requests);
                Assert.Contains("text and Chirp routing",RookChatConfigurationDialog.VertexSharedSettingWarning);
                _ui.Run(()=>dialog.VertexLocation.Text="us-central1");
                await Run("save");
                Assert.Equal("save",requests[1].GetProperty("operation").GetString());
                Assert.Equal("us-central1",region);
            }
            finally { _ui.Run(()=>dialog.Dispose()); }
        }
    }
}
