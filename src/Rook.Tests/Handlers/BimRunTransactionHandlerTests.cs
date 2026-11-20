using System;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rook.Bim;
using Rook.Handlers;
using Rook.Tests.Bim;
using Xunit;

namespace Rook.Tests.Handlers
{
    [Collection(RookBimRuntimeRegistryCollection.Name)]
    public class BimRunTransactionHandlerTests
    {
        [Theory]
        [InlineData("{\"op\":\"run_transaction\",\"code\":\"pass\"}", "name is required")]
        [InlineData("{\"op\":\"run_transaction\",\"name\":\"   \",\"code\":\"pass\"}", "name is required")]
        [InlineData("{\"op\":\"run_transaction\",\"name\":\"Rename level\"}", "code is required")]
        [InlineData("{\"op\":\"run_transaction\",\"name\":\"Rename level\",\"code\":\"pass\",\"timeoutSeconds\":0}", "timeoutSeconds must be between 1 and 90")]
        [InlineData("{\"op\":\"run_transaction\",\"name\":\"Rename level\",\"code\":\"pass\",\"timeoutSeconds\":91}", "timeoutSeconds must be between 1 and 90")]
        public void Dispatch_RunTransaction_RefusesInvalidRequestBeforeTheRuntimeIsReached(
            string body,
            string expectedMessage)
        {
            var runtime = new RecordingRuntime(BimApiResponse.Ok(null));
            RookBimRuntimeRegistry.Install(runtime, "test-run-transaction");
            try
            {
                var response = new BimHandler().Dispatch(body);
                var data = ToJsonElement(response.Data);

                Assert.False(response.Success);
                Assert.Equal(400, response.HttpStatus);
                Assert.Equal("invalid_request", data.GetProperty("errorCode").GetString());
                Assert.Contains(expectedMessage, data.GetProperty("message").GetString());
                Assert.Equal(0, runtime.RunTransactionCalls);
            }
            finally
            {
                RookBimRuntimeRegistry.ResetForTests();
            }
        }

        [Fact]
        public void Dispatch_RunTransaction_ForwardsTheValidatedRequestAndReturnsRuntimeData()
        {
            var runtime = new RecordingRuntime(BimApiResponse.Ok(new
            {
                transaction = new { name = "Rename level", status = "committed" },
                changed = true,
                result = JsonNode.Parse("{\"renamed\":311}")
            }));
            RookBimRuntimeRegistry.Install(runtime, "test-run-transaction");
            try
            {
                var response = new BimHandler().Dispatch(
                    "{\"op\":\"run_transaction\",\"name\":\"  Rename level \",\"code\":\"result = 1\",\"timeoutSeconds\":30}");
                var data = ToJsonElement(response.Data);

                Assert.True(response.Success);
                Assert.Equal(200, response.HttpStatus);
                Assert.Equal(1, runtime.RunTransactionCalls);
                Assert.Equal("Rename level", runtime.LastRequest!.EffectiveName);
                Assert.Equal("result = 1", runtime.LastRequest.Code);
                Assert.Equal(30, runtime.LastRequest.EffectiveTimeoutSeconds);
                Assert.Equal("committed", data.GetProperty("transaction").GetProperty("status").GetString());
                Assert.True(data.GetProperty("changed").GetBoolean());
                // The script's own result keys travel verbatim, not camel-cased or renamed.
                Assert.Equal(311, data.GetProperty("result").GetProperty("renamed").GetInt32());
            }
            finally
            {
                RookBimRuntimeRegistry.ResetForTests();
            }
        }

        [Fact]
        public void Dispatch_RunTransaction_ScriptFailureKeepsRollbackDetailsForTheCaller()
        {
            var failure = BimApiResponse.Fail(
                BimErrorCode.TransactionScriptFailed,
                "The script raised ZeroDivisionError: division by zero. Transaction 'Rename level' was rolled back; the Revit document is unchanged.",
                422);
            failure.Data = new
            {
                transaction = new { name = "Rename level", status = "rolled_back" },
                documentChanged = false,
                traceback = "Traceback (most recent call last): ..."
            };
            RookBimRuntimeRegistry.Install(new RecordingRuntime(failure), "test-run-transaction");
            try
            {
                var response = new BimHandler().Dispatch(
                    "{\"op\":\"run_transaction\",\"name\":\"Rename level\",\"code\":\"1/0\"}");
                var data = ToJsonElement(response.Data);

                Assert.False(response.Success);
                Assert.Equal(422, response.HttpStatus);
                Assert.Equal("transaction_script_failed", data.GetProperty("errorCode").GetString());
                Assert.Contains("rolled back", data.GetProperty("message").GetString());
                var details = data.GetProperty("details");
                Assert.Equal("rolled_back", details.GetProperty("transaction").GetProperty("status").GetString());
                Assert.False(details.GetProperty("documentChanged").GetBoolean());
                Assert.Contains("Traceback", details.GetProperty("traceback").GetString());
            }
            finally
            {
                RookBimRuntimeRegistry.ResetForTests();
            }
        }

