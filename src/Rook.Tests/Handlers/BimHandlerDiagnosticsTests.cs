using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Bim;
using Rook.Handlers;
using Rook.Tests.Bim;
using Xunit;

namespace Rook.Tests.Handlers
{
    [Collection(RookBimRuntimeRegistryCollection.Name)]
    public sealed class BimHandlerDiagnosticsTests
    {
        private static readonly string[] RequestDiagnosticFields =
        {
            "correlationId",
            "lastStage",
            "lastOutcome",
            "lastItemIndex",
            "firstFailureStage",
            "firstFailureExceptionType",
            "firstFailureHResult",
            "requestDroppedCount",
            "traceComplete",
            "sinkState",
            "droppedCount",
        };

        [Fact]
        public void Dispatch_SuccessCreatesOneContextAndOneMatchingTerminal()
        {
            var sink = new RecordingSink();
            var session = new BimDiagnosticSession(true, sink);
            var runtime = new RecordingRuntime();

            using (BimDiagnostics.PushSessionForTests(session))
            using (InstallRuntime(runtime))
            {
                var response = new BimHandler(() => true)
                    .Dispatch("{\"op\":\"active_document\"}");

                Assert.True(response.Success);
                var context = Assert.Single(runtime.Contexts);
                Assert.True(context.Enabled);
                Assert.False(string.IsNullOrWhiteSpace(context.CorrelationId));
                Assert.Equal(context.CorrelationId,
                    ToJsonElement(response.Diagnostic)
                        .GetProperty("correlationId").GetString());
                var terminal = Assert.Single(Terminals(sink));
                Assert.Equal(context.CorrelationId, terminal.CorrelationId);
                Assert.Equal(BimDiagnosticOutcome.Success, terminal.Outcome);
            }
        }

        [Fact]
        public void Dispatch_RuntimeExceptionRecordsFailureAndCompletesOnce()
        {
            var sink = new RecordingSink();
            var session = new BimDiagnosticSession(true, sink);
            var exception = new HandlerRuntimeTestException("forbidden model title");
            var runtime = new RecordingRuntime { RuntimeException = exception };

            using (BimDiagnostics.PushSessionForTests(session))
            using (InstallRuntime(runtime))
            {
                var response = new BimHandler(() => true)
                    .Dispatch("{\"op\":\"active_document\"}");
                var data = ToJsonElement(response.Data);

                Assert.False(response.Success);
                Assert.Equal(500, response.HttpStatus);
                Assert.Equal("internal_error", data.GetProperty("errorCode").GetString());
                var context = Assert.Single(runtime.Contexts);
                var failure = Assert.Single(sink.Envelopes, envelope =>
                    envelope.Kind == BimDiagnosticRecordKind.Failure &&
                    envelope.Stage == BimDiagnosticStage.HandlerRuntime);
                Assert.Equal(context.CorrelationId, failure.CorrelationId);
                Assert.Equal(typeof(HandlerRuntimeTestException).FullName, failure.ExceptionTypeName);
                Assert.Equal(exception.HResult, failure.ExceptionHResult);
                Assert.Equal(BimDiagnosticFailureImpact.Production, failure.Fields.FailureImpact);
                Assert.Equal(BimDiagnosticOutcome.Failure, Assert.Single(Terminals(sink)).Outcome);
            }
        }

