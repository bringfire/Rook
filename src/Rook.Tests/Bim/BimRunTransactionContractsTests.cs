using System.Text.Json.Nodes;
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
            // Idle wait (10 s) + script timeout + commit grace (15 s) must stay
            // under the 120 s read timeout of bridge.py and the agent dispatcher.
            Assert.True(10 + BimRunTransactionRequest.MaxTimeoutSeconds + 15 < 120);
        }

        [Fact]
        public void ScriptResult_SuccessPayloadCarriesOutputAndResult()
        {
            var result = BimTransactionScriptResult.Parse(
                "{\"success\":true,\"stage\":\"done\",\"output\":\"hi\\n\",\"stderr\":\"\",\"error\":\"\"," +
                "\"traceback\":\"\",\"result\":{\"ids\":[1,2]},\"resultOmittedReason\":null}");

            Assert.True(result.Success);
            Assert.True(result.PayloadPresent);
            Assert.Equal("done", result.Stage);
            Assert.Equal("hi\n", result.Output);
            Assert.Null(result.ResultOmittedReason);
            Assert.Equal(2, result.Result!["ids"]!.AsArray().Count);
            // The node must be attachable to a response object.
            Assert.Null(result.Result.Parent);
            var holder = new JsonObject { ["result"] = result.Result };
            Assert.Equal(1, holder["result"]!["ids"]![0]!.GetValue<int>());
        }

        [Fact]
        public void ScriptResult_FailurePayloadKeepsErrorAndTraceback()
        {
            var result = BimTransactionScriptResult.Parse(
                "{\"success\":false,\"stage\":\"run\",\"output\":\"before\",\"stderr\":\"\"," +
                "\"error\":\"ZeroDivisionError: division by zero\",\"traceback\":\"Traceback...\",\"result\":null}");

            Assert.False(result.Success);
            Assert.True(result.PayloadPresent);
            Assert.Equal("run", result.Stage);
            Assert.Equal("ZeroDivisionError: division by zero", result.Error);
            Assert.Equal("Traceback...", result.Traceback);
            Assert.Equal("before", result.Output);
            Assert.Null(result.Result);
        }

        [Theory]
        [InlineData(null)]
        [InlineData("")]
        [InlineData("{")]
        [InlineData("[1,2]")]
        public void ScriptResult_UnusablePayloadIsNeverSuccess(string? json)
        {
            var result = BimTransactionScriptResult.Parse(json);

            Assert.False(result.Success);
            Assert.False(result.PayloadPresent);
            Assert.NotEqual(string.Empty, result.Error);
        }

        [Theory]
        [InlineData("{\"stage\":\"done\"}")]
        [InlineData("{\"success\":\"true\",\"stage\":\"done\"}")]
        [InlineData("{\"success\":1,\"stage\":\"done\"}")]
        [InlineData("{\"success\":null,\"stage\":\"done\"}")]
        public void ScriptResult_OnlyLiteralTrueCountsAsSuccess(string json)
        {
            var result = BimTransactionScriptResult.Parse(json);

            Assert.False(result.Success);
            Assert.True(result.PayloadPresent);
            Assert.Equal("The script wrapper did not report success.", result.Error);
        }

        [Fact]
        public void ScriptResult_TruncatesLongOutputAndSaysSo()
        {
            var output = new string('x', BimTransactionScriptResult.MaxStreamLength + 10);
            var payload = new JsonObject
            {
                ["success"] = true,
                ["stage"] = "done",
                ["output"] = output,
                ["stderr"] = "short"
            };

            var result = BimTransactionScriptResult.Parse(payload.ToJsonString());

            Assert.Equal(BimTransactionScriptResult.MaxStreamLength, result.Output.Length);
            Assert.True(result.OutputTruncated);
            Assert.Equal("short", result.Stderr);
            Assert.False(result.StderrTruncated);
        }

        [Fact]
        public void ScriptResult_OversizedResultIsOmittedWithAReasonButStaysSuccess()
        {
            var payload = new JsonObject
            {
                ["success"] = true,
                ["stage"] = "done",
                ["result"] = new string('r', BimTransactionScriptResult.MaxResultJsonLength + 1)
            };

            var result = BimTransactionScriptResult.Parse(payload.ToJsonString());

            Assert.True(result.Success);
            Assert.Null(result.Result);
            Assert.Contains("the limit is 100000", result.ResultOmittedReason);
        }

        [Fact]
        public void ScriptResult_MissingCarriesTheReason()
        {
            var result = BimTransactionScriptResult.Missing("Rhino refused to start the script command.");

            Assert.False(result.Success);
            Assert.False(result.PayloadPresent);
            Assert.Equal("none", result.Stage);
            Assert.Equal("Rhino refused to start the script command.", result.Error);
        }
    }
}
