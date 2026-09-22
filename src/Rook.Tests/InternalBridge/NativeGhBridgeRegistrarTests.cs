using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using Rook;
using Rook.Handlers;
using Rook.InternalBridge;
using Rook.Services.Vision;
using Xunit;

namespace Rook.Tests.InternalBridge
{
    public class NativeGhBridgeRegistrarTests
    {
        [Fact]
        public void MapBridgeStatus_NullHttpStatus_SuccessTrue_FallsBackTo200()
        {
            var result = new ApiResponse { Success = true, Data = "ok", HttpStatus = null };
            Assert.Equal(200, NativeGhBridgeRegistrar.MapBridgeStatus(result));
        }

        [Fact]
        public void MapBridgeStatus_NullHttpStatus_SuccessFalse_FallsBackTo400()
        {
            var result = new ApiResponse { Success = false, Data = "bad", HttpStatus = null };
            Assert.Equal(400, NativeGhBridgeRegistrar.MapBridgeStatus(result));
        }

        [Fact]
        public void MapBridgeStatus_DefaultApiResponse_FallsBackTo400()
        {
            // Brand-new ApiResponse: Success defaults to false, HttpStatus
            // defaults to null. This is the legacy contract image-side
            // handlers depend on; pinned so it cannot regress.
            Assert.Equal(400, NativeGhBridgeRegistrar.MapBridgeStatus(new ApiResponse()));
        }

        [Fact]
        public void QueryDocumentForBridge_NotReady_ReturnsStructuredFailure()
        {
            var result = NativeGhBridgeRegistrar.QueryDocumentForBridge("{}");

            AssertGrasshopperNotReady(result, "gh_query");
        }

        [Fact]
        public void DocumentForBridge_NotReady_DoesNotCreateDocument()
        {
            var result = NativeGhBridgeRegistrar.DocumentForBridge("{}");

            AssertGrasshopperNotReady(result, "gh_document");
        }

        [Fact]
        public void ErrorsForBridge_NotReady_ReturnsStructuredFailure()
        {
            var result = NativeGhBridgeRegistrar.ErrorsForBridge("{}");

            AssertGrasshopperNotReady(result, "gh_errors");
        }

        [Fact]
        public void CreatePanelForBridge_NotReady_ReturnsStructuredFailure()
        {
            var result = NativeGhBridgeRegistrar.CreatePanelForBridge("{}");

            AssertGrasshopperNotReady(result, "gh_create_panel");
        }

        [Fact]
        public void CreateSliderForBridge_NotReady_ReturnsStructuredFailure()
        {
            var result = NativeGhBridgeRegistrar.CreateSliderForBridge("{}");

            AssertGrasshopperNotReady(result, "gh_create_slider");
        }

        [Fact]
        public void ConnectForBridge_NotReady_ReturnsStructuredFailure()
        {
            var result = NativeGhBridgeRegistrar.ConnectForBridge("{}");

            AssertGrasshopperNotReady(result, "gh_connect");
        }

        [Fact]
        public void SetValueForBridge_NotReady_ReturnsStructuredFailure()
        {
            var result = NativeGhBridgeRegistrar.SetValueForBridge("{}");

            AssertGrasshopperNotReady(result, "gh_set_value");
        }

        [Fact]
        public void GrasshopperHandler_OnlyLifecycleRoutesPermitMissingDocument()
        {
            var sourcePath = Path.GetFullPath(Path.Combine(
                AppContext.BaseDirectory,
                "..",
                "..",
                "..",
                "..",
                "Rook",
                "Handlers",
                "GrasshopperHandler.cs"));
            var source = File.ReadAllText(sourcePath);
            Assert.DoesNotContain("createDocumentIfMissing", source);
            var permissiveCalls = Regex.Matches(source, @"GetGrasshopper\(requireDocument:\s*false\)")
                .Cast<Match>()
                .Select(match => new
                {
                    Method = FindContainingMethodName(source, match.Index),
                    Line = source.Take(match.Index).Count(ch => ch == '\n') + 1,
                })
                .ToArray();

            var actualMethods = permissiveCalls.Select(call => call.Method).ToHashSet();
            var expectedMethods = new[] { "OpenDocument", "NewDocument" }.ToHashSet();
            var callSummary = string.Join(
                ", ",
                permissiveCalls.Select(call => $"{call.Method}:L{call.Line}"));

            Assert.True(
                expectedMethods.SetEquals(actualMethods),
                $"Only lifecycle routes may resolve context without requiring a document. Found: {callSummary}");
        }

        [Fact]
        public void Batch_component_info_bridge_forwards_the_exact_request_body_once()
        {
            var source = ReadRegistrarSource();
            const string exactForwarder =
                "requestJson => Handler.HandleBatchComponentInfo(requestJson)";

            Assert.Single(Regex.Matches(source, Regex.Escape(exactForwarder)).Cast<Match>());
        }