        [Fact]
        public void Dispatch_SerializerExceptionRecordsOneFailureAndUsesMinimalFallback()
        {
            var sink = new RecordingSink();
            var session = new BimDiagnosticSession(true, sink);
            var runtime = new RecordingRuntime();
            var exception = new HandlerSerializerTestException(
                "forbidden model title and C:\\private\\model.rvt");
            var serializerCalls = 0;

            using (BimDiagnostics.PushSessionForTests(session))
            using (InstallRuntime(runtime))
            {
                var handler = new BimHandler(
                    () => true,
                    value =>
                    {
                        Interlocked.Increment(ref serializerCalls);
                        throw exception;
                    });

                var response = handler.Dispatch("{\"op\":\"active_document\"}");
                var data = ToJsonElement(response.Data);
                var diagnostic = ToJsonElement(response.Diagnostic);

                Assert.False(response.Success);
                Assert.Equal(500, response.HttpStatus);
                Assert.Equal("internal_error", data.GetProperty("errorCode").GetString());
                Assert.Equal("BIM dispatch failed.", data.GetProperty("message").GetString());
                Assert.Equal(1, serializerCalls);

                var failure = Assert.Single(sink.Envelopes, envelope =>
                    envelope.Kind == BimDiagnosticRecordKind.Failure &&
                    envelope.Stage == BimDiagnosticStage.HandlerSerialize);
                Assert.Equal(BimDiagnosticDetailCode.SerializationFailure,
                    failure.Fields.DetailCode);
                Assert.Equal(BimDiagnosticFailureImpact.Production,
                    failure.Fields.FailureImpact);
                Assert.Equal(typeof(HandlerSerializerTestException).FullName,
                    failure.ExceptionTypeName);
                Assert.Equal(exception.HResult, failure.ExceptionHResult);
                Assert.Equal("handler.serialize",
                    diagnostic.GetProperty("firstFailureStage").GetString());
                Assert.Equal(typeof(HandlerSerializerTestException).FullName,
                    diagnostic.GetProperty("firstFailureExceptionType").GetString());
                Assert.Equal(exception.HResult,
                    diagnostic.GetProperty("firstFailureHResult").GetInt32());
                Assert.Equal("handler.serialize",
                    diagnostic.GetProperty("lastStage").GetString());
                Assert.Equal("failure",
                    diagnostic.GetProperty("lastOutcome").GetString());
                Assert.DoesNotContain(exception.Message,
                    JsonSerializer.Serialize(response), StringComparison.Ordinal);

                var terminal = Assert.Single(Terminals(sink));
                Assert.Equal(failure.CorrelationId, terminal.CorrelationId);
                Assert.Equal(BimDiagnosticOutcome.Failure, terminal.Outcome);
            }
        }

        [Fact]
        public void Dispatch_FailureDetailsUsesInjectedSerializerOnce()
        {
            var sink = new RecordingSink();
            var session = new BimDiagnosticSession(true, sink);
            var runtime = new DetailFailureRuntime();
            var serializerCalls = 0;

            using (BimDiagnostics.PushSessionForTests(session))
            using (InstallRuntime(runtime))
            {
                var response = new BimHandler(
                    () => true,
                    value =>
                    {
                        Interlocked.Increment(ref serializerCalls);
                        return new JsonObject { ["serialized"] = true };
                    }).Dispatch("{\"op\":\"active_document\"}");
                var data = ToJsonElement(response.Data);

                Assert.False(response.Success);
                Assert.Equal(1, serializerCalls);
                Assert.True(data.GetProperty("details")
                    .GetProperty("serialized").GetBoolean());
                Assert.Equal(BimDiagnosticOutcome.Failure,
                    Assert.Single(Terminals(sink)).Outcome);
            }
        }

        [Fact]
        public void Dispatch_ArgumentSerializerExceptionStillUsesMinimalFallback()
        {
            var sink = new RecordingSink();
            var session = new BimDiagnosticSession(true, sink);
            var runtime = new RecordingRuntime();

            using (BimDiagnostics.PushSessionForTests(session))
            using (InstallRuntime(runtime))
            {
                var response = new BimHandler(
                    () => true,
                    value => throw new ArgumentException("serializer detail"))
                    .Dispatch("{\"op\":\"active_document\"}");
                var data = ToJsonElement(response.Data);

                Assert.Equal(500, response.HttpStatus);
                Assert.Equal("internal_error", data.GetProperty("errorCode").GetString());
                Assert.Equal(BimDiagnosticStage.HandlerSerialize,
                    Assert.Single(sink.Envelopes, envelope =>
                        envelope.Kind == BimDiagnosticRecordKind.Failure)
                        .Stage);
                Assert.Equal(BimDiagnosticOutcome.Failure,
                    Assert.Single(Terminals(sink)).Outcome);
            }
        }

