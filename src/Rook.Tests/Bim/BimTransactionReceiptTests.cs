using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    [Collection(RookBimRuntimeRegistryCollection.Name)]
    public class BimTransactionReceiptTests
    {
        private static BimTransactionReceipt NewReceipt(string name = "Rename level")
        {
            return BimTransactionReceiptStore.Create(name);
        }

        private static JsonElement Json(object? value)
        {
            using var document = JsonDocument.Parse(JsonSerializer.Serialize(value));
            return document.RootElement.Clone();
        }

        // ---- the receipt: one writer, confirmed states are final ------------

        [Fact]
        public void NewReceipt_IsNotStartedWithNoCauseAndNotFinal()
        {
            var snapshot = NewReceipt().Snapshot();

            Assert.Equal(BimTransactionStatus.NotStarted, snapshot.Status);
            Assert.Equal(BimErrorCode.None, snapshot.Cause);
            Assert.False(snapshot.CommitProhibited);
            Assert.False(snapshot.IsTerminal);
            Assert.StartsWith("tx-", snapshot.Id);
        }

        [Fact]
        public void Refuse_RecordsTheFirstCauseAndIsFinal()
        {
            var receipt = NewReceipt();

            receipt.Refuse(BimErrorCode.DocumentMismatch, "wrong document");
            receipt.Refuse(BimErrorCode.InternalError, "a later, vaguer refusal");

            var snapshot = receipt.Snapshot();
            Assert.Equal(BimTransactionStatus.NotStarted, snapshot.Status);
            Assert.Equal(BimErrorCode.DocumentMismatch, snapshot.Cause);
            Assert.Equal("wrong document", snapshot.Message);
            Assert.True(snapshot.CommitProhibited);
            Assert.True(snapshot.IsTerminal);
        }

        [Fact]
        public void Committed_IsFinalAndCannotBeOverwrittenByAnythingAfterIt()
        {
            var receipt = NewReceipt();
            receipt.MarkOpen();
            receipt.Settle(BimTransactionStatus.Committed);

            // Everything that can happen after a commit: late cancellation,
            // a failing report, a second settle from a finally block.
            receipt.ProhibitCommit(BimErrorCode.TransactionTimeout, "caller stopped waiting");
            receipt.Settle(BimTransactionStatus.RolledBack);
            receipt.Settle(BimTransactionStatus.Unresolved);
            receipt.Refuse(BimErrorCode.InternalError, "late refusal");

            var snapshot = receipt.Snapshot();
            Assert.Equal(BimTransactionStatus.Committed, snapshot.Status);
            Assert.Equal(BimErrorCode.None, snapshot.Cause);
            Assert.False(snapshot.CommitProhibited);
            Assert.True(snapshot.IsTerminal);
        }

        [Fact]
        public void RolledBack_IsFinalAndKeepsItsCause()
        {
            var receipt = NewReceipt();
            receipt.MarkOpen();
            receipt.ProhibitCommit(BimErrorCode.TransactionScriptFailed, "The script raised ValueError.");
            receipt.Settle(BimTransactionStatus.RolledBack);

            receipt.Settle(BimTransactionStatus.Unresolved);
            receipt.Settle(BimTransactionStatus.Committed);

            var snapshot = receipt.Snapshot();
            Assert.Equal(BimTransactionStatus.RolledBack, snapshot.Status);
            Assert.Equal(BimErrorCode.TransactionScriptFailed, snapshot.Cause);
        }

        [Fact]
        public void Unresolved_CanStillBecomeAConfirmedState()
        {
            var receipt = NewReceipt();
            receipt.MarkOpen();
            receipt.Settle(BimTransactionStatus.Unresolved);
            Assert.False(receipt.Snapshot().IsTerminal);

            receipt.Settle(BimTransactionStatus.RolledBack);

            Assert.Equal(BimTransactionStatus.RolledBack, receipt.Snapshot().Status);
        }

        [Fact]
        public void ProhibitCommit_KeepsTheFirstCause()
        {
            var receipt = NewReceipt();
            receipt.MarkOpen();

            receipt.ProhibitCommit(BimErrorCode.TransactionTimeout, "The script did not finish within 5 s.");
            receipt.ProhibitCommit(BimErrorCode.TransactionScriptFailed, "it raised later");

            Assert.Equal(BimErrorCode.TransactionTimeout, receipt.Snapshot().Cause);
        }

        // ---- the store -------------------------------------------------------

        [Fact]
        public void Store_FindsAReceiptByIdAndForgetsTheOldestBeyondItsCapacity()
        {
            BimTransactionReceiptStore.ResetForTests();
            var first = NewReceipt("first");
            for (var index = 0; index < BimTransactionReceiptStore.Capacity; index++)
            {
                NewReceipt("filler " + index);
            }

            var last = NewReceipt("last");

            Assert.False(BimTransactionReceiptStore.TryGet(first.Id, out _));
            Assert.True(BimTransactionReceiptStore.TryGet(last.Id, out var found));
            Assert.Same(last, found);
            Assert.False(BimTransactionReceiptStore.TryGet("tx-does-not-exist", out _));
            Assert.Equal("last", BimTransactionReceiptStore.Recent(1).Single().Name);
            Assert.Equal(BimTransactionReceiptStore.Capacity, BimTransactionReceiptStore.Recent(1000).Count);
        }

        // ---- the single decision point ----------------------------------------

        public static IEnumerable<object[]> OutcomeTable()
        {
            // status, commitProhibited, cause -> wire code, http, documentChanged
            yield return new object?[] { "not_started", BimErrorCode.DocumentMismatch, BimErrorCode.DocumentMismatch, 409, false };
            yield return new object?[] { "not_started", BimErrorCode.DocumentNotModifiable, BimErrorCode.DocumentNotModifiable, 409, false };
            yield return new object?[] { "not_started", BimErrorCode.RevitNotIdle, BimErrorCode.RevitNotIdle, 503, false };
            yield return new object?[] { "not_started", BimErrorCode.TransactionTimeout, BimErrorCode.TransactionTimeout, 504, false };
            yield return new object?[] { "rolled_back", BimErrorCode.TransactionScriptFailed, BimErrorCode.TransactionScriptFailed, 422, false };
            yield return new object?[] { "rolled_back", BimErrorCode.TransactionRolledBack, BimErrorCode.TransactionRolledBack, 409, false };
            yield return new object?[] { "rolled_back", BimErrorCode.TransactionTimeout, BimErrorCode.TransactionTimeout, 504, false };
            yield return new object?[] { "rolled_back", BimErrorCode.InternalError, BimErrorCode.InternalError, 500, false };
            // Still open, commit withdrawn: the cause is reported, the document is not claimed either way.
            yield return new object?[] { "open_prohibited", BimErrorCode.TransactionTimeout, BimErrorCode.TransactionTimeout, 504, null };
            yield return new object?[] { "open_prohibited", BimErrorCode.TransactionScriptFailed, BimErrorCode.TransactionScriptFailed, 422, null };
            // Not confirmed: whatever the cause, the answer is "unknown".
            yield return new object?[] { "open", BimErrorCode.None, BimErrorCode.TransactionOutcomeUnknown, 409, null };
            yield return new object?[] { "unresolved", BimErrorCode.None, BimErrorCode.TransactionOutcomeUnknown, 409, null };
            yield return new object?[] { "unresolved", BimErrorCode.TransactionScriptFailed, BimErrorCode.TransactionOutcomeUnknown, 409, null };
            yield return new object?[] { "unresolved", BimErrorCode.TransactionRolledBack, BimErrorCode.TransactionOutcomeUnknown, 409, null };
        }

        private static BimTransactionReceiptSnapshot Arrange(string state, BimErrorCode cause)
        {
            var receipt = NewReceipt();
            switch (state)
            {
                case "not_started":
                    receipt.Refuse(cause, "cause text.");
                    break;
                case "rolled_back":
                    receipt.MarkOpen();
                    receipt.ProhibitCommit(cause, "cause text.");
                    receipt.Settle(BimTransactionStatus.RolledBack);
                    break;
                case "open_prohibited":
                    receipt.MarkOpen();
                    receipt.ProhibitCommit(cause, "cause text.");
                    break;
                case "open":
                    receipt.MarkOpen();
                    break;
                case "unresolved":
                    receipt.MarkOpen();
                    if (cause != BimErrorCode.None)
                    {
                        receipt.ProhibitCommit(cause, "cause text.");
                    }

                    receipt.Settle(BimTransactionStatus.Unresolved);
                    break;
                default:
                    throw new ArgumentOutOfRangeException(nameof(state));
            }

            return receipt.Snapshot();
        }

        [Theory]
        [MemberData(nameof(OutcomeTable))]
        public void Report_ChoosesCodeStatusAndDocumentClaimFromTheReceiptAlone(
            string state,
            BimErrorCode cause,
            BimErrorCode expectedCode,
            int expectedHttp,
            bool? expectedDocumentChanged)
        {
            var snapshot = Arrange(state, cause);

            var response = BimTransactionReport.Build(snapshot);
            var data = Json(response.Data);

            Assert.False(response.Success);
            Assert.Equal(expectedCode, response.ErrorCode);
            Assert.Equal(expectedHttp, response.HttpStatus);
            Assert.Equal(snapshot.Id, data.GetProperty("transaction").GetProperty("id").GetString());
            var changed = data.GetProperty("documentChanged");
            Assert.Equal(
                expectedDocumentChanged,
                changed.ValueKind == JsonValueKind.Null ? (bool?)null : changed.GetBoolean());
        }

        [Fact]
        public void Report_OnlyAConfirmedEndStateSaysTheDocumentIsUnchangedOrInvitesARetry()
        {
            var rolledBack = BimTransactionReport.Message(Arrange("rolled_back", BimErrorCode.TransactionScriptFailed));
            var notStarted = BimTransactionReport.Message(Arrange("not_started", BimErrorCode.DocumentNotModifiable));
            var openProhibited = BimTransactionReport.Message(Arrange("open_prohibited", BimErrorCode.TransactionTimeout));
            var open = BimTransactionReport.Message(Arrange("open", BimErrorCode.None));
            var unresolved = BimTransactionReport.Message(Arrange("unresolved", BimErrorCode.TransactionScriptFailed));

            Assert.Contains("was rolled back; the Revit document is unchanged", rolledBack);
            Assert.Contains("Fix the script (see details.traceback) and call again.", rolledBack);
            Assert.Contains("No transaction was started; the Revit document is unchanged", notStarted);

            foreach (var unconfirmed in new[] { openProhibited, open, unresolved })
            {
                Assert.DoesNotContain("is unchanged", unconfirmed);
                Assert.DoesNotContain("call again", unconfirmed);
                Assert.Contains("rookbim_transaction_receipt", unconfirmed);
            }

            Assert.Contains("will not be committed", openProhibited);
            Assert.Contains("Do not run the script again", open);
            // The cause is kept, but it does not get to decide the advice.
            Assert.Contains("cause text.", unresolved);
            Assert.Contains("Do not run the script again", unresolved);
        }

        [Fact]
        public void Report_CommittedIsSuccessWithTheReceiptAndWhateverDetailsExist()
        {
            var receipt = NewReceipt();
            receipt.SetDocument(new BimDocumentIdentity { Title = "Tower.rvt", DocumentKey = "file-document-v1:abc" });
            receipt.MarkOpen();
            receipt.Settle(BimTransactionStatus.Committed);

            var response = BimTransactionReport.Build(
                receipt.Snapshot(),
                new Dictionary<string, object?> { ["output"] = "renamed\n", ["transaction"] = "must not replace the receipt" },
                committedChange: true);
            var data = Json(response.Data);

            Assert.True(response.Success);
            Assert.Equal(200, response.HttpStatus);
            Assert.Equal("committed", data.GetProperty("transaction").GetProperty("status").GetString());
            Assert.Equal("Rename level", data.GetProperty("transaction").GetProperty("name").GetString());
            Assert.True(data.GetProperty("documentChanged").GetBoolean());
            Assert.Equal("renamed\n", data.GetProperty("output").GetString());
            Assert.Equal("file-document-v1:abc", data.GetProperty("document").GetProperty("DocumentKey").GetString());
        }

        [Fact]
        public void Report_CommittedWithNoChangesSaysSo()
        {
            var receipt = NewReceipt();
            receipt.MarkOpen();
            receipt.Settle(BimTransactionStatus.Committed);

            var data = Json(BimTransactionReport.Build(receipt.Snapshot(), null, committedChange: false).Data);

            Assert.False(data.GetProperty("documentChanged").GetBoolean());
        }

        [Fact]
        public void Report_OversizedDetailsAreDroppedWithReasonsButTheCommittedReceiptSurvives()
        {
            var receipt = NewReceipt();
            receipt.MarkOpen();
            receipt.Settle(BimTransactionStatus.Committed);
            var huge = Enumerable.Range(0, 200)
                .Select(index => new { identity = new string('é', 4000), elementId = index })
                .ToList();

            var response = BimTransactionReport.Build(
                receipt.Snapshot(),
                new Dictionary<string, object?>
                {
                    ["elements"] = huge,
                    ["result"] = "kept: small",
                    ["output"] = "kept too",
                },
                committedChange: true);
            var data = Json(response.Data);
            var size = JsonSerializer.SerializeToUtf8Bytes(response.Data).Length;

            Assert.True(response.Success);
            Assert.Equal("committed", data.GetProperty("transaction").GetProperty("status").GetString());
            Assert.Equal(JsonValueKind.Null, data.GetProperty("elements").ValueKind);
            Assert.Equal("kept: small", data.GetProperty("result").GetString());
            var omitted = data.GetProperty("omitted").EnumerateArray().Single();
            Assert.Equal("elements", omitted.GetProperty("field").GetString());
            Assert.Contains("the limit is 600000", omitted.GetProperty("reason").GetString());
            Assert.True(size <= BimTransactionReport.MaxDataBytes);
        }

        [Fact]
        public void Report_DetailsThatCannotBeSerializedAreDroppedAndTheReceiptSurvives()
        {
            var receipt = NewReceipt();
            receipt.MarkOpen();
            receipt.Settle(BimTransactionStatus.Committed);
            var loop = new Dictionary<string, object?>();
            loop["self"] = loop;

            var response = BimTransactionReport.Build(
                receipt.Snapshot(),
                new Dictionary<string, object?> { ["result"] = loop, ["output"] = "kept" },
                committedChange: true);
            var data = Json(response.Data);

            Assert.True(response.Success);
            Assert.Equal("committed", data.GetProperty("transaction").GetProperty("status").GetString());
            Assert.Equal(JsonValueKind.Null, data.GetProperty("result").ValueKind);
            Assert.Equal("kept", data.GetProperty("output").GetString());
            Assert.Contains(
                "could not be serialized",
                data.GetProperty("omitted").EnumerateArray().Single().GetProperty("reason").GetString());
        }

        [Fact]
        public void Report_WireStatusNamesAreTheDocumentedVocabulary()
        {
            Assert.Equal("not_started", BimTransactionReport.WireStatus(BimTransactionStatus.NotStarted));
            Assert.Equal("open", BimTransactionReport.WireStatus(BimTransactionStatus.Open));
            Assert.Equal("committed", BimTransactionReport.WireStatus(BimTransactionStatus.Committed));
            Assert.Equal("rolled_back", BimTransactionReport.WireStatus(BimTransactionStatus.RolledBack));
            Assert.Equal("unresolved", BimTransactionReport.WireStatus(BimTransactionStatus.Unresolved));
        }
    }
}