        [Fact]
        public void OpenDocument_PreflightRunsBeforeTheSingleUiBoundary()
        {
            var method = ExtractMethod(ReadRegistrarSource(), "private static int HandleOpenDocument");
            var read = method.IndexOf("ReadUtf8(requestJsonUtf8, requestJsonLength)", StringComparison.Ordinal);
            var preflight = method.IndexOf("GrasshopperHandler.PreflightOpenDocument(requestJson)", StringComparison.Ordinal);
            var uiBoundary = method.IndexOf("ExecuteApiResponseCallback(", StringComparison.Ordinal);

            Assert.True(read >= 0);
            Assert.True(preflight > read);
            Assert.True(uiBoundary > preflight);
            Assert.Contains("WriteUtf8Response(", method);
            Assert.DoesNotContain("RhinoApp.InvokeOnUiThread", method);
        }

        [Fact]
        public void ReadinessWait_UsesDedicatedOffUiExecutor()
        {
            var method = ExtractMethod(
                ReadRegistrarSource(),
                "private static int HandleWaitForSolveReadiness");

            Assert.Contains("ExecuteReadinessWaitCallback", method);
            AssertReadinessCodeStaysDirect(method);
        }

        [Fact]
        public void ReadinessStatus_UsesDedicatedOffUiExecutor()
        {
            var method = ExtractMethod(
                ReadRegistrarSource(),
                "private static int HandleSolveReadiness");

            Assert.Contains("ExecuteReadinessStatusCallback", method);
            AssertReadinessCodeStaysDirect(method);
        }

        [Fact]
        public void InspectOutputCallback_ForwardsOptionalReadinessReceipt()
        {
            var method = ExtractMethod(
                ReadRegistrarSource(),
                "internal static ApiResponse InspectOutputForBridge");

            Assert.Contains("GetStringArg(args, \"readiness_receipt_id\")", method);
        }

        [Theory]
        [InlineData("{\"guid\":\"COMPONENT\",\"param\":\"Result\",\"outputIndex\":0}", "selector")]
        [InlineData("{\"guid\":\"COMPONENT\",\"param\":null,\"outputIndex\":0}", "selector")]
        [InlineData("{\"guid\":\"COMPONENT\",\"param\":null}", "param")]
        [InlineData("{\"guid\":\"COMPONENT\",\"outputIndex\":null}", "outputIndex")]
        public void InspectOutputForBridge_InvalidSelectorReturnsStructured400BeforeHandler(
            string requestJson,
            string expectedField)
        {
            var response = NativeGhBridgeRegistrar.InspectOutputForBridge(requestJson);

            Assert.False(response.Success);
            Assert.Equal(400, response.HttpStatus);
            var data = JsonSerializer.SerializeToElement(response.Data);
            Assert.Equal("invalid_request", data.GetProperty("code").GetString());
            Assert.Equal(expectedField, data.GetProperty("field").GetString());
        }

        [Fact]
        public void ReadinessExecutors_RunDirectlyWithoutUiDispatchOrWorkerHop()
        {
            var callerThread = Thread.CurrentThread.ManagedThreadId;
            int? statusThread = null;
            int? waitThread = null;

            InvokeReadinessExecutorForTests("ExecuteReadinessStatusForTests", () =>
            {
                statusThread = Thread.CurrentThread.ManagedThreadId;
                return new ApiResponse { Success = true, Data = new { status = "ready" } };
            });
            InvokeReadinessExecutorForTests("ExecuteReadinessWaitForTests", () =>
            {
                waitThread = Thread.CurrentThread.ManagedThreadId;
                return new ApiResponse { Success = true, Data = new { wait_status = "ready" } };
            });

            Assert.Equal(callerThread, statusThread);
            Assert.Equal(callerThread, waitThread);
        }

        [Fact]
        public void ReadinessWait_MaximumTimeoutReachesManagedHandlerUnchanged()
        {
            string? observedReceiptId = null;
            int? observedTimeoutMs = null;
            var method = typeof(NativeGhBridgeRegistrar).GetMethod(
                "ExecuteReadinessWaitForTests",
                BindingFlags.Static | BindingFlags.NonPublic,
                binder: null,
                types: new[] { typeof(string), typeof(Func<string, int, ApiResponse>) },
                modifiers: null);
            Assert.NotNull(method);

            var result = Assert.IsType<ApiResponse>(method!.Invoke(null, new object[]
            {
                "{\"readiness_receipt_id\":\"opaque-maximum\",\"timeout_ms\":300000}",
                new Func<string?, int, ApiResponse>((receiptId, timeoutMs) =>
                {
                    observedReceiptId = receiptId;
                    observedTimeoutMs = timeoutMs;
                    return new ApiResponse { Success = true, Data = new { wait_status = "terminal" } };
                }),
            }));

            Assert.True(result.Success);
            Assert.Equal("opaque-maximum", observedReceiptId);
            Assert.Equal(300000, observedTimeoutMs);
        }