        [Fact]
        public void Dispatch_SerializerFailureUsesMinimalFallbackAfterEarlierProductionFailure()
        {
            var sink = new RecordingSink();
            var session = new BimDiagnosticSession(true, sink);
            var runtime = new PriorFailureRuntime();

            using (BimDiagnostics.PushSessionForTests(session))
            using (InstallRuntime(runtime))
            {
                var response = new BimHandler(
                    () => true,
                    value => throw new ArgumentException("serializer detail"))
                    .Dispatch("{\"op\":\"active_document\"}");
                var diagnostic = ToJsonElement(response.Diagnostic);

                Assert.Equal(500, response.HttpStatus);
                Assert.Equal("revit.document.acquire",
                    diagnostic.GetProperty("firstFailureStage").GetString());
                Assert.Equal(typeof(PriorRuntimeTestException).FullName,
                    diagnostic.GetProperty("firstFailureExceptionType").GetString());
                Assert.Equal("handler.serialize",
                    diagnostic.GetProperty("lastStage").GetString());
                Assert.Equal("failure",
                    diagnostic.GetProperty("lastOutcome").GetString());
                Assert.Equal(2, sink.Envelopes.Count(envelope =>
                    envelope.Kind == BimDiagnosticRecordKind.Failure));
                Assert.Single(Terminals(sink));
            }
        }

        [Fact]
        public void Dispatch_TypedDeserializeFailureCompletesAcceptedRequestOnce()
        {
            var sink = new RecordingSink();
            var session = new BimDiagnosticSession(true, sink);

            using (BimDiagnostics.PushSessionForTests(session))
            {
                var response = new BimHandler(() => true).Dispatch(
                    "{\"op\":\"element_info\",\"identity\":{\"elementId\":\"not-an-integer\"}}");
                var data = ToJsonElement(response.Data);

                Assert.False(response.Success);
                Assert.Equal(400, response.HttpStatus);
                Assert.Equal("invalid_scope", data.GetProperty("errorCode").GetString());
                var failure = Assert.Single(sink.Envelopes, envelope =>
                    envelope.Kind == BimDiagnosticRecordKind.Failure &&
                    envelope.Stage == BimDiagnosticStage.HandlerDeserialize);
                Assert.DoesNotContain(sink.Envelopes, envelope =>
                    envelope.Kind == BimDiagnosticRecordKind.Failure &&
                    envelope.Stage == BimDiagnosticStage.HandlerRuntime);
                var terminal = Assert.Single(Terminals(sink));
                Assert.NotNull(failure.CorrelationId);
                Assert.Equal(failure.CorrelationId, terminal.CorrelationId);
                Assert.Equal(BimDiagnosticOutcome.Failure, terminal.Outcome);
            }
        }

        [Fact]
        public void Dispatch_PreDiscriminatorFailureUsesUncorrelatedEvidenceWithoutTerminal()
        {
            var sink = new RecordingSink();
            var session = new BimDiagnosticSession(true, sink);

            using (BimDiagnostics.PushSessionForTests(session))
            {
                var response = new BimHandler(() => true).Dispatch("{");

                Assert.Equal(400, response.HttpStatus);
                Assert.Null(response.Diagnostic);
                var failure = Assert.Single(sink.Envelopes, envelope =>
                    envelope.Kind == BimDiagnosticRecordKind.Failure);
                Assert.Equal(BimDiagnosticStage.HandlerDeserialize, failure.Stage);
                Assert.Equal("unparsed", failure.Operation);
                Assert.Null(failure.CorrelationId);
                Assert.Empty(Terminals(sink));
            }
        }

        [Fact]
        public void Dispatch_StandaloneStatusCreatesContextBeforeEarlyReturnAndCompletesOnce()
        {
            var sink = new RecordingSink();
            var session = new BimDiagnosticSession(true, sink);

            using (BimDiagnostics.PushSessionForTests(session))
            {
                var response = new BimHandler(() => false)
                    .Dispatch("{\"op\":\"status\"}");
                var diagnostic = ToJsonElement(response.Diagnostic);

                Assert.True(response.Success);
                var terminal = Assert.Single(Terminals(sink));
                Assert.Equal(BimDiagnosticOutcome.Success, terminal.Outcome);
                Assert.Equal(terminal.CorrelationId,
                    diagnostic.GetProperty("correlationId").GetString());
                Assert.Contains(sink.Envelopes, envelope =>
                    envelope.CorrelationId == terminal.CorrelationId &&
                    envelope.Stage == BimDiagnosticStage.HandlerSerialize &&
                    envelope.Outcome == BimDiagnosticOutcome.Success);
            }
        }

