using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rook.Bim;
using Rook.Handlers;
using Rook.Tests.Bim;
using Xunit;

namespace Rook.Tests.Handlers
{
    [Collection(RookBimRuntimeRegistryCollection.Name)]
    public sealed class BimCreationGuidProbeHandlerTests
    {
        [Fact]
        public void Dispatch_WhenDiagnosticsDisabledRejectsBeforeRuntime()
        {
            var runtime = new RecordingRuntime();
            using (BimDiagnostics.PushSessionForTests(new BimDiagnosticSession(false, null)))
            using (Install(runtime))
            {
                var response = new BimHandler(() => true).Dispatch(
                    "{\"op\":\"creation_guid_probe\",\"action\":\"begin\"}");

                Assert.False(response.Success);
                Assert.Equal(503, response.HttpStatus);
                Assert.Equal("capability_unavailable", Json(response.Data)
                    .GetProperty("errorCode").GetString());
                Assert.Equal(0, runtime.ProbeCalls);
                Assert.Same(runtime, RookBimRuntimeRegistry.Current);
                Assert.Equal("creation-guid-probe-test", RookBimRuntimeRegistry.Source);
            }
        }

        [Theory]
        [InlineData("begin", null, BimCreationGuidProbeAction.Begin, null)]
        [InlineData("capture", "file_local_reopen", BimCreationGuidProbeAction.Capture,
            BimCreationGuidProbeCase.FileLocalReopen)]
        [InlineData("complete", null, BimCreationGuidProbeAction.Complete, null)]
        [InlineData("abort", null, BimCreationGuidProbeAction.Abort, null)]
        public void Dispatch_WhenDiagnosticsEnabledBindsExactWireValuesAndSerializesSafeResult(
            string action,
            string? caseId,
            BimCreationGuidProbeAction expectedAction,
            BimCreationGuidProbeCase? expectedCase)
        {
            var sink = new RecordingSink();
            var runtime = new RecordingRuntime();
            using (BimDiagnostics.PushSessionForTests(new BimDiagnosticSession(true, sink)))
            using (Install(runtime))
            {
                var body = new JsonObject
                {
                    ["op"] = "creation_guid_probe",
                    ["action"] = action,
                    ["caseId"] = caseId,
                }.ToJsonString();

                var response = new BimHandler(() => true).Dispatch(body);

                Assert.True(response.Success);
                Assert.Equal(1, runtime.ProbeCalls);
                Assert.Equal(expectedAction, runtime.LastRequest!.Action);
                Assert.Equal(expectedCase, runtime.LastRequest.CaseId);
                Assert.Equal("creation-001", Json(response.Data)
                    .GetProperty("creation_alias").GetString());
                Assert.Single(sink.Terminals);
            }
        }

        [Fact]
        public void Dispatch_WhenProbeRuntimeFailsCompletesExactlyOnce()
        {
            var sink = new RecordingSink();
            var runtime = new RecordingRuntime
            {
                Response = BimApiResponse.Fail(BimErrorCode.InternalError, "safe failure", 500),
            };
            using (BimDiagnostics.PushSessionForTests(new BimDiagnosticSession(true, sink)))
            using (Install(runtime))
            {
                var response = new BimHandler(() => true).Dispatch(
                    "{\"op\":\"creation_guid_probe\",\"action\":\"abort\"}");

                Assert.False(response.Success);
                Assert.Equal(1, runtime.ProbeCalls);
                Assert.Single(sink.Terminals);
            }
        }

        [Fact]
        public void Dispatch_SerializesTaskOneSafeResultThroughWireSerializer()
        {
            var runtime = new RecordingRuntime
            {
                Response = BimApiResponse.Ok(new BimCreationGuidProbeAbortResult(
                    BimCreationGuidProbeSessionCode.Aborted, true)),
            };
            using (BimDiagnostics.PushSessionForTests(new BimDiagnosticSession(true, null)))
            using (Install(runtime))
            {
                var response = new BimHandler(() => true).Dispatch(
                    "{\"op\":\"creation_guid_probe\",\"action\":\"abort\"}");
                var data = Json(response.Data);

                Assert.True(response.Success);
                Assert.Equal("aborted", data.GetProperty("code").GetString());
                Assert.True(data.GetProperty("rawStateCleared").GetBoolean());
            }
        }