        [Theory]
        [InlineData(0)]
        [InlineData(-1)]
        [InlineData(300001)]
        public void ReadinessWait_OutOfRangeTimeoutDoesNotInvokeManagedHandler(int timeoutMs)
        {
            var invoked = false;
            var result = InvokeReadinessWaitRequestForTests(
                $"{{\"readiness_receipt_id\":\"opaque-invalid\",\"timeout_ms\":{timeoutMs}}}",
                (_, __) =>
                {
                    invoked = true;
                    return new ApiResponse { Success = true };
                });

            Assert.False(invoked);
            Assert.False(result.Success);
            Assert.Equal(
                "readiness_timeout_ms_out_of_range",
                result.Data?.GetType().GetProperty("error")?.GetValue(result.Data));
        }

        [Fact]
        public void ReadinessDirectCallback_PropagatesStructuredDataAndExactStatus()
        {
            var result = InvokeDirectReadinessCallbackForTests(new ApiResponse
            {
                Success = false,
                HttpStatus = 422,
                Data = new
                {
                    error = "readiness_timeout_ms_out_of_range",
                    details = new { minimum = 1, maximum = 300000 },
                },
            });

            Assert.Equal(0, result.ReturnCode);
            Assert.Equal(422, result.HttpStatusCode);
            using var response = JsonDocument.Parse(result.ResponseJson);
            Assert.False(response.RootElement.GetProperty("success").GetBoolean());
            var data = response.RootElement.GetProperty("data");
            Assert.Equal("readiness_timeout_ms_out_of_range", data.GetProperty("error").GetString());
            Assert.Equal(1, data.GetProperty("details").GetProperty("minimum").GetInt32());
            Assert.Equal(300000, data.GetProperty("details").GetProperty("maximum").GetInt32());
        }

        [Fact]
        public void ReadinessRoutes_AppendAbi18Callbacks()
        {
            var registrar = ReadRegistrarSource();
            var nativeProxy = ReadNativeProxySource();

            Assert.Contains("private const uint BridgeAbiVersion = 18", registrar);
            Assert.Contains("constexpr uint32_t kGhBridgeAbiVersion = 18", nativeProxy);
            AssertStructTail(
                ExtractTypeBody(registrar, "private struct NativeGhBridgeRegistration"),
                "public IntPtr GhSolveReadiness;",
                "public IntPtr GhWaitForSolveReadiness;");
            AssertStructTail(
                ExtractTypeBody(nativeProxy, "struct GhBridgeRegistration"),
                "GhBridgeCallbackFn gh_solve_readiness = nullptr;",
                "GhBridgeCallbackFn gh_wait_for_solve_readiness = nullptr;");

            Assert.Contains("SolveReadinessCallback = HandleSolveReadiness", registrar);
            Assert.Contains("WaitForSolveReadinessCallback = HandleWaitForSolveReadiness", registrar);
            Assert.Contains("GhSolveReadiness = Marshal.GetFunctionPointerForDelegate(SolveReadinessCallback)", registrar);
            Assert.Contains("GhWaitForSolveReadiness = Marshal.GetFunctionPointerForDelegate(WaitForSolveReadinessCallback)", registrar);

            var registrationCheck = ExtractMethod(
                nativeProxy,
                "bool HasGrasshopperCoreRegistrationLocked");
            Assert.Contains("registration.gh_solve_readiness != nullptr", registrationCheck);
            Assert.Contains("registration.gh_wait_for_solve_readiness != nullptr", registrationCheck);

            var registerExport = ExtractMethod(
                nativeProxy,
                "int __stdcall RookRegisterGhBridge");
            Assert.Contains("ValidateGhBridgeRegistration", registerExport);
        }