        [Fact]
        public async Task Dispatch_ConcurrentRequestsKeepDistinctContextsAndMatchingTerminals()
        {
            var sink = new RecordingSink();
            var session = new BimDiagnosticSession(true, sink);
            var runtime = new BarrierRuntime(2);

            using (BimDiagnostics.PushSessionForTests(session))
            using (InstallRuntime(runtime))
            {
                var handler = new BimHandler(() => true);
                var first = Task.Run(() => handler.Dispatch("{\"op\":\"active_document\"}"));
                var second = Task.Run(() => handler.Dispatch("{\"op\":\"active_document\"}"));

                Assert.True(runtime.WaitUntilEntered(TimeSpan.FromSeconds(10)));
                runtime.Release();
                var responses = await Task.WhenAll(first, second);

                Assert.All(responses, response => Assert.True(response.Success));
                var contexts = runtime.Contexts.ToArray();
                Assert.Equal(2, contexts.Length);
                Assert.Equal(2, contexts.Select(context => context.CorrelationId).Distinct().Count());
                var terminals = Terminals(sink).ToArray();
                Assert.Equal(2, terminals.Length);
                Assert.Equal(
                    contexts.Select(context => context.CorrelationId).OrderBy(value => value),
                    terminals.Select(terminal => terminal.CorrelationId).OrderBy(value => value));
                Assert.All(terminals,
                    terminal => Assert.Equal(BimDiagnosticOutcome.Success, terminal.Outcome));
            }
        }

        [Fact]
        public void Dispatch_EnabledHttpDiagnosticMergesRequestEvidenceIntoPhase2Object()
        {
            var sink = new RecordingSink();
            var session = new BimDiagnosticSession(true, sink);
            var runtime = new StatusRuntime();

            using (BimDiagnostics.PushSessionForTests(session))
            using (InstallRuntime(runtime))
            {
                var response = new BimHandler(() => true)
                    .Dispatch("{\"op\":\"status\"}");
                var diagnostic = ToJsonElement(response.Diagnostic);

                Assert.Equal("not_rhino_inside", diagnostic.GetProperty("reasonCode").GetString());
                Assert.Equal("host_blocked", diagnostic.GetProperty("failureKind").GetString());
                Assert.Equal("/capabilities",
                    diagnostic.GetProperty("diagnosticRoute").GetProperty("path").GetString());
                Assert.False(string.IsNullOrWhiteSpace(
                    diagnostic.GetProperty("correlationId").GetString()));
                Assert.Equal("handler.serialize", diagnostic.GetProperty("lastStage").GetString());
                Assert.Equal("success", diagnostic.GetProperty("lastOutcome").GetString());
                Assert.Equal(0, diagnostic.GetProperty("requestDroppedCount").GetInt64());
                Assert.True(diagnostic.GetProperty("traceComplete").GetBoolean());
                Assert.Equal("ready", diagnostic.GetProperty("sinkState").GetString());
                Assert.Equal(0, diagnostic.GetProperty("droppedCount").GetInt64());
            }
        }

        [Fact]
        public void Dispatch_DisabledHttpDiagnosticPreservesPhase2ShapeWithoutRequestFields()
        {
            var session = new BimDiagnosticSession(false, null);

            using (BimDiagnostics.PushSessionForTests(session))
            {
                var response = new BimHandler(() => false)
                    .Dispatch("{\"op\":\"status\"}");
                var diagnostic = ToJsonElement(response.Diagnostic);

                Assert.Equal("not_rhino_inside", diagnostic.GetProperty("reasonCode").GetString());
                Assert.Equal("host_blocked", diagnostic.GetProperty("failureKind").GetString());
                Assert.Equal("/capabilities",
                    diagnostic.GetProperty("diagnosticRoute").GetProperty("path").GetString());
                foreach (var field in RequestDiagnosticFields)
                {
                    Assert.False(diagnostic.TryGetProperty(field, out _), field);
                }
            }
        }

