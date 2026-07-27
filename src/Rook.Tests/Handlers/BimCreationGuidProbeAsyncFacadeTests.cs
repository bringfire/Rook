using System;
using System.Linq;
using System.Reflection;
using System.Text;
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
    public sealed class BimCreationGuidProbeAsyncFacadeTests
    {
        [Fact]
        public void StartAndPoll_AreNonblockingSingleSlotAndClearAfterTerminalRead()
        {
            using var release = new ManualResetEventSlim(false);
            var coordinator = Coordinator(body =>
            {
                release.Wait();
                return Success(new JsonObject { ["creation_alias"] = "creation-001" });
            });

            var start = coordinator.Start("begin", null);

            Assert.Equal("accepted", start.State);
            Assert.Equal("pending", coordinator.Poll(start.OperationId).State);
            Assert.Equal("busy", coordinator.Start("abort", null).State);
            release.Set();
            var completed = AwaitTerminal(coordinator, start.OperationId);
            Assert.Equal("completed", completed.State);
            Assert.True(completed.Success);
            Assert.Equal("{\"creation_alias\":\"creation-001\"}", completed.DataJson);
            Assert.Equal("not_found", coordinator.Poll(start.OperationId).State);
        }

        [Theory]
        [InlineData("capture", null)]
        [InlineData("begin", "file_local")]
        [InlineData("CAPTURE", "file_local")]
        [InlineData("capture", "not_a_case")]
        public void Start_RejectsInvalidClosedRequestsWithoutLaunching(string action, string? caseId)
        {
            var launches = 0;
            var coordinator = new BimCreationGuidProbeAsyncCoordinator(
                _ => throw new InvalidOperationException(),
                work => { launches++; Task.Run(work); },
                () => DateTime.UtcNow);

            var result = coordinator.Start(action, caseId);

            Assert.Equal("invalid", result.State);
            Assert.Equal("probe_request_invalid", result.FailureCode);
            Assert.Equal(0, launches);
        }

        [Fact]
        public void WorkerFailure_RetainsOnlyBoundedTypeAndHResult()
        {
            const string secret = "Snowdon Towers C:\\private\\model.rvt 11111111-1111-1111-1111-111111111111";
            var coordinator = Coordinator(_ => throw new FixtureException(secret));

            var start = coordinator.Start("abort", null);
            var poll = AwaitTerminal(coordinator, start.OperationId);

            Assert.Equal("worker_failed", poll.State);
            Assert.Equal("probe_worker_failed", poll.FailureCode);
            Assert.Equal(typeof(FixtureException).FullName, poll.ExceptionType);
            Assert.NotNull(poll.HResult);
            Assert.DoesNotContain(secret, poll.ExceptionType ?? string.Empty, StringComparison.Ordinal);
            Assert.Null(poll.DataJson);
        }

        [Theory]
        [InlineData("capability_unavailable", "capability_unavailable")]
        [InlineData("invalid_scope", "invalid_scope")]
        [InlineData("unknown_host_detail", "internal_error")]
        public void FailedResponse_ProjectsOnlyAllowlistedErrorCode(string input, string expected)
        {
            var response = new ApiResponse
            {
                Success = false,
                HttpStatus = 503,
                Data = new JsonObject
                {
                    ["errorCode"] = input,
                    ["details"] = "C:\\private\\model.rvt",
                },
                Diagnostic = new { model = "Snowdon Towers" },
            };
            var coordinator = Coordinator(_ => response);

            var start = coordinator.Start("begin", null);
            var poll = AwaitTerminal(coordinator, start.OperationId);

            Assert.Equal("completed", poll.State);
            Assert.False(poll.Success);
            Assert.Equal("{\"errorCode\":\"" + expected + "\"}", poll.DataJson);
            Assert.DoesNotContain("private", poll.DataJson!, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("Snowdon", poll.DataJson!, StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void OversizeSuccess_DropsPayloadAndReportsTooLarge()
        {
            var coordinator = Coordinator(_ => Success(
                new JsonObject { ["value"] = new string('x', 262145) }));

            var start = coordinator.Start("complete", null);
            var poll = AwaitTerminal(coordinator, start.OperationId);

            Assert.Equal("completed", poll.State);
            Assert.Equal("probe_response_too_large", poll.FailureCode);
            Assert.Null(poll.DataJson);
        }

        [Fact]
        public void UnexpectedSuccessShape_IsRejected()
        {
            var coordinator = Coordinator(_ => Success(new { unsafeValue = "raw" }));

            var start = coordinator.Start("begin", null);
            var poll = AwaitTerminal(coordinator, start.OperationId);

            Assert.Equal("probe_response_shape_invalid", poll.FailureCode);
            Assert.Null(poll.DataJson);
        }

        [Fact]
        public void Watchdog_IsStickyRetainsSlotAndIgnoresLateCompletion()
        {
            var now = new DateTime(2026, 7, 26, 12, 0, 0, DateTimeKind.Utc);
            using var release = new ManualResetEventSlim(false);
            var coordinator = new BimCreationGuidProbeAsyncCoordinator(
                _ =>
                {
                    release.Wait();
                    return Success(new JsonObject { ["late"] = true });
                },
                work => Task.Run(work),
                () => now);

            var start = coordinator.Start("begin", null);
            now = now.AddSeconds(11);
            var timedOut = coordinator.Poll(start.OperationId);

            Assert.Equal("timed_out", timedOut.State);
            Assert.Equal("probe_worker_timed_out", timedOut.FailureCode);
            Assert.Equal("busy", coordinator.Start("abort", null).State);
            release.Set();
            Assert.True(SpinWait.SpinUntil(
                () => coordinator.Poll(start.OperationId).State == "timed_out",
                TimeSpan.FromSeconds(1)));
            Assert.Equal("timed_out", coordinator.Poll(start.OperationId).State);
        }

        [Fact]
        public void Watchdog_WorkerPublishingAfterDeadlineBeforeFirstPollBecomesStickyTimeout()
        {
            var now = new DateTime(2026, 7, 26, 12, 0, 0, DateTimeKind.Utc);
            using var release = new ManualResetEventSlim(false);
            using var publicationFinished = new ManualResetEventSlim(false);
            var coordinator = new BimCreationGuidProbeAsyncCoordinator(
                _ =>
                {
                    release.Wait();
                    return Success(new JsonObject { ["late"] = true });
                },
                work => Task.Run(() =>
                {
                    work();
                    publicationFinished.Set();
                }),
                () => now);

            var start = coordinator.Start("begin", null);
            now = now.AddSeconds(11);
            release.Set();
            Assert.True(publicationFinished.Wait(TimeSpan.FromSeconds(2)));

            Assert.Equal("timed_out", coordinator.Poll(start.OperationId).State);
            Assert.Equal("busy", coordinator.Start("abort", null).State);
            Assert.Equal("timed_out", coordinator.Poll(start.OperationId).State);
        }

        [Fact]
        public void Watchdog_TerminalPublishedBeforeDeadlineRemainsTerminalWhenPolledLater()
        {
            var now = new DateTime(2026, 7, 26, 12, 0, 0, DateTimeKind.Utc);
            using var release = new ManualResetEventSlim(false);
            using var publicationFinished = new ManualResetEventSlim(false);
            var coordinator = new BimCreationGuidProbeAsyncCoordinator(
                _ =>
                {
                    release.Wait();
                    return Success(new JsonObject { ["on_time"] = true });
                },
                work => Task.Run(() =>
                {
                    work();
                    publicationFinished.Set();
                }),
                () => now);

            var start = coordinator.Start("begin", null);
            now = now.AddSeconds(9);
            release.Set();
            Assert.True(publicationFinished.Wait(TimeSpan.FromSeconds(2)));
            now = now.AddSeconds(2);

            var completed = coordinator.Poll(start.OperationId);
            Assert.Equal("completed", completed.State);
            Assert.Equal("{\"on_time\":true}", completed.DataJson);
            Assert.Equal("not_found", coordinator.Poll(start.OperationId).State);
        }

        [Fact]
        public void SlotType_DoesNotRetainForbiddenRawObjects()
        {
            var slot = typeof(BimCreationGuidProbeAsyncCoordinator)
                .GetNestedTypes(BindingFlags.NonPublic)
                .Single(type => type.Name.IndexOf("Slot", StringComparison.Ordinal) >= 0);

            var fieldTypes = slot.GetFields(BindingFlags.Instance |
                BindingFlags.Public | BindingFlags.NonPublic).Select(field => field.FieldType).ToArray();

            Assert.DoesNotContain(fieldTypes, type => typeof(Exception).IsAssignableFrom(type));
            Assert.DoesNotContain(fieldTypes, type => typeof(ApiResponse).IsAssignableFrom(type));
            Assert.DoesNotContain(fieldTypes, type => typeof(Delegate).IsAssignableFrom(type));
            Assert.DoesNotContain(fieldTypes, type => type == typeof(Task<ApiResponse>));
        }

        [Theory]
        [InlineData(false, 0, false, "{\"errorCode\":\"capability_unavailable\"}")]
        [InlineData(true, 1, true, "{\"creation_alias\":\"creation-001\"}")]
        public void Coordinator_ThroughActualHandlerPreservesGateAndSafeProjection(
            bool enabled, int expectedCalls, bool expectedSuccess, string expectedJson)
        {
            var runtime = new ProbeRuntime();
            RookBimRuntimeRegistry.Install(runtime, "async-probe-test");
            try
            {
                using (BimDiagnostics.PushSessionForTests(new BimDiagnosticSession(enabled, null)))
                {
                    var coordinator = Coordinator(body => new BimHandler(() => true).Dispatch(body));

                    var start = coordinator.Start("begin", null);
                    var terminal = AwaitTerminal(coordinator, start.OperationId);

                    Assert.Equal("completed", terminal.State);
                    Assert.Equal(expectedSuccess, terminal.Success);
                    Assert.Equal(expectedJson, terminal.DataJson);
                    Assert.Equal(expectedCalls, runtime.Calls);
                }
            }
            finally
            {
                RookBimRuntimeRegistry.ResetForTests();
            }
        }

        private static BimCreationGuidProbeAsyncCoordinator Coordinator(Func<string, ApiResponse> dispatch)
        {
            return new BimCreationGuidProbeAsyncCoordinator(
                dispatch,
                work => Task.Run(work),
                () => DateTime.UtcNow);
        }

        private static BimCreationGuidProbeAsyncPoll AwaitTerminal(
            BimCreationGuidProbeAsyncCoordinator coordinator,
            string operationId)
        {
            BimCreationGuidProbeAsyncPoll? terminal = null;
            Assert.True(SpinWait.SpinUntil(() =>
            {
                var current = coordinator.Poll(operationId);
                if (current.State == "pending")
                {
                    return false;
                }

                terminal = current;
                return true;
            }, TimeSpan.FromSeconds(2)));
            return terminal!;
        }

        private static ApiResponse Success(object data) => new ApiResponse
        {
            Success = true,
            HttpStatus = 200,
            Data = data,
        };

        private sealed class FixtureException : Exception
        {
            internal FixtureException(string message) : base(message) { }
        }

        private sealed class ProbeRuntime : IRookBimRuntime
        {
            internal int Calls { get; private set; }

            public BimApiResponse CreationGuidProbe(BimDiagnosticContext diagnostics,
                BimCreationGuidProbeRequest request)
            {
                Calls++;
                return BimApiResponse.Ok(new JsonObject
                {
                    ["creation_alias"] = "creation-001",
                });
            }

            public BimStatusResponse Status(BimDiagnosticContext diagnostics) => new BimStatusResponse();
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
    }
}