        [Fact]
        public void ReadinessProxyAndServerRoutes_AreWiredExactly()
        {
            var root = FindRepoRoot();
            var nativeProxy = ReadNativeProxySource();
            var nativeProxyHeader = File.ReadAllText(Path.Combine(
                root, "src", "RookNative", "Handlers", "GrasshopperProxyHandler.h"));
            var server = File.ReadAllText(Path.Combine(root, "src", "RookNative", "RookServer.cpp"));
            var serverHeader = File.ReadAllText(Path.Combine(root, "src", "RookNative", "RookServer.h"));

            Assert.Contains("void HandleGrasshopperSolveReadiness", nativeProxyHeader);
            Assert.Contains("void HandleGrasshopperWaitForSolveReadiness", nativeProxyHeader);
            Assert.Contains("void HandleGrasshopperSolveReadiness", serverHeader);
            Assert.Contains("void HandleGrasshopperWaitForSolveReadiness", serverHeader);

            var statusProxy = ExtractMethod(nativeProxy, "void HandleGrasshopperSolveReadiness");
            Assert.Contains("DispatchGrasshopperRoute", statusProxy);
            Assert.Contains("\"/gh/solve-readiness\"", statusProxy);
            Assert.Contains("registration.gh_solve_readiness", statusProxy);

            var waitProxy = ExtractMethod(nativeProxy, "void HandleGrasshopperWaitForSolveReadiness");
            Assert.Contains("DispatchGrasshopperRoute", waitProxy);
            Assert.Contains("\"/gh/wait-for-solve-readiness\"", waitProxy);
            Assert.Contains("registration.gh_wait_for_solve_readiness", waitProxy);

            Assert.Contains("ghGet(\"/gh/solve-readiness\"", server);
            Assert.Contains("HandleGrasshopperSolveReadiness(req, res);", server);
            Assert.Contains("ghPost(\"/gh/wait-for-solve-readiness\"", server);
            Assert.Contains("HandleGrasshopperWaitForSolveReadiness(req, res);", server);
        }

        [Fact]
        public void ReadinessHandlersAndExecutors_StayOffUiAndNonPolling()
        {
            var source = ReadRegistrarSource();
            var methodSignatures = new[]
            {
                "private static int HandleSolveReadiness",
                "private static int HandleWaitForSolveReadiness",
                "private static ApiResponse ExecuteReadinessStatusCallback",
                "private static ApiResponse ExecuteReadinessWaitCallback",
                "private static int ExecuteDirectReadinessCallback",
            };

            foreach (var signature in methodSignatures)
            {
                AssertReadinessCodeStaysDirect(ExtractMethod(source, signature));
            }

            var directSerializer = ExtractMethod(
                source,
                "private static int ExecuteDirectReadinessCallback");
            Assert.Contains("MapBridgeStatus(result)", directSerializer);
        }

        private static void AssertGrasshopperNotReady(ApiResponse result, string operation)
        {
            Assert.False(result.Success);
            Assert.NotNull(result.Data);

            var dataType = result.Data!.GetType();
            Assert.Equal(
                "grasshopper_not_ready",
                dataType.GetProperty("error")?.GetValue(result.Data));
            Assert.Equal(
                false,
                dataType.GetProperty("ready_for_edit")?.GetValue(result.Data));
            Assert.Equal(
                false,
                dataType.GetProperty("verified")?.GetValue(result.Data));
            Assert.Equal(
                operation,
                dataType.GetProperty("operation")?.GetValue(result.Data));
            Assert.NotNull(dataType.GetProperty("errors")?.GetValue(result.Data));
            Assert.NotNull(dataType.GetProperty("message")?.GetValue(result.Data));
            Assert.NotNull(dataType.GetProperty("verification_note")?.GetValue(result.Data));
            Assert.NotNull(dataType.GetProperty("status")?.GetValue(result.Data));
        }

        private static string FindContainingMethodName(string source, int index)
        {
            var beforeCall = source.Substring(0, index);
            var matches = Regex.Matches(
                beforeCall,
                @"(?:public|private|internal)\s+[^\r\n{;=]+?\s+(?<name>[A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*\{",
                RegexOptions.Singleline);

            return matches.Count == 0
                ? "<unknown>"
                : matches[matches.Count - 1].Groups["name"].Value;
        }