        [Fact]
        public void Dispatch_StatusAlwaysIncludesEightProvenanceAndSinkFields()
        {
            foreach (var enabled in new[] { false, true })
            {
                var sink = enabled ? new RecordingSink() : null;
                var session = new BimDiagnosticSession(enabled, sink);
                using (BimDiagnostics.PushSessionForTests(session))
                {
                    var response = new BimHandler(() => false)
                        .Dispatch("{\"op\":\"status\"}");
                    var data = ToJsonElement(response.Data);

                    Assert.Equal(JsonValueKind.String, data.GetProperty("coreVersion").ValueKind);
                    Assert.Equal(JsonValueKind.String, data.GetProperty("coreCommit").ValueKind);
                    Assert.Equal(JsonValueKind.String, data.GetProperty("moduleVersion").ValueKind);
                    Assert.Equal(JsonValueKind.String, data.GetProperty("moduleCommit").ValueKind);
                    Assert.Equal(enabled, data.GetProperty("diagnosticsEnabled").GetBoolean());
                    Assert.Equal(enabled ? "ready" : "disabled",
                        data.GetProperty("sinkState").GetString());
                    Assert.Equal(0, data.GetProperty("droppedCount").GetInt64());
                    Assert.Equal("none", data.GetProperty("sinkFailureCode").GetString());
                }
            }
        }

        [Fact]
        public void InitializeFromEnvironment_NestedTestScopesRestoreLifoAcrossDispatch()
        {
            var outerSink = new RecordingSink();
            var outer = new BimDiagnosticSession(true, outerSink);
            var inner = new BimDiagnosticSession(false, null);

            using (BimDiagnostics.PushSessionForTests(outer))
            {
                using (BimDiagnostics.PushSessionForTests(inner))
                {
                    var innerResponse = new BimHandler(() => false)
                        .Dispatch("{\"op\":\"status\"}");
                    Assert.False(ToJsonElement(innerResponse.Data)
                        .GetProperty("diagnosticsEnabled").GetBoolean());
                }

                var outerResponse = new BimHandler(() => false)
                    .Dispatch("{\"op\":\"status\"}");
                Assert.True(ToJsonElement(outerResponse.Data)
                    .GetProperty("diagnosticsEnabled").GetBoolean());
                Assert.Single(Terminals(outerSink));
            }
        }

        [Fact]
        public void InitializeFromEnvironment_AfterTestScopeUsesProductionSessionAgain()
        {
            BimDiagnostics.InitializeFromEnvironment();
            var productionEnabled = BimDiagnostics.SnapshotStatus().Enabled;
            var replacement = new BimDiagnosticSession(!productionEnabled,
                productionEnabled ? null : new RecordingSink());

            using (BimDiagnostics.PushSessionForTests(replacement))
            {
                BimDiagnostics.InitializeFromEnvironment();
                Assert.Equal(!productionEnabled, BimDiagnostics.SnapshotStatus().Enabled);
            }

            BimDiagnostics.InitializeFromEnvironment();
            Assert.Equal(productionEnabled, BimDiagnostics.SnapshotStatus().Enabled);
        }

        [Fact]
        public void Source_HasOneAcceptedCompletionAndNoDisabledContextScaffold()
        {
            var source = ReadSourceFile("src", "Rook", "Handlers", "BimHandler.cs");
            var dispatch = ExtractFunctionBySignature(source, "public ApiResponse Dispatch(");

            Assert.Equal(1, CountOccurrences(source, "CompleteRequest("));
            Assert.Equal(1, CountOccurrences(dispatch, "CompleteRequest("));
            Assert.Contains("finally", dispatch);
            Assert.True(dispatch.IndexOf("finally", StringComparison.Ordinal) <
                dispatch.IndexOf("CompleteRequest(", StringComparison.Ordinal));
            Assert.DoesNotContain("Task 5 temporary migration scaffold", source);
            Assert.DoesNotContain("BimDiagnosticContext.Disabled", dispatch);
            Assert.Equal(1, CountOccurrences(dispatch, "CreateContext("));
            Assert.True(dispatch.IndexOf("InitializeFromEnvironment()", StringComparison.Ordinal) <
                dispatch.IndexOf("ParseObjectBody(body)", StringComparison.Ordinal));
            Assert.True(dispatch.IndexOf("CreateUncorrelatedContext(\"unparsed\")",
                StringComparison.Ordinal) <
                dispatch.IndexOf("ParseObjectBody(body)", StringComparison.Ordinal));
        }

