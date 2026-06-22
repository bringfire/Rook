using System.Text.Json.Nodes;
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction
{
    public class NativeEndpointSelectionTests
    {
        private static JsonObject Doc(string pluginType, int processId, int port) => new()
        {
            ["pluginType"] = pluginType,
            ["processId"] = processId,
            ["port"] = port,
            ["host"] = "127.0.0.1",
        };

        [Fact]
        public void Selects_Native_Entry_For_Current_Process()
        {
            var docs = new[] { Doc("native", 4242, 51000), Doc("native", 9999, 52000), Doc("chat", 4242, 53000) };
            Assert.Equal(51000, NativeEndpointResolver.SelectNativePort(docs, currentProcessId: 4242));
        }

        [Fact]
        public void Returns_Null_When_No_Native_Entry_For_This_Process()
        {
            var docs = new[] { Doc("native", 9999, 52000), Doc("chat", 4242, 53000) };
            Assert.Null(NativeEndpointResolver.SelectNativePort(docs, currentProcessId: 4242));
        }

        [Fact]
        public void Returns_Null_For_Empty()
        {
            Assert.Null(NativeEndpointResolver.SelectNativePort(new JsonObject[0], currentProcessId: 4242));
        }

        [Fact]
        public void Ambiguous_Same_Process_Native_Entries_Return_Null()
        {
            // Two native entries for THIS pid (stale/duplicate) — fail closed, don't guess.
            var docs = new[] { Doc("native", 4242, 51000), Doc("native", 4242, 52000) };
            Assert.Null(NativeEndpointResolver.SelectNativePort(docs, currentProcessId: 4242));
        }
    }
}