        [Fact]
        public void Dispatch_RevitNotIdle_NamesTheDialogCauseAndIsNotReportedAsMissingHost()
        {
            var refusal = BimApiResponse.Fail(
                BimErrorCode.RevitNotIdle,
                "Revit did not become idle within 10 s, so RookBIM operation 'run_transaction' never ran and nothing was read or changed.",
                503);
            RookBimRuntimeRegistry.Install(new RecordingRuntime(refusal), "test-run-transaction");
            try
            {
                var response = new BimHandler().Dispatch(
                    "{\"op\":\"run_transaction\",\"name\":\"Rename level\",\"code\":\"pass\"}");
                var data = ToJsonElement(response.Data);
                var diagnostic = ToJsonElement(response.Diagnostic);

                Assert.False(response.Success);
                Assert.Equal(503, response.HttpStatus);
                Assert.Equal("revit_not_idle", data.GetProperty("errorCode").GetString());
                Assert.NotEqual("not_rhino_inside", data.GetProperty("errorCode").GetString());
                Assert.Equal("revit_not_idle", diagnostic.GetProperty("reasonCode").GetString());
                Assert.Equal("host_blocked", diagnostic.GetProperty("failureKind").GetString());
                Assert.True(diagnostic.GetProperty("retryable").GetBoolean());
                Assert.True(diagnostic.GetProperty("userActionRequired").GetBoolean());
                Assert.Equal("POST /bim/run-transaction", diagnostic.GetProperty("route").GetString());
                Assert.Contains("dialog", diagnostic.GetProperty("recommendedNextStep").GetString());
            }
            finally
            {
                RookBimRuntimeRegistry.ResetForTests();
            }
        }

        [Fact]
        public void Dispatch_Status_RevitNotIdleKeepsItsOwnReasonCode()
        {
            RookBimRuntimeRegistry.Install(new RecordingRuntime(BimApiResponse.Ok(null)), "test-run-transaction");
            try
            {
                var response = new BimHandler(() => true).Dispatch("{\"op\":\"status\"}");
                var data = ToJsonElement(response.Data);
                var diagnostic = ToJsonElement(response.Diagnostic);

                Assert.False(data.GetProperty("available").GetBoolean());
                Assert.Equal("revit_not_idle", data.GetProperty("errorCode").GetString());
                Assert.Equal("revit", data.GetProperty("host").GetString());
                Assert.Equal("revit_not_idle", diagnostic.GetProperty("reasonCode").GetString());
                Assert.Equal("GET /bim/status", diagnostic.GetProperty("route").GetString());
            }
            finally
            {
                RookBimRuntimeRegistry.ResetForTests();
            }
        }

        [Theory]
        [InlineData(BimErrorCode.InvalidRequest, "invalid_request")]
        [InlineData(BimErrorCode.RevitNotIdle, "revit_not_idle")]
        [InlineData(BimErrorCode.RevitOperationTimeout, "revit_operation_timeout")]
        [InlineData(BimErrorCode.DocumentNotModifiable, "document_not_modifiable")]
        [InlineData(BimErrorCode.TransactionScriptFailed, "transaction_script_failed")]
        [InlineData(BimErrorCode.TransactionRolledBack, "transaction_rolled_back")]
        [InlineData(BimErrorCode.TransactionTimeout, "transaction_timeout")]
        public void MapErrorCode_GivesEveryTransactionAndIdleFailureItsOwnWireCode(
            BimErrorCode code,
            string expected)
        {
            Assert.Equal(expected, BimHandler.MapErrorCode(code));
        }

        [Fact]
        public void UnavailableRuntime_RefusesRunTransaction()
        {
            var runtime = new RookBimUnavailableRuntime("rookbim_unavailable", "nope");

            var response = runtime.RunTransaction(
                BimDiagnosticContext.Disabled,
                new BimRunTransactionRequest { Name = "Rename level", Code = "pass" });

            Assert.False(response.Success);
            Assert.Equal(BimErrorCode.RookBimUnavailable, response.ErrorCode);
            Assert.Equal(503, response.HttpStatus);
        }

        private static JsonElement ToJsonElement(object? value)
        {
            var json = JsonSerializer.Serialize(value);
            using var document = JsonDocument.Parse(json);
            return document.RootElement.Clone();
        }

        private sealed class RecordingRuntime : IRookBimRuntime
        {
            private readonly BimApiResponse runTransactionResponse;

            public RecordingRuntime(BimApiResponse runTransactionResponse)
            {
                this.runTransactionResponse = runTransactionResponse;
            }

            public int RunTransactionCalls { get; private set; }

            public BimRunTransactionRequest? LastRequest { get; private set; }

            public BimStatusResponse Status(BimDiagnosticContext diagnostics)
            {
                return new BimStatusResponse
                {
                    Available = false,
                    Runtime = "rookbim",
                    ErrorCode = "revit_not_idle",
                    Message = "Revit did not become idle within 5 s.",
                    Host = "revit",
                    Module = "RookBim.dll"
                };
            }

            public BimApiResponse RunTransaction(BimDiagnosticContext diagnostics, BimRunTransactionRequest request)
            {
                RunTransactionCalls++;
                LastRequest = request;
                return runTransactionResponse;
            }

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
