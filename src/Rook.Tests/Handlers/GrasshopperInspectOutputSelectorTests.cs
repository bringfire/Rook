using System.Collections.Generic;
using System.Text.Json;
using Rook.Handlers;
using Xunit;

namespace Rook.Tests.Handlers
{
    public sealed class GrasshopperInspectOutputSelectorTests
    {
        [Fact]
        public void Parse_OmissionIsTheOnlyDefaultSelector()
        {
            var parsed = Parse("{}", out var selector, out var error);

            Assert.True(parsed, error?.Message);
            Assert.Null(selector.Param);
            Assert.Null(selector.OutputIndex);
        }

        [Theory]
        [InlineData("Result")]
        [InlineData("5")]
        [InlineData(" 5 ")]
        [InlineData("+5")]
        [InlineData("005")]
        public void Parse_PreservesExistingStringParamValues(string param)
        {
            var json = JsonSerializer.Serialize(new Dictionary<string, object?>
            {
                ["param"] = param,
            });

            var parsed = Parse(json, out var selector, out var error);

            Assert.True(parsed, error?.Message);
            Assert.Equal(param, selector.Param);
            Assert.Null(selector.OutputIndex);
        }

        [Theory]
        [InlineData("{\"outputIndex\":5}", 5)]
        [InlineData("{\"outputIndex\":\"5\"}", 5)]
        public void Parse_AcceptsIntegerAndNativeQueryStringOutputIndex(
            string json,
            int expectedIndex)
        {
            var parsed = Parse(json, out var selector, out var error);

            Assert.True(parsed, error?.Message);
            Assert.Null(selector.Param);
            Assert.Equal(expectedIndex, selector.OutputIndex);
        }

        [Theory]
        [InlineData("{\"param\":\"Result\",\"outputIndex\":0}", "selector", "Specify only one of param and outputIndex")]
        [InlineData("{\"param\":null}", "param", "param must be a non-empty string")]
        [InlineData("{\"param\":\"\"}", "param", "param must be a non-empty string")]
        [InlineData("{\"param\":\"   \"}", "param", "param must be a non-empty string")]
        [InlineData("{\"param\":5}", "param", "param must be a non-empty string")]
        [InlineData("{\"outputIndex\":null}", "outputIndex", "outputIndex must be a non-negative integer")]
        [InlineData("{\"outputIndex\":-1}", "outputIndex", "outputIndex must be a non-negative integer")]
        [InlineData("{\"outputIndex\":1.5}", "outputIndex", "outputIndex must be a non-negative integer")]
        [InlineData("{\"outputIndex\":true}", "outputIndex", "outputIndex must be a non-negative integer")]
        [InlineData("{\"outputIndex\":\"\"}", "outputIndex", "outputIndex must be a non-negative integer")]
        [InlineData("{\"outputIndex\":\"   \"}", "outputIndex", "outputIndex must be a non-negative integer")]
        [InlineData("{\"outputIndex\":\"five\"}", "outputIndex", "outputIndex must be a non-negative integer")]
        public void Parse_RejectsEveryExplicitMalformedOrConflictingSelector(
            string json,
            string expectedField,
            string expectedMessage)
        {
            var parsed = Parse(json, out _, out var error);

            Assert.False(parsed);
            Assert.NotNull(error);
            Assert.Equal(expectedField, error!.Field);
            Assert.Equal(expectedMessage, error.Message);
        }

        [Fact]
        public void Resolve_OmissionDefaultsToOutputZero()
        {
            var outputs = Outputs(8);

            var resolved = GhInspectOutputSelectorResolver.TryResolve(
                outputs,
                default,
                out var output,
                out var error);

            Assert.True(resolved, error?.Message);
            Assert.Same(outputs[0], output.Value);
            Assert.Equal(0, output.Index);
        }

        [Theory]
        [InlineData(5)]
        [InlineData(6)]
        [InlineData(7)]
        public void Resolve_ExplicitOutputIndexSelectsTheRequestedOutput(int outputIndex)
        {
            var outputs = Outputs(8);
            var selector = new GhInspectOutputSelector(param: null, outputIndex);

            var resolved = GhInspectOutputSelectorResolver.TryResolve(
                outputs,
                selector,
                out var output,
                out var error);

            Assert.True(resolved, error?.Message);
            Assert.Same(outputs[outputIndex], output.Value);
            Assert.Equal(outputIndex, output.Index);
        }

        [Theory]
        [InlineData("Output 6", 6)]
        [InlineData("O6", 6)]
        [InlineData("6", 6)]
        [InlineData(" 6 ", 6)]
        [InlineData("+6", 6)]
        [InlineData("006", 6)]
        public void Resolve_ParamRetainsNameNicknameAndNumericStringSemantics(
            string param,
            int expectedIndex)
        {
            var outputs = Outputs(8);
            var selector = new GhInspectOutputSelector(param, outputIndex: null);

            var resolved = GhInspectOutputSelectorResolver.TryResolve(
                outputs,
                selector,
                out var output,
                out var error);

            Assert.True(resolved, error?.Message);
            Assert.Same(outputs[expectedIndex], output.Value);
            Assert.Equal(expectedIndex, output.Index);
        }

        [Theory]
        [InlineData("Missing", null)]
        [InlineData("-1", null)]
        [InlineData("8", null)]
        [InlineData(null, -1)]
        [InlineData(null, 8)]
        public void Resolve_InvalidExplicitSelectorNeverFallsBackOrReadsOutputZero(
            string? param,
            int? outputIndex)
        {
            var outputs = Outputs(8);
            var selector = new GhInspectOutputSelector(param, outputIndex);

            var resolved = GhInspectOutputSelectorResolver.TryResolve(
                outputs,
                selector,
                out var output,
                out var error);

            Assert.False(resolved);
            Assert.Null(output.Value);
            Assert.NotNull(error);
            Assert.Equal(0, outputs[0].VolatileDataReadCount);
        }

        [Fact]
        public void Resolve_UnknownNameReturnsFixedFieldErrorWithoutEchoingSelector()
        {
            var outputs = Outputs(1);
            var selector = new GhInspectOutputSelector(new string('x', 10_000), outputIndex: null);

            var resolved = GhInspectOutputSelectorResolver.TryResolve(
                outputs,
                selector,
                out _,
                out var error);

            Assert.False(resolved);
            Assert.NotNull(error);
            Assert.Equal("param", error!.Field);
            Assert.Equal("Output parameter name was not found", error.Message);
        }

        private static bool Parse(
            string json,
            out GhInspectOutputSelector selector,
            out GhInspectOutputSelectorError? error)
        {
            var args = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(json);
            return GhInspectOutputSelectorResolver.TryParse(args, out selector, out error);
        }

        private static List<FakeOutput> Outputs(int count)
        {
            var outputs = new List<FakeOutput>();
            for (var index = 0; index < count; index++)
            {
                outputs.Add(new FakeOutput($"Output {index}", $"O{index}"));
            }

            return outputs;
        }

        private sealed class FakeOutput
        {
            public FakeOutput(string name, string nickName)
            {
                Name = name;
                NickName = nickName;
            }

            public string Name { get; }
            public string NickName { get; }
            public int VolatileDataReadCount { get; private set; }
            public object? VolatileData
            {
                get
                {
                    VolatileDataReadCount++;
                    return null;
                }
            }
        }
    }
}