        [Fact]
        public void Source_CentralizesEveryToWireDataEntryBehindSerializeForWire()
        {
            var source = ReadSourceFile("src", "Rook", "Handlers", "BimHandler.cs");
            var wrapper = ExtractFunctionBySignature(source,
                "private JsonNode? SerializeForWire(");

            Assert.Equal(1, CountOccurrences(source, "ToWireData("));
            Assert.Equal(0, CountOccurrences(wrapper, "ToWireData("));
            Assert.Contains("wireSerializer", wrapper);
            Assert.DoesNotContain("SerializeBimDispatchEnvelope", source);

            var fallback = ExtractFunctionBySignature(source,
                "private ApiResponse BuildMinimalInternalError(");
            Assert.DoesNotContain("SerializeForWire(", fallback);
            Assert.DoesNotContain("ToWireData(", fallback);
            Assert.DoesNotContain("Fail(", fallback);
        }

        private static IEnumerable<BimDiagnosticEnvelope> Terminals(RecordingSink sink)
        {
            return sink.Envelopes.Where(envelope =>
                envelope.Kind == BimDiagnosticRecordKind.Terminal);
        }

        private static IDisposable InstallRuntime(IRookBimRuntime runtime)
        {
            RookBimRuntimeRegistry.Install(runtime, "diagnostics-test");
            return new ActionOnDispose(RookBimRuntimeRegistry.ResetForTests);
        }

        private static JsonElement ToJsonElement(object? value)
        {
            var json = JsonSerializer.Serialize(value);
            using var document = JsonDocument.Parse(json);
            return document.RootElement.Clone();
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var directory = new DirectoryInfo(AppContext.BaseDirectory);
            while (directory != null)
            {
                var candidate = Path.Combine(directory.FullName, Path.Combine(pathParts));
                if (File.Exists(candidate))
                {
                    return File.ReadAllText(candidate);
                }

                directory = directory.Parent;
            }

            throw new FileNotFoundException(
                "Could not locate source file " + string.Join("/", pathParts));
        }

        private static string ExtractFunctionBySignature(string source, string signature)
        {
            var signatureStart = source.IndexOf(signature, StringComparison.Ordinal);
            Assert.True(signatureStart >= 0, $"Could not find signature '{signature}'.");
            var bodyStart = source.IndexOf('{', signatureStart);
            Assert.True(bodyStart >= 0, $"Could not find function body for '{signature}'.");

            var depth = 0;
            for (var index = bodyStart; index < source.Length; index++)
            {
                if (source[index] == '{')
                {
                    depth++;
                }
                else if (source[index] == '}')
                {
                    depth--;
                    if (depth == 0)
                    {
                        return source.Substring(signatureStart, index - signatureStart + 1);
                    }
                }
            }

            throw new InvalidOperationException($"Could not extract function '{signature}'.");
        }

        private static int CountOccurrences(string value, string token)
        {
            var count = 0;
            var index = 0;
            while ((index = value.IndexOf(token, index, StringComparison.Ordinal)) >= 0)
            {
                count++;
                index += token.Length;
            }

            return count;
        }

        private sealed class RecordingSink : IBimDiagnosticEnvelopeSink
        {
            private readonly object sync = new object();
            private readonly List<BimDiagnosticEnvelope> envelopes =
                new List<BimDiagnosticEnvelope>();

            internal IReadOnlyList<BimDiagnosticEnvelope> Envelopes
            {
                get
                {
                    lock (sync)
                    {
                        return envelopes.ToArray();
                    }
                }
            }

            public bool TryEnqueue(BimDiagnosticEnvelope envelope)
            {
                lock (sync)
                {
                    envelopes.Add(envelope);
                    return true;
                }
            }
        }

        private class RecordingRuntime : IRookBimRuntime
        {
            private readonly ConcurrentQueue<BimDiagnosticContext> contexts =
                new ConcurrentQueue<BimDiagnosticContext>();

            internal IReadOnlyCollection<BimDiagnosticContext> Contexts => contexts.ToArray();

            internal Exception? RuntimeException { get; set; }

            public virtual BimStatusResponse Status(BimDiagnosticContext diagnostics)
            {
                Record(diagnostics);
                return new BimStatusResponse { Available = true, Runtime = "test" };
            }

            public virtual BimApiResponse ActiveDocument(BimDiagnosticContext diagnostics)
            {
                Record(diagnostics);
                if (RuntimeException != null)
                {
                    throw RuntimeException;
                }

                return BimApiResponse.Ok(new JsonObject { ["kind"] = "active_document" });
            }

            public BimApiResponse ListCategories(BimDiagnosticContext diagnostics) =>
                BimApiResponse.Ok(null);