        [Fact]
        public void NativeSurface_DoesNotExposeCreationGuidProbe()
        {
            var source = Read("src/RookNative/RookServer.cpp") +
                Read("src/RookNative/Handlers/GrasshopperProxyHandler.cpp") +
                Read("src/RookNative/Handlers/GrasshopperProxyHandler.h");

            Assert.DoesNotContain("creation_guid_probe", source, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("CreationGuidProbe", source, StringComparison.Ordinal);
        }

        private static JsonElement Json(object? value)
        {
            using var document = JsonDocument.Parse(JsonSerializer.Serialize(value));
            return document.RootElement.Clone();
        }

        private static IDisposable Install(IRookBimRuntime runtime)
        {
            RookBimRuntimeRegistry.Install(runtime, "creation-guid-probe-test");
            return new ActionOnDispose(RookBimRuntimeRegistry.ResetForTests);
        }

        private static string Read(string relativePath)
        {
            var directory = new System.IO.DirectoryInfo(AppContext.BaseDirectory);
            while (directory != null)
            {
                var candidate = System.IO.Path.Combine(directory.FullName,
                    relativePath.Replace('/', System.IO.Path.DirectorySeparatorChar));
                if (System.IO.File.Exists(candidate))
                {
                    return System.IO.File.ReadAllText(candidate);
                }

                directory = directory.Parent;
            }

            throw new System.IO.FileNotFoundException(relativePath);
        }

        private sealed class RecordingRuntime : IRookBimRuntime
        {
            internal int ProbeCalls { get; private set; }
            internal BimCreationGuidProbeRequest? LastRequest { get; private set; }
            internal BimApiResponse Response { get; set; } = BimApiResponse.Ok(
                new JsonObject { ["creation_alias"] = "creation-001" });

            public BimApiResponse CreationGuidProbe(BimDiagnosticContext diagnostics,
                BimCreationGuidProbeRequest request)
            {
                ProbeCalls++;
                LastRequest = request;
                return Response;
            }

            public BimStatusResponse Status(BimDiagnosticContext diagnostics) =>
                new BimStatusResponse { Available = true };
            public BimApiResponse ActiveDocument(BimDiagnosticContext diagnostics) => BimApiResponse.Ok(null);
            public BimApiResponse ListCategories(BimDiagnosticContext diagnostics) => BimApiResponse.Ok(null);
            public BimApiResponse QueryElements(BimDiagnosticContext diagnostics, BimQueryElementsRequest request) => BimApiResponse.Ok(null);
            public BimApiResponse ElementInfo(BimDiagnosticContext diagnostics, BimElementRequest request) => BimApiResponse.Ok(null);
            public BimApiResponse ElementParameters(BimDiagnosticContext diagnostics, BimElementRequest request) => BimApiResponse.Ok(null);
            public BimApiResponse SelectElements(BimDiagnosticContext diagnostics, BimSelectElementsRequest request) => BimApiResponse.Ok(null);
            public BimApiResponse ClearSelection(BimDiagnosticContext diagnostics) => BimApiResponse.Ok(null);
            public BimApiResponse ExportElements(BimDiagnosticContext diagnostics, BimExportElementsRequest request) => BimApiResponse.Ok(null);
            public BimApiResponse ExportPreset(BimDiagnosticContext diagnostics, BimExportPresetRequest request) => BimApiResponse.Ok(null);
        }

        private sealed class RecordingSink : IBimDiagnosticEnvelopeSink
        {
            private readonly List<BimDiagnosticEnvelope> terminals = new List<BimDiagnosticEnvelope>();
            internal IReadOnlyList<BimDiagnosticEnvelope> Terminals => terminals;

            public bool TryEnqueue(BimDiagnosticEnvelope envelope)
            {
                if (envelope.Kind == BimDiagnosticRecordKind.Terminal)
                {
                    terminals.Add(envelope);
                }

                return true;
            }
        }

        private sealed class ActionOnDispose : IDisposable
        {
            private readonly Action action;
            internal ActionOnDispose(Action action) => this.action = action;
            public void Dispose() => action();
        }
    }
}
