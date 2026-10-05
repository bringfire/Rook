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
