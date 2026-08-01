using System.Collections.Generic;
using Rook.Handlers;
using Xunit;

namespace Rook.Tests.Handlers
{
    public sealed class GrasshopperConnectionSelectorTests
    {
        [Fact]
        public void ParseRequest_AcceptsExplicitIndices()
        {
            var parsed = GhConnectionSelectorResolver.TryParseRequest(
                "{\"sourceGuid\":\"source\",\"sourceIndex\":2,\"targetGuid\":\"target\",\"targetIndex\":7}",
                out var request,
                out var error);

            Assert.True(parsed, error);
            Assert.NotNull(request);
            Assert.Equal(2, request!.SourceSelector.Index);
            Assert.Equal(7, request.TargetSelector.Index);
            Assert.Null(request.SourceSelector.Name);
            Assert.Null(request.TargetSelector.Name);
        }

        [Fact]
        public void ParseRequest_PreservesNumericParamAliases()
        {
            var parsed = GhConnectionSelectorResolver.TryParseRequest(
                "{\"sourceGuid\":\"source\",\"sourceParam\":1,\"targetGuid\":\"target\",\"targetParam\":5}",
                out var request,
                out var error);

            Assert.True(parsed, error);
            Assert.Equal(1, request!.SourceSelector.Index);
            Assert.Equal(5, request.TargetSelector.Index);
        }

        [Theory]
        [InlineData("{\"sourceGuid\":\"source\",\"sourceParam\":\"R\",\"sourceIndex\":0,\"targetGuid\":\"target\"}", "Specify only one of sourceParam and sourceIndex")]
        [InlineData("{\"sourceGuid\":\"source\",\"targetGuid\":\"target\",\"targetParam\":\"A\",\"targetIndex\":0}", "Specify only one of targetParam and targetIndex")]
        [InlineData("{\"sourceGuid\":\"source\",\"sourceIndex\":-1,\"targetGuid\":\"target\"}", "sourceIndex must be a non-negative integer")]
        [InlineData("{\"sourceGuid\":\"source\",\"targetGuid\":\"target\",\"targetIndex\":1.5}", "targetIndex must be a non-negative integer")]
        [InlineData("{\"sourceGuid\":\"source\",\"sourceParam\":\"   \",\"targetGuid\":\"target\"}", "sourceParam must be a non-empty name or non-negative integer")]
        public void ParseRequest_RejectsAmbiguousOrMalformedSelectors(string json, string expectedError)
        {
            var parsed = GhConnectionSelectorResolver.TryParseRequest(json, out _, out var error);

            Assert.False(parsed);
            Assert.Equal(expectedError, error);
        }

        [Theory]
        [InlineData(5)]
        [InlineData(6)]
        [InlineData(7)]
        public void Resolve_UsesRequestedHighIndexAndReturnsActualMetadata(int requestedIndex)
        {
            var component = ComponentWithInputs(
                new FakeParam("Input 0", "I0"),
                new FakeParam("Input 1", "I1"),
                new FakeParam("Input 2", "I2"),
                new FakeParam("Input 3", "I3"),
                new FakeParam("Input 4", "I4"),
                new FakeParam("Input 5", "I5"),
                new FakeParam("Input 6", "I6"),
                new FakeParam("Input 7", "I7"));

            var resolved = GhConnectionSelectorResolver.TryResolve(
                component,
                isInput: true,
                new GhConnectionSelector(index: requestedIndex, name: null),
                out var parameter,
                out var error);

            Assert.True(resolved, error);
            Assert.Same(component.Params.Input[requestedIndex], parameter.Value);
            Assert.Equal(requestedIndex, parameter.Index);
            Assert.Equal($"Input {requestedIndex}", parameter.Name);
        }

        [Fact]
        public void Resolve_UsesNameOrNicknameAndReturnsCanonicalName()
        {
            var component = ComponentWithInputs(
                new FakeParam("Mesh", "M"),
                new FakeParam("Source Curves", "C"));

            var resolved = GhConnectionSelectorResolver.TryResolve(
                component,
                isInput: true,
                new GhConnectionSelector(index: null, name: "c"),
                out var parameter,
                out var error);

            Assert.True(resolved, error);
            Assert.Same(component.Params.Input[1], parameter.Value);
            Assert.Equal(1, parameter.Index);
            Assert.Equal("Source Curves", parameter.Name);
        }

        [Fact]
        public void Resolve_AllowsOmissionOnlyForSingletonCollections()
        {
            var singleton = ComponentWithInputs(new FakeParam("Only", "O"));
            Assert.True(GhConnectionSelectorResolver.TryResolve(
                singleton,
                isInput: true,
                default,
                out var parameter,
                out var singletonError), singletonError);
            Assert.Equal(0, parameter.Index);

            var multiple = ComponentWithInputs(
                new FakeParam("First", "A"),
                new FakeParam("Second", "B"));
            Assert.False(GhConnectionSelectorResolver.TryResolve(
                multiple,
                isInput: true,
                default,
                out _,
                out var multipleError));
            Assert.Equal("Target input selector is required because the component has 2 inputs", multipleError);
        }

        [Theory]
        [InlineData(2, null, "Target input index 2 is out of range for 2 inputs")]
        [InlineData(null, "Missing", "Target input parameter not found: Missing")]
        public void Resolve_RejectsOutOfRangeIndicesAndUnknownNames(int? index, string? name, string expectedError)
        {
            var component = ComponentWithInputs(
                new FakeParam("First", "A"),
                new FakeParam("Second", "B"));

            var resolved = GhConnectionSelectorResolver.TryResolve(
                component,
                isInput: true,
                new GhConnectionSelector(index, name),
                out _,
                out var error);

            Assert.False(resolved);
            Assert.Equal(expectedError, error);
        }

        [Fact]
        public void Resolve_ValidatesSelectorsForObjectsThatAreThemselvesParameters()
        {
            var parameterObject = new FakeParam("Slider", "S");

            Assert.True(GhConnectionSelectorResolver.TryResolve(
                parameterObject,
                isInput: false,
                default,
                out var resolved,
                out var omittedError), omittedError);
            Assert.Same(parameterObject, resolved.Value);
            Assert.Equal(0, resolved.Index);

            Assert.False(GhConnectionSelectorResolver.TryResolve(
                parameterObject,
                isInput: false,
                new GhConnectionSelector(1, null),
                out _,
                out var rangeError));
            Assert.Equal("Source output index 1 is out of range for 1 output", rangeError);
        }

        private static FakeComponent ComponentWithInputs(params FakeParam[] inputs)
        {
            return new FakeComponent(inputs, new[] { new FakeParam("Result", "R") });
        }

        private sealed class FakeComponent
        {
            public FakeComponent(IReadOnlyList<FakeParam> inputs, IReadOnlyList<FakeParam> outputs)
            {
                Params = new FakeParams(inputs, outputs);
            }

            public FakeParams Params { get; }
        }

        private sealed class FakeParams
        {
            public FakeParams(IReadOnlyList<FakeParam> inputs, IReadOnlyList<FakeParam> outputs)
            {
                Input = inputs;
                Output = outputs;
            }

            public IReadOnlyList<FakeParam> Input { get; }
            public IReadOnlyList<FakeParam> Output { get; }
        }

        private sealed class FakeParam
        {
            public FakeParam(string name, string nickName)
            {
                Name = name;
                NickName = nickName;
            }

            public string Name { get; }
            public string NickName { get; }
            public IReadOnlyList<object> Sources { get; } = new List<object>();
            public IReadOnlyList<object> Recipients { get; } = new List<object>();
        }
    }
}
