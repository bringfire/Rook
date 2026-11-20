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
        [InlineData("{\"op\":\"run_transaction\",\"name\":\"Rename level\",\"code\":\"pass\",\"documentKey\":\"\"}", "documentKey was given but is blank")]
        [InlineData("{\"op\":\"run_transaction\",\"name\":\"Rename level\",\"code\":\"pass\",\"documentKey\":\"  \"}", "documentKey was given but is blank")]
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

        [Theory]
        [InlineData("{\"op\":\"run_transaction\",\"name\":\"Rename level\",\"code\":\"pass\",\"timeoutSeconds\":\"30\"}")]
        [InlineData("{\"op\":\"run_transaction\",\"name\":123,\"code\":\"pass\"}")]
        [InlineData("{\"op\":\"run_transaction\",\"name\":\"Rename level\",\"code\":[\"pass\"]}")]
        public void Dispatch_RunTransaction_WrongTypedFieldIsAnInvalidRequestNotAnInvalidScope(string body)
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
                Assert.Contains("wrong JSON type", data.GetProperty("message").GetString());
                Assert.Contains("timeoutSeconds (integer, optional)", data.GetProperty("message").GetString());
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
                    "{\"op\":\"run_transaction\",\"name\":\"  Rename level \",\"code\":\"result = 1\",\"timeoutSeconds\":30,\"documentKey\":\"file-document-v1:abc\"}");
                var data = ToJsonElement(response.Data);

                Assert.True(response.Success);
                Assert.Equal(200, response.HttpStatus);
                Assert.Equal(1, runtime.RunTransactionCalls);
                Assert.Equal("Rename level", runtime.LastRequest!.EffectiveName);
                Assert.Equal("result = 1", runtime.LastRequest.Code);
                Assert.Equal(30, runtime.LastRequest.EffectiveTimeoutSeconds);
                Assert.Equal("file-document-v1:abc", runtime.LastRequest.DocumentKey);
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
        [InlineData(BimErrorCode.TransactionOutcomeUnknown, "transaction_outcome_unknown")]
        [InlineData(BimErrorCode.TransactionReceiptNotFound, "transaction_receipt_not_found")]
        public void MapErrorCode_GivesEveryTransactionAndIdleFailureItsOwnWireCode(
            BimErrorCode code,
            string expected)
        {
            Assert.Equal(expected, BimHandler.MapErrorCode(code));
        }

        [Fact]
        public void Dispatch_TransactionReceipt_AnswersFromMemoryWithoutTheRuntime()
        {
            // The runtime throws if touched: a receipt must be readable while
            // the host API thread is busy with the very transaction asked about.
            RookBimRuntimeRegistry.Install(new ThrowingRuntime(), "test-receipt");
            try
            {
                var receipt = BimTransactionReceiptStore.Create("Rename level");
                receipt.SetDocument(new BimDocumentIdentity { Title = "Tower.rvt", DocumentKey = "file-document-v1:abc" });
                receipt.MarkOpen();
                receipt.ProhibitCommit(BimErrorCode.TransactionTimeout, "The script did not finish within 5 s.");

                var open = ToJsonElement(new BimHandler().Dispatch(
                    "{\"op\":\"transaction_receipt\",\"transactionId\":\"" + receipt.Id + "\"}").Data);

                Assert.Equal("open", open.GetProperty("transaction").GetProperty("status").GetString());
                Assert.True(open.GetProperty("transaction").GetProperty("commitProhibited").GetBoolean());
                Assert.False(open.GetProperty("final").GetBoolean());
                Assert.Equal(JsonValueKind.Null, open.GetProperty("documentChanged").ValueKind);
                Assert.Equal("transaction_timeout", open.GetProperty("errorCode").GetString());
                Assert.Contains("will not be committed", open.GetProperty("message").GetString());
                Assert.Equal("file-document-v1:abc", open.GetProperty("document").GetProperty("documentKey").GetString());

                // The host thread finishes the rollback and leaves; the same id now reads final.
                receipt.Settle(BimTransactionStatus.RolledBack);
                receipt.EndObservation();
                var settled = ToJsonElement(new BimHandler().Dispatch(
                    "{\"op\":\"transaction_receipt\",\"transactionId\":\"" + receipt.Id + "\"}").Data);

                Assert.Equal("rolled_back", settled.GetProperty("transaction").GetProperty("status").GetString());
                Assert.True(settled.GetProperty("final").GetBoolean());
                Assert.False(settled.GetProperty("documentChanged").GetBoolean());
                Assert.Contains("the Revit document is unchanged", settled.GetProperty("message").GetString());
                // A lookup has no details block, so it must not send the reader to one.
                Assert.DoesNotContain("details.", settled.GetProperty("message").GetString());
            }
            finally
            {
                RookBimRuntimeRegistry.ResetForTests();
            }
        }

        [Fact]
        public void Dispatch_TransactionReceipt_CommittedReadsAsCommittedWithNoErrorCode()
        {
            var receipt = BimTransactionReceiptStore.Create("Rename level");
            receipt.MarkOpen();
            receipt.Settle(BimTransactionStatus.Committed, true);
            receipt.EndObservation();

            var response = new BimHandler().Dispatch(
                "{\"op\":\"transaction_receipt\",\"transactionId\":\"" + receipt.Id + "\"}");
            var data = ToJsonElement(response.Data);

            Assert.True(response.Success);
            Assert.Equal("committed", data.GetProperty("transaction").GetProperty("status").GetString());
            Assert.True(data.GetProperty("final").GetBoolean());
            Assert.True(data.GetProperty("documentChanged").GetBoolean());
            Assert.Equal(JsonValueKind.Null, data.GetProperty("errorCode").ValueKind);
        }

        [Fact]
        public void Dispatch_TransactionReceipt_ACommitThatChangedNothingReadsUnchangedNotChanged()
        {
            // code = "pass": committed, nothing changed. The lookup must give
            // the same answer the write call gave.
            var receipt = BimTransactionReceiptStore.Create("No-op");
            receipt.MarkOpen();
            receipt.Settle(BimTransactionStatus.Committed, false);
            receipt.EndObservation();

            var data = ToJsonElement(new BimHandler().Dispatch(
                "{\"op\":\"transaction_receipt\",\"transactionId\":\"" + receipt.Id + "\"}").Data);

            Assert.Equal("committed", data.GetProperty("transaction").GetProperty("status").GetString());
            Assert.False(data.GetProperty("documentChanged").GetBoolean());
        }

        [Fact]
        public void Dispatch_TransactionReceipt_AWriteStillInTheQueueReadsQueuedNotFailed()
        {
            var receipt = BimTransactionReceiptStore.Create("Waiting behind a dialog");

            var response = new BimHandler().Dispatch(
                "{\"op\":\"transaction_receipt\",\"transactionId\":\"" + receipt.Id + "\"}");
            var data = ToJsonElement(response.Data);

            Assert.True(response.Success);
            Assert.Equal("queued", data.GetProperty("transaction").GetProperty("status").GetString());
            Assert.False(data.GetProperty("final").GetBoolean());
            Assert.Equal(JsonValueKind.Null, data.GetProperty("errorCode").ValueKind);
            Assert.Equal(JsonValueKind.Null, data.GetProperty("documentChanged").ValueKind);
            Assert.Contains("it may still run", data.GetProperty("message").GetString());
            Assert.Contains("do not submit it again", data.GetProperty("message").GetString());
        }

        [Fact]
        public void Dispatch_TransactionReceipt_UnknownIdIsRefusedWithWhatToDoInstead()
        {
            var response = new BimHandler().Dispatch(
                "{\"op\":\"transaction_receipt\",\"transactionId\":\"tx-000000000000\"}");
            var data = ToJsonElement(response.Data);

            Assert.False(response.Success);
            Assert.Equal(404, response.HttpStatus);
            Assert.Equal("transaction_receipt_not_found", data.GetProperty("errorCode").GetString());
            Assert.Contains("do not survive a restart of Revit", data.GetProperty("message").GetString());
            Assert.Contains("read the model back", data.GetProperty("message").GetString());
        }

        [Fact]
        public void Dispatch_TransactionReceipt_WithoutAnIdListsRecentReceiptsNewestFirst()
        {
            BimTransactionReceiptStore.Create("older");
            BimTransactionReceiptStore.Create("newer");

            var response = new BimHandler().Dispatch("{\"op\":\"transaction_receipt\"}");
            var data = ToJsonElement(response.Data);
            var receipts = data.GetProperty("receipts");

            Assert.True(response.Success);
            Assert.Equal(64, data.GetProperty("kept").GetInt32());
            Assert.True(receipts.GetArrayLength() >= 2 && receipts.GetArrayLength() <= 10);
            Assert.Equal("newer", receipts[0].GetProperty("transaction").GetProperty("name").GetString());
            Assert.Equal("older", receipts[1].GetProperty("transaction").GetProperty("name").GetString());
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

        private sealed class ThrowingRuntime : IRookBimRuntime
        {
            private static InvalidOperationException Touched() =>
                new InvalidOperationException("The receipt lookup must not reach the runtime.");

            public BimStatusResponse Status(BimDiagnosticContext diagnostics) => throw Touched();
            public BimApiResponse RunTransaction(BimDiagnosticContext diagnostics, BimRunTransactionRequest request) => throw Touched();
            public BimApiResponse ActiveDocument(BimDiagnosticContext diagnostics) => throw Touched();
            public BimApiResponse ListCategories(BimDiagnosticContext diagnostics) => throw Touched();
            public BimApiResponse QueryElements(BimDiagnosticContext diagnostics, BimQueryElementsRequest request) => throw Touched();
            public BimApiResponse ElementInfo(BimDiagnosticContext diagnostics, BimElementRequest request) => throw Touched();
            public BimApiResponse ElementParameters(BimDiagnosticContext diagnostics, BimElementRequest request) => throw Touched();
            public BimApiResponse SelectElements(BimDiagnosticContext diagnostics, BimSelectElementsRequest request) => throw Touched();
            public BimApiResponse ClearSelection(BimDiagnosticContext diagnostics) => throw Touched();
            public BimApiResponse ExportElements(BimDiagnosticContext diagnostics, BimExportElementsRequest request) => throw Touched();
            public BimApiResponse ExportPreset(BimDiagnosticContext diagnostics, BimExportPresetRequest request) => throw Touched();
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
