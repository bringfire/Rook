using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class BimRunTransactionContractsTests
    {
        [Fact]
        public void Request_ValidRequestUsesTrimmedNameAndDefaultTimeout()
        {
            var request = new BimRunTransactionRequest { Name = "  Rename Level 2  ", Code = "pass" };

            var validation = request.Validate();

            Assert.True(validation.Success);
            Assert.Equal("Rename Level 2", request.EffectiveName);
            Assert.Equal(BimRunTransactionRequest.DefaultTimeoutSeconds, request.EffectiveTimeoutSeconds);
        }

        [Theory]
        [InlineData(null, "pass", "name is required")]
        [InlineData("", "pass", "name is required")]
        [InlineData("Two\nlines", "pass", "single line")]
        [InlineData("Rename", null, "code is required")]
        [InlineData("Rename", "   ", "code is required")]
        public void Request_RefusesMissingOrMalformedFieldsWithInvalidRequest(
            string? name,
            string? code,
            string expectedMessage)
        {
            var validation = new BimRunTransactionRequest { Name = name, Code = code }.Validate();

            Assert.False(validation.Success);
            Assert.Equal(BimErrorCode.InvalidRequest, validation.ErrorCode);
            Assert.Contains(expectedMessage, validation.Message);
        }

        [Fact]
        public void Request_RefusesNamesLongerThanTheLimitAndSaysTheLength()
        {
            var name = new string('n', BimRunTransactionRequest.MaxNameLength + 1);

            var validation = new BimRunTransactionRequest { Name = name, Code = "pass" }.Validate();

            Assert.False(validation.Success);
            Assert.Contains("at most 120 characters; got 121", validation.Message);
        }

        [Theory]
        [InlineData(1, true)]
        [InlineData(90, true)]
        [InlineData(0, false)]
        [InlineData(91, false)]
        [InlineData(-5, false)]
        public void Request_TimeoutMustStayInsideTheHttpBudget(int timeoutSeconds, bool valid)
        {
            var validation = new BimRunTransactionRequest
            {
                Name = "Rename",
                Code = "pass",
                TimeoutSeconds = timeoutSeconds
            }.Validate();

            Assert.Equal(valid, validation.Success);
        }

        [Fact]
        public void Request_TimeoutBudgetFitsUnderTheClientReadTimeout()
        {
            // Queue pickup (10 s) + setup (4 s) + script + return allowance (1 s)
            // + commit grace (8 s) must stay under the 120 s read timeout of
            // bridge.py and the agent dispatcher.
            Assert.True(10 + 4 + BimRunTransactionRequest.MaxTimeoutSeconds + 1 + 8 < 120);
        }

        [Fact]
        public void Request_DocumentKeyIsOptionalAndBounded()
        {
            var without = new BimRunTransactionRequest { Name = "Rename", Code = "pass" };
            var with = new BimRunTransactionRequest
            {
                Name = "Rename",
                Code = "pass",
                DocumentKey = "file-document-v1:abc"
            };
            var tooLong = new BimRunTransactionRequest
            {
                Name = "Rename",
                Code = "pass",
                DocumentKey = new string('k', BimRunTransactionRequest.MaxDocumentKeyLength + 1)
            };

            Assert.True(without.Validate().Success);
            Assert.False(without.HasDocumentKey);
            Assert.True(with.Validate().Success);
            Assert.True(with.HasDocumentKey);
            var refused = tooLong.Validate();
            Assert.False(refused.Success);
            Assert.Equal(BimErrorCode.InvalidRequest, refused.ErrorCode);
            Assert.Contains("documentKey must be at most 300 characters; got 301", refused.Message);
        }

        [Theory]
        [InlineData("")]
        [InlineData("   ")]
        public void Request_ABlankDocumentKeyIsRefusedInsteadOfSilentlyDisablingTheGuard(string blank)
        {
            var request = new BimRunTransactionRequest { Name = "Rename", Code = "pass", DocumentKey = blank };

            var validation = request.Validate();

            Assert.False(validation.Success);
            Assert.Equal(BimErrorCode.InvalidRequest, validation.ErrorCode);
            Assert.Contains("documentKey was given but is blank", validation.Message);
            Assert.Contains("Leave documentKey out", validation.Message);
            // Had it passed validation, the guard would still be on, not off.
            Assert.True(request.HasDocumentKey);
        }

        private static BimTransactionScriptResult HostRun(
            bool hostReturned = true,
            string? hostError = null,
            bool completed = true,
            string? stage = "done",
            string? scriptError = null,
            string? traceback = null,
            string? output = "",
            bool outputTruncated = false,
            string? resultJson = null,
            string? resultOmittedReason = null)
        {
            return BimTransactionScriptResult.FromHostRun(
                hostReturned, hostError, completed, stage, scriptError, traceback,
                output, outputTruncated, string.Empty, false, resultJson, resultOmittedReason);
        }

        [Fact]
        public void ScriptResult_SuccessNeedsTheHostToSeeTheReturnAndTheScriptToReportCompletion()
        {
            var result = HostRun(output: "hi\n", resultJson: "{\"ids\":[1,2]}");

            Assert.True(result.Success);
            Assert.True(result.HostObservedReturn);
            Assert.False(result.ScriptRaised);
            Assert.Equal("done", result.Stage);
            Assert.Equal("hi\n", result.Output);
            Assert.Equal(2, result.Result!["ids"]!.AsArray().Count);
            Assert.Null(result.Result.Parent);
        }

        [Fact]
        public void ScriptResult_ScriptReportingCompletionIsNotEnoughIfTheHostSawTheEngineFail()
        {
            // The script-side signal alone must never authorize a commit.
            var result = HostRun(hostReturned: false, hostError: "engine fault", completed: true);

            Assert.False(result.Success);
            Assert.False(result.ScriptRaised);
            Assert.Equal("engine fault", result.Error);
        }

        [Fact]
        public void ScriptResult_HostSeeingAReturnIsNotEnoughIfTheScriptNeverReportedCompletion()
        {
            var result = HostRun(hostReturned: true, completed: false, stage: "run");

            Assert.False(result.Success);
            Assert.Contains("did not reach its end (stage 'run')", result.Error);
        }

        [Fact]
        public void ScriptResult_AScriptExceptionKeepsItsErrorAndTraceback()
        {
            var result = HostRun(
                hostReturned: false,
                hostError: "wall type not found",
                completed: false,
                stage: "run",
                scriptError: "ValueError: wall type not found",
                traceback: "Traceback...\nValueError: wall type not found",
                output: "before");

            Assert.False(result.Success);
            Assert.True(result.ScriptRaised);
            Assert.Equal("ValueError: wall type not found", result.Error);
            Assert.EndsWith("ValueError: wall type not found", result.Traceback);
            Assert.Equal("before", result.Output);
            Assert.Null(result.Result);
        }

        [Fact]
        public void ScriptResult_AReportedScriptErrorWinsEvenIfBothOtherSignalsLookFine()
        {
            var result = HostRun(hostReturned: true, completed: true, scriptError: "ValueError: x");

            Assert.False(result.Success);
            Assert.True(result.ScriptRaised);
        }

        [Fact]
        public void ScriptResult_NotRunCarriesTheReasonAndIsNeverSuccess()
        {
            var result = BimTransactionScriptResult.NotRun("Rhino's Python 3 script engine is not available.");

            Assert.False(result.Success);
            Assert.False(result.HostObservedReturn);
            Assert.False(result.ScriptRaised);
            Assert.Equal("none", result.Stage);
            Assert.Equal("Rhino's Python 3 script engine is not available.", result.Error);
        }

        [Fact]
        public void ScriptResult_TruncatesLongOutputAndKeepsTheProducersFlag()
        {
            var cut = HostRun(output: new string('x', BimTransactionScriptResult.MaxStreamLength + 10));
            var flagged = HostRun(output: "short", outputTruncated: true);

            Assert.Equal(BimTransactionScriptResult.MaxStreamLength, cut.Output.Length);
            Assert.True(cut.OutputTruncated);
            Assert.Equal("short", flagged.Output);
            Assert.True(flagged.OutputTruncated);
        }

        [Fact]
        public void ScriptResult_LongTracebackKeepsItsEnd()
        {
            var traceback = new string('t', BimTransactionScriptResult.MaxTracebackLength) + "ValueError: the cause";

            var result = HostRun(
                hostReturned: false, completed: false, stage: "run",
                scriptError: "ValueError: the cause", traceback: traceback);

            Assert.EndsWith("ValueError: the cause", result.Traceback);
            Assert.StartsWith("[...truncated...]", result.Traceback);
        }

        [Fact]
        public void ScriptResult_OversizedResultIsOmittedWithAReasonButStaysSuccess()
        {
            var json = "\"" + new string('r', BimTransactionScriptResult.MaxResultJsonLength) + "\"";

            var result = HostRun(resultJson: json);

            Assert.True(result.Success);
            Assert.Null(result.Result);
            Assert.Contains("the limit is 50000", result.ResultOmittedReason);
        }

        [Fact]
        public void ScriptResult_ADeeplyNestedResultIsOmittedAndDoesNotFailTheScript()
        {
            // Small, valid JSON, but deeper than the reader accepts. This must
            // cost the caller the return value only, never the edit.
            var json = new string('[', 80) + new string(']', 80);

            var result = HostRun(resultJson: json);

            Assert.True(result.Success);
            Assert.Null(result.Result);
            Assert.Contains("could not be read back as JSON", result.ResultOmittedReason);
            Assert.Contains("nested at most 32 deep", result.ResultOmittedReason);
        }

        [Fact]
        public void ScriptResult_MalformedResultTextIsOmittedAndDoesNotFailTheScript()
        {
            var result = HostRun(resultJson: "{not json");

            Assert.True(result.Success);
            Assert.Null(result.Result);
            Assert.NotNull(result.ResultOmittedReason);
        }

        [Fact]
        public void ScriptResult_KeepsTheProducersOmissionReason()
        {
            var result = HostRun(resultOmittedReason: "result was not returned: result has a dict key of type int");

            Assert.True(result.Success);
            Assert.Null(result.Result);
            Assert.Contains("dict key of type int", result.ResultOmittedReason);
        }
    }
}