            public BimApiResponse QueryElements(
                BimDiagnosticContext diagnostics,
                BimQueryElementsRequest request) => BimApiResponse.Ok(null);

            public BimApiResponse ElementInfo(
                BimDiagnosticContext diagnostics,
                BimElementRequest request) => BimApiResponse.Ok(null);

            public BimApiResponse ElementParameters(
                BimDiagnosticContext diagnostics,
                BimElementRequest request) => BimApiResponse.Ok(null);

            public BimApiResponse SelectElements(
                BimDiagnosticContext diagnostics,
                BimSelectElementsRequest request) => BimApiResponse.Ok(null);

            public BimApiResponse ClearSelection(BimDiagnosticContext diagnostics) =>
                BimApiResponse.Ok(null);

            public BimApiResponse ExportElements(
                BimDiagnosticContext diagnostics,
                BimExportElementsRequest request) => BimApiResponse.Ok(null);

            public BimApiResponse ExportPreset(
                BimDiagnosticContext diagnostics,
                BimExportPresetRequest request) => BimApiResponse.Ok(null);

            protected void Record(BimDiagnosticContext context)
            {
                contexts.Enqueue(context);
            }
        }

        private sealed class BarrierRuntime : RecordingRuntime
        {
            private readonly CountdownEvent entered;
            private readonly ManualResetEventSlim release = new ManualResetEventSlim(false);

            internal BarrierRuntime(int participantCount)
            {
                entered = new CountdownEvent(participantCount);
            }

            public override BimApiResponse ActiveDocument(BimDiagnosticContext diagnostics)
            {
                Record(diagnostics);
                entered.Signal();
                if (!release.Wait(TimeSpan.FromSeconds(10)))
                {
                    throw new TimeoutException("Concurrent dispatch release timed out.");
                }

                return BimApiResponse.Ok(new JsonObject { ["kind"] = "active_document" });
            }

            internal bool WaitUntilEntered(TimeSpan timeout) => entered.Wait(timeout);

            internal void Release() => release.Set();
        }

        private sealed class StatusRuntime : RecordingRuntime
        {
            public override BimStatusResponse Status(BimDiagnosticContext diagnostics)
            {
                Record(diagnostics);
                return new BimStatusResponse
                {
                    Available = false,
                    Runtime = "rookbim",
                    ErrorCode = "not_rhino_inside",
                    Message = "Host is unavailable.",
                    Host = "unknown",
                    Module = "RookBim.dll",
                };
            }
        }

        private sealed class DetailFailureRuntime : RecordingRuntime
        {
            public override BimApiResponse ActiveDocument(BimDiagnosticContext diagnostics)
            {
                Record(diagnostics);
                return new BimApiResponse
                {
                    Success = false,
                    ErrorCode = BimErrorCode.DocumentMismatch,
                    Message = "Document changed.",
                    HttpStatus = 409,
                    Data = new JsonObject { ["expected"] = "bounded" },
                };
            }
        }

        private sealed class PriorFailureRuntime : RecordingRuntime
        {
            public override BimApiResponse ActiveDocument(BimDiagnosticContext diagnostics)
            {
                Record(diagnostics);
                BimDiagnostics.ObserveException(
                    diagnostics,
                    BimDiagnosticStage.RevitDocumentAcquire,
                    new PriorRuntimeTestException(),
                    new BimDiagnosticFields(
                        BimDiagnosticDetailCode.None,
                        null,
                        BimDiagnosticFailureImpact.Production));
                return BimApiResponse.Ok(new JsonObject { ["kind"] = "active_document" });
            }
        }

        private sealed class HandlerRuntimeTestException : Exception
        {
            internal HandlerRuntimeTestException(string message)
                : base(message)
            {
                HResult = unchecked((int)0x81234567);
            }
        }

        private sealed class HandlerSerializerTestException : Exception
        {
            internal HandlerSerializerTestException(string message)
                : base(message)
            {
                HResult = unchecked((int)0x82345678);
            }
        }

        private sealed class PriorRuntimeTestException : Exception
        {
        }

        private sealed class ActionOnDispose : IDisposable
        {
            private Action? action;

            internal ActionOnDispose(Action action)
            {
                this.action = action;
            }

            public void Dispose()
            {
                Interlocked.Exchange(ref action, null)?.Invoke();
            }
        }
    }
}