        private static string FindRepoRoot()
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir is not null)
            {
                if (File.Exists(Path.Combine(dir.FullName, "Rook.sln")))
                    return dir.FullName;
                dir = dir.Parent;
            }
            throw new DirectoryNotFoundException("Could not locate Rook.sln from test output directory.");
        }

        private static string ReadRegistrarSource() => File.ReadAllText(Path.Combine(
            FindRepoRoot(),
            "src",
            "Rook",
            "InternalBridge",
            "NativeGhBridgeRegistrar.cs"));

        private static string ReadNativeProxySource() => File.ReadAllText(Path.Combine(
            FindRepoRoot(),
            "src",
            "RookNative",
            "Handlers",
            "GrasshopperProxyHandler.cpp"));

        private static string ExtractMethod(string source, string signature)
        {
            var signatureIndex = source.IndexOf(signature, StringComparison.Ordinal);
            Assert.True(signatureIndex >= 0, $"Could not find method: {signature}");

            var bodyStart = source.IndexOf('{', signatureIndex);
            Assert.True(bodyStart > signatureIndex, $"Could not find method body: {signature}");

            var depth = 0;
            for (var index = bodyStart; index < source.Length; index++)
            {
                if (source[index] == '{')
                {
                    depth++;
                }
                else if (source[index] == '}' && --depth == 0)
                {
                    return source.Substring(signatureIndex, index - signatureIndex + 1);
                }
            }

            throw new Xunit.Sdk.XunitException($"Unterminated method body: {signature}");
        }

        private static string ExtractTypeBody(string source, string declaration)
        {
            var declarationIndex = source.IndexOf(declaration, StringComparison.Ordinal);
            Assert.True(declarationIndex >= 0, $"Could not find type: {declaration}");

            var bodyStart = source.IndexOf('{', declarationIndex);
            Assert.True(bodyStart > declarationIndex, $"Could not find type body: {declaration}");

            var depth = 0;
            for (var index = bodyStart; index < source.Length; index++)
            {
                if (source[index] == '{')
                {
                    depth++;
                }
                else if (source[index] == '}' && --depth == 0)
                {
                    return source.Substring(bodyStart + 1, index - bodyStart - 1);
                }
            }

            throw new Xunit.Sdk.XunitException($"Unterminated type body: {declaration}");
        }

        private static void AssertStructTail(string body, string penultimateField, string finalField)
        {
            var statements = body
                .Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries)
                .Select(line => line.Trim())
                .Where(line => line.EndsWith(";", StringComparison.Ordinal))
                .ToArray();

            Assert.True(statements.Length >= 2, "Expected at least two fields in the registration structure.");
            Assert.Equal(penultimateField, statements[statements.Length - 2]);
            Assert.Equal(finalField, statements[statements.Length - 1]);
        }

        private static void AssertReadinessCodeStaysDirect(string source)
        {
            var forbidden = new[]
            {
                "ExecuteApiResponseCallback",
                "DocumentContext.WithDocument",
                "RhinoApp.InvokeOnUiThread",
                "Task.Run",
                "Thread.Sleep",
                "Task.Delay",
                "System.Threading.Timer",
                "while (",
                "for (",
            };

            foreach (var token in forbidden)
            {
                Assert.DoesNotContain(token, source, StringComparison.Ordinal);
            }
        }

        private static ApiResponse InvokeReadinessExecutorForTests(
            string methodName,
            Func<ApiResponse> operation)
        {
            var method = typeof(NativeGhBridgeRegistrar).GetMethod(
                methodName,
                BindingFlags.Static | BindingFlags.NonPublic,
                binder: null,
                types: new[] { typeof(Func<ApiResponse>) },
                modifiers: null);
            Assert.NotNull(method);

            return Assert.IsType<ApiResponse>(method!.Invoke(null, new object[] { operation }));
        }

        private static ApiResponse InvokeReadinessWaitRequestForTests(
            string requestJson,
            Func<string?, int, ApiResponse> operation)
        {
            var method = typeof(NativeGhBridgeRegistrar).GetMethod(
                "ExecuteReadinessWaitForTests",
                BindingFlags.Static | BindingFlags.NonPublic,
                binder: null,
                types: new[] { typeof(string), typeof(Func<string, int, ApiResponse>) },
                modifiers: null);
            Assert.NotNull(method);

            return Assert.IsType<ApiResponse>(method!.Invoke(null, new object[] { requestJson, operation }));
        }

        private static DirectCallbackResult InvokeDirectReadinessCallbackForTests(ApiResponse apiResponse)
        {
            const int responseCapacity = 4096;
            var requestBytes = Encoding.UTF8.GetBytes("{}");
            var requestBuffer = Marshal.AllocHGlobal(requestBytes.Length);
            var responseBuffer = Marshal.AllocHGlobal(responseCapacity);
            var responseLength = Marshal.AllocHGlobal(sizeof(int));
            var httpStatusCode = Marshal.AllocHGlobal(sizeof(int));

            try
            {
                Marshal.Copy(requestBytes, 0, requestBuffer, requestBytes.Length);
                Marshal.WriteInt32(responseLength, 0);
                Marshal.WriteInt32(httpStatusCode, 0);

                var method = typeof(NativeGhBridgeRegistrar).GetMethod(
                    "ExecuteDirectReadinessCallback",
                    BindingFlags.Static | BindingFlags.NonPublic,
                    binder: null,
                    types: new[]
                    {
                        typeof(IntPtr),
                        typeof(int),
                        typeof(IntPtr),
                        typeof(int),
                        typeof(IntPtr),
                        typeof(IntPtr),
                        typeof(Func<string, ApiResponse>),
                    },
                    modifiers: null);
                Assert.NotNull(method);

                var returnCode = Assert.IsType<int>(method!.Invoke(null, new object[]
                {
                    requestBuffer,
                    requestBytes.Length,
                    responseBuffer,
                    responseCapacity,
                    responseLength,
                    httpStatusCode,
                    new Func<string, ApiResponse>(_ => apiResponse),
                }));
                var length = Marshal.ReadInt32(responseLength);
                var responseBytes = new byte[length];
                Marshal.Copy(responseBuffer, responseBytes, 0, length);

                return new DirectCallbackResult
                {
                    ReturnCode = returnCode,
                    HttpStatusCode = Marshal.ReadInt32(httpStatusCode),
                    ResponseJson = Encoding.UTF8.GetString(responseBytes),
                };
            }
            finally
            {
                Marshal.FreeHGlobal(requestBuffer);
                Marshal.FreeHGlobal(responseBuffer);
                Marshal.FreeHGlobal(responseLength);
                Marshal.FreeHGlobal(httpStatusCode);
            }
        }

        private sealed class DirectCallbackResult
        {
            public int ReturnCode { get; set; }
            public int HttpStatusCode { get; set; }
            public string ResponseJson { get; set; } = string.Empty;
        }

        private static string ExtractSwitchArm(string source, string caseLabel)
        {
            var caseIndex = source.IndexOf(caseLabel, StringComparison.Ordinal);
            Assert.True(caseIndex >= 0, $"Could not find switch case: {caseLabel}");

            var nextCaseIndex = source.IndexOf("\n                case ", caseIndex + caseLabel.Length, StringComparison.Ordinal);
            Assert.True(nextCaseIndex > caseIndex, $"Could not find switch case after: {caseLabel}");

            return source.Substring(caseIndex, nextCaseIndex - caseIndex);
        }

        [Theory]
        [InlineData(415)]
        [InlineData(500)]
        [InlineData(503)]
        public void MapBridgeStatus_FailureWithExplicitStatus_HonorsHttpStatus(int explicitStatus)
        {
            var result = new ApiResponse
            {
                Success = false,
                Data = "typed error",
                HttpStatus = explicitStatus,
            };
            Assert.Equal(explicitStatus, NativeGhBridgeRegistrar.MapBridgeStatus(result));
        }

        [Theory]
        [InlineData(200)]
        [InlineData(202)]
        public void MapBridgeStatus_SuccessWithExplicitStatus_HonorsHttpStatus(int explicitStatus)
        {
            // Video Cancelled / Interrupted are terminal-state reads that
            // return Success=true with state metadata in Data. The typed
            // override path must work in either direction (success and
            // failure) so a future caller setting a non-200 success code
            // is not silently downgraded.
            var result = new ApiResponse
            {
                Success = true,
                Data = "ok with explicit status",
                HttpStatus = explicitStatus,
            };
            Assert.Equal(explicitStatus, NativeGhBridgeRegistrar.MapBridgeStatus(result));
        }

        // (Step 8 cleanup) Removed MapBridgeStatus_NullResponse_Returns500.
        // The helper's defensive null guard was unreachable: production
        // callers (the async and off-UI executors) read result.Success
        // for the JSON envelope before invoking the helper. The helper
        // is now tightened; a regression that introduces a null path
        // would NRE earlier and surface as a generic 500 via the
        // executors' outer exception handler.

        // ─── ExpectedVisionOps ───────────────────────────────────────────

        [Theory]
        [InlineData("capture_depth")]
        [InlineData("generate")]
        [InlineData("enhance_prompt")]
        [InlineData("list_artifacts")]
        [InlineData("get_artifact")]
        [InlineData("approve_artifact")]
        [InlineData("delete_artifact")]
        [InlineData("consume_approved")]
        public void ExpectedVisionOps_ContainsAllImageOps(string op)
        {
            // Regression — image ops must continue to route after V2.
            Assert.Contains(op, NativeGhBridgeRegistrar.ExpectedVisionOps);
        }

        [Theory]
        [InlineData(VideoOpHandler.OpSubmit)]
        [InlineData(VideoOpHandler.OpStatus)]
        [InlineData(VideoOpHandler.OpCancel)]
        [InlineData(VideoOpHandler.OpResult)]
        [InlineData(VideoOpHandler.OpEstimate)]
        public void ExpectedVisionOps_ContainsAllV2VideoOps(string op)
        {
            // Pin the five V2 video ops are wired in. If the trampoline
            // switch adds a video op without updating ExpectedVisionOps,
            // the unknown-op rejection message would silently omit it
            // (and an integration test would catch it later, expensively).
            Assert.Contains(op, NativeGhBridgeRegistrar.ExpectedVisionOps);
        }

        [Theory]
        [InlineData(VideoOpHandler.OpListJobs)]
        [InlineData(VideoOpHandler.OpListModels)]
        public void ExpectedVisionOps_ContainsV4VideoListOps(string op)
        {
            // V4 promoted the two list ops from bridge-only (V3) to
            // native HTTP. They route through DispatchOffUi alongside
            // status/result/estimate. If a future PR removes them
            // without updating this test, agent-direct + curl access
            // would silently break.
            Assert.Contains(op, NativeGhBridgeRegistrar.ExpectedVisionOps);
        }

        [Fact]
        public void ExpectedVisionOps_ContainsDirectorPublishVideo()
        {
            Assert.Contains("publish_director_video", NativeGhBridgeRegistrar.ExpectedVisionOps);
        }

        [Theory]
        [InlineData("get_presentation_diagnostics")]
        [InlineData("repair_presentation")]
        public void ExpectedVisionOps_ContainsPresentationOps(string op)
        {
            // Presentation reconciler (spec 2026-06-10): typed dump/repair
            // ops reachable via POST /vision/presentation. Native
            // constructs the op bodies itself; the trampoline routes both
            // through the UI-thread dispatcher alongside capture_depth.
            Assert.Contains(op, NativeGhBridgeRegistrar.ExpectedVisionOps);
        }

        [Fact]
        public void ExpectedVisionOps_HasExactly18Ops()
        {
            // Pinned count: 8 image + 1 Director publish + 5 V2 video
            // + 2 V4 video list ops + 2 presentation ops.
            // If this drifts, either a new op landed (update both the
            // count and the per-op test above) or one was removed
            // (intentional retirement).
            Assert.Equal(18, NativeGhBridgeRegistrar.ExpectedVisionOps.Count);
        }

        [Fact]
        public void VisionDispatch_RoutesDirectorPublishVideoThroughOffUi()
        {
            var source = File.ReadAllText(Path.Combine(FindRepoRoot(), "src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs"));
            var publishArm = ExtractSwitchArm(source, "case \"publish_director_video\":");

            Assert.Contains("return ExecuteOffUiApiResponseCallback(", publishArm);
            Assert.Contains("reqJson => Vision.DispatchOffUi(reqJson)", publishArm);
            Assert.Contains("timeoutSeconds: 180", publishArm);
            Assert.DoesNotContain("_videoOpHandler", publishArm);
            Assert.DoesNotContain("ExecuteAsyncApiResponseCallback", publishArm);
        }

        [Fact]
        public void Registrar_DeclaresCanvasDirectorDispatchCallback()
        {
            var source = File.ReadAllText(Path.Combine(FindRepoRoot(), "src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs"));

            Assert.Contains("CanvasDirectorDispatchCallback", source);
            Assert.Contains("HandleCanvasDirectorDispatch", source);
            Assert.Contains("public IntPtr CanvasDirectorDispatch;", source);
            Assert.Contains("CanvasDirectorDispatch = Marshal.GetFunctionPointerForDelegate(CanvasDirectorDispatchCallback)", source);

            var syncStart = source.IndexOf("private static int ExecuteApiResponseCallback", StringComparison.Ordinal);
            var nextFunction = source.IndexOf("private static uint? ParseDocumentSerialNumber", syncStart, StringComparison.Ordinal);
            var syncExecutor = source.Substring(syncStart, nextFunction - syncStart);
            Assert.Contains("statusCode = MapBridgeStatus(result);", syncExecutor);
            Assert.DoesNotContain("statusCode = result.Success ? 200 : 400;", syncExecutor);
            Assert.Contains("timeoutErrorCode", syncExecutor);
            Assert.Contains("solve_timeout", source);
        }

        [Theory]
        [InlineData("set_provider_secret")]
        [InlineData("test_provider_secret")]
        [InlineData("clear_provider_secret")]
        [InlineData("list_image_models")]
        public void ExpectedVisionOps_DoesNotExposeProviderSettingsOps(string op)
        {
            Assert.DoesNotContain(op, NativeGhBridgeRegistrar.ExpectedVisionOps);
        }

        // ─── BuildUnknownOpMessage ───────────────────────────────────────

        [Fact]
        public void BuildUnknownOpMessage_NullOp_ReturnsMissingDiscriminator()
        {
            var msg = NativeGhBridgeRegistrar.BuildUnknownOpMessage(null);
            Assert.Contains("missing required 'op'", msg);
        }

        [Fact]
        public void BuildUnknownOpMessage_EmptyOp_ReturnsMissingDiscriminator()
        {
            var msg = NativeGhBridgeRegistrar.BuildUnknownOpMessage(string.Empty);
            Assert.Contains("missing required 'op'", msg);
        }

        [Fact]
        public void BuildUnknownOpMessage_UnknownOp_QuotesOpAndListsAllExpected()
        {
            var msg = NativeGhBridgeRegistrar.BuildUnknownOpMessage("frobnicate");

            Assert.Contains("'frobnicate'", msg);
            // Every expected op must appear in the message — the rule
            // that prevents drift between the switch and the rejection
            // message. The message is sorted ordinal so its content is
            // deterministic regardless of HashSet iteration order.
            foreach (var expected in NativeGhBridgeRegistrar.ExpectedVisionOps)
            {
                Assert.Contains($"'{expected}'", msg);
            }
        }

        // ─── Shared-singleton wiring (Codex step 7 follow-up) ────────────

        [Fact]
        public void Registrar_VisionHandler_UsesSharedArtifactStore()
        {
            // Mirrors VisionWebSurface's reflection pin. The native HTTP
            // image-side path (vision_dispatch → Vision.Dispatch /
            // DispatchAsync / DispatchOffUi) MUST go through the same
            // ArtifactStore instance as the tab and the V2 video
            // subsystem. A regression to fresh stores would silently
            // split in-memory artifact state across the two transports.
            var visionField = typeof(NativeGhBridgeRegistrar).GetField(
                "Vision",
                BindingFlags.Static | BindingFlags.NonPublic);
            Assert.NotNull(visionField);
            var vision = (VisionHandler)visionField!.GetValue(null)!;
            Assert.NotNull(vision);

            var artifactStoreField = typeof(VisionHandler).GetField(
                "_artifactStore",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(artifactStoreField);
            var actual = artifactStoreField!.GetValue(vision);

            Assert.Same(RookSubsystemRoot.Instance.SharedArtifactStore, actual);
        }

        [Fact]
        public void Registrar_VisionHandler_UsesSecretStoreShimBackedBySharedGenerationSecretStore()
        {
            // VisionSecretStore remains as the compatibility facade for
            // prompt/settings code, but the shared identity now lives in
            // the keyed IGenerationSecretStore under the shim.
            var visionField = typeof(NativeGhBridgeRegistrar).GetField(
                "Vision",
                BindingFlags.Static | BindingFlags.NonPublic);
            Assert.NotNull(visionField);
            var vision = (VisionHandler)visionField!.GetValue(null)!;

            var secretsField = typeof(VisionHandler).GetField(
                "_secrets",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(secretsField);
            var shim = Assert.IsType<VisionSecretStore>(secretsField!.GetValue(vision));
            var generationField = typeof(VisionSecretStore).GetField(
                "_generationSecrets",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(generationField);

            Assert.Same(
                RookSubsystemRoot.Instance.SharedGenerationSecretStore,
                generationField!.GetValue(shim));
        }

        [Fact]
        public void Registrar_VisionHandler_UsesSharedGenerationSecretStore()
        {
            // Same invariant as the legacy VisionSecretStore pin, now
            // retargeted to the PR-4 keyed secret store. Native HTTP and
            // the tab must share this exact instance so set/test/use
            // paths see one credential source.
            var visionField = typeof(NativeGhBridgeRegistrar).GetField(
                "Vision",
                BindingFlags.Static | BindingFlags.NonPublic);
            Assert.NotNull(visionField);
            var vision = (VisionHandler)visionField!.GetValue(null)!;

            var secretsField = typeof(VisionHandler).GetField(
                "_generationSecrets",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(secretsField);
            var actual = secretsField!.GetValue(vision);

            Assert.Same(RookSubsystemRoot.Instance.SharedGenerationSecretStore, actual);
        }

        [Fact]
        public void Registrar_VisionHandler_UsesSharedImageProviderRegistry()
        {
            var visionField = typeof(NativeGhBridgeRegistrar).GetField(
                "Vision",
                BindingFlags.Static | BindingFlags.NonPublic);
            Assert.NotNull(visionField);
            var vision = (VisionHandler)visionField!.GetValue(null)!;
            var registryField = typeof(VisionHandler).GetField(
                "_imageProviderRegistry",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(registryField);

            Assert.Same(
                RookSubsystemRoot.Instance.ImageJobs.Registry,
                registryField!.GetValue(vision));
        }

        [Fact]
        public void BuildUnknownOpMessage_ListsExpectedOpsInOrdinalOrder()
        {
            // The message orders the expected list ordinal-ascending so
            // the output is stable for snapshotting / diffing. Pin the
            // ordering rule explicitly.
            var msg = NativeGhBridgeRegistrar.BuildUnknownOpMessage("x");

            var ordered = NativeGhBridgeRegistrar.ExpectedVisionOps
                .OrderBy(s => s, System.StringComparer.Ordinal)
                .ToArray();

            int lastIdx = -1;
            foreach (var op in ordered)
            {
                var idx = msg.IndexOf($"'{op}'", System.StringComparison.Ordinal);
                Assert.True(idx > lastIdx,
                    $"op '{op}' should appear after '{ordered[System.Math.Max(0, System.Array.IndexOf(ordered, op) - 1)]}'");
                lastIdx = idx;
            }
        }
    }
}
