using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;
using Rook.Handlers;
using Rook.InternalBridge;
using Xunit;

namespace Rook.Tests.InternalBridge
{
    public sealed class GrasshopperDispatchContextTests
    {
        private static readonly Guid IntendedId = Guid.Parse("11111111-1111-1111-1111-111111111111");
        private static readonly Guid DecoyId = Guid.Parse("22222222-2222-2222-2222-222222222222");

        [Fact]
        public void GuardedMutation_UsesTheDocumentCapturedDuringValidation()
        {
            var intended = new FakeGhDocument(IntendedId);
            var decoy = new FakeGhDocument(DecoyId);
            var source = new SwitchingSource(intended, decoy);
            object? operatedOn = null;

            var result = GrasshopperDispatchContext.Execute(
                source,
                GhManagedDispatchScope.Mutation,
                IntendedId.ToString("D"),
                () =>
                {
                    operatedOn = GrasshopperDispatchContext.Current!.Document;
                    return new ApiResponse { Success = true, Data = new Dictionary<string, object?>() };
                });

            Assert.True(result.Success);
            Assert.Same(intended, operatedOn);
            Assert.Equal(1, source.CaptureCount);
            Assert.Equal(IntendedId.ToString("D"), Data(result).GetProperty("ghDocumentId").GetString());
        }

        [Theory]
        [InlineData(null, "gh_target_required")]
        [InlineData("", "invalid_arguments")]
        [InlineData("not-a-guid", "invalid_arguments")]
        [InlineData("11111111-1111-1111-1111-11111111111A", "invalid_arguments")]
        public void GuardedMutation_RejectsMissingOrNoncanonicalIdentity(
            string? expected,
            string error)
        {
            var source = new SwitchingSource(new FakeGhDocument(IntendedId));

            var result = GrasshopperDispatchContext.Execute(
                source,
                GhManagedDispatchScope.Mutation,
                expected,
                () => throw new InvalidOperationException("operation must not run"));

            Assert.False(result.Success);
            Assert.Equal(error, Data(result).GetProperty("error").GetString());
            Assert.Equal(0, source.CaptureCount);
        }

        [Fact]
        public void GuardedMutation_RejectsMissingAndChangedActiveDocumentsBeforeOperation()
        {
            var unavailable = new SwitchingSource(null);
            var unavailableResult = GrasshopperDispatchContext.Execute(
                unavailable,
                GhManagedDispatchScope.Mutation,
                IntendedId.ToString("D"),
                () => throw new InvalidOperationException("operation must not run"));

            var changed = new SwitchingSource(new FakeGhDocument(DecoyId));
            var changedResult = GrasshopperDispatchContext.Execute(
                changed,
                GhManagedDispatchScope.Mutation,
                IntendedId.ToString("D"),
                () => throw new InvalidOperationException("operation must not run"));

            Assert.Equal("gh_target_unavailable", Data(unavailableResult).GetProperty("error").GetString());
            Assert.Equal("gh_target_changed", Data(changedResult).GetProperty("error").GetString());
            Assert.Equal(1, unavailable.CaptureCount);
            Assert.Equal(1, changed.CaptureCount);
        }

        [Fact]
        public void Observation_ProjectsTheCapturedDocumentIdentity()
        {
            var document = new FakeGhDocument(IntendedId);
            var source = new SwitchingSource(document);

            var result = GrasshopperDispatchContext.Execute(
                source,
                GhManagedDispatchScope.Observation,
                null,
                () => new ApiResponse
                {
                    Success = true,
                    Data = new Dictionary<string, object?> { ["observed"] = true },
                });

            Assert.True(result.Success);
            Assert.Equal(IntendedId.ToString("D"), Data(result).GetProperty("ghDocumentId").GetString());
            Assert.Equal(1, source.CaptureCount);
        }

        [Fact]
        public void Observation_WithLatchedIdentityRejectsChangedDocumentBeforeOperation()
        {
            var source = new SwitchingSource(new FakeGhDocument(DecoyId));

            var result = GrasshopperDispatchContext.Execute(
                source,
                GhManagedDispatchScope.Observation,
                IntendedId.ToString("D"),
                () => throw new InvalidOperationException("operation must not run"));

            Assert.False(result.Success);
            Assert.Equal("gh_target_changed", Data(result).GetProperty("error").GetString());
            Assert.Equal(1, source.CaptureCount);
        }

        [Fact]
        public void ObservationProjection_PreservesTheBridgeCamelCaseWireContract()
        {
            var result = GrasshopperDispatchContext.Execute(
                new SwitchingSource(new FakeGhDocument(IntendedId)),
                GhManagedDispatchScope.Observation,
                null,
                () => new ApiResponse
                {
                    Success = true,
                    Data = new { ExistingField = "kept" },
                });

            var data = Data(result);
            Assert.Equal("kept", data.GetProperty("existingField").GetString());
            Assert.False(data.TryGetProperty("ExistingField", out _));
        }

        [Fact]
        public void Transition_CapturesAndReturnsOnlyTheResultingDocumentIdentity()
        {
            var source = new SwitchingSource(null);

            var result = GrasshopperDispatchContext.Execute(
                source,
                GhManagedDispatchScope.Transition,
                null,
                () =>
                {
                    Assert.Equal(0, source.CaptureCount);
                    source.Current = new FakeGhDocument(IntendedId);
                    return new ApiResponse
                    {
                        Success = true,
                        Data = new Dictionary<string, object?> { ["opened"] = true },
                    };
                });

            Assert.True(result.Success);
            Assert.Equal(IntendedId.ToString("D"), Data(result).GetProperty("ghDocumentId").GetString());
            Assert.Equal(1, source.CaptureCount);
        }

        [Fact]
        public void DispatchContext_RestoresThePriorContextAfterException()
        {
            var outer = new SwitchingSource(new FakeGhDocument(IntendedId));
            var inner = new SwitchingSource(new FakeGhDocument(DecoyId));

            GrasshopperDispatchContext.Execute(
                outer,
                GhManagedDispatchScope.Observation,
                null,
                () =>
                {
                    Assert.Equal(IntendedId, GrasshopperDispatchContext.Current!.DocumentId);
                    Assert.Throws<InvalidOperationException>(() =>
                        GrasshopperDispatchContext.Execute(
                            inner,
                            GhManagedDispatchScope.Observation,
                            null,
                            () => throw new InvalidOperationException("boom")));
                    Assert.Equal(IntendedId, GrasshopperDispatchContext.Current!.DocumentId);
                    return new ApiResponse { Success = true, Data = new Dictionary<string, object?>() };
                });

            Assert.Null(GrasshopperDispatchContext.Current);
        }

        [Fact]
        public void LockedRhinoDocument_DoesNotFallBackWhenSerialNoLongerResolves()
        {
            var active = new object();

            var resolved = DocumentContext.ResolveDocument(
                42,
                _ => (object?)null,
                () => active);

            Assert.Null(resolved);
            Assert.Same(
                active,
                DocumentContext.ResolveDocument<object>(null, _ => null, () => active));
        }

        [Fact]
        public void Registrar_ConsumesTheServiceOwnedScopeAtTheCommonCallbackBoundary()
        {
            var document = new FakeGhDocument(IntendedId);
            var source = new SwitchingSource(document);
            var requestJson = JsonSerializer.Serialize(new Dictionary<string, object?>
            {
                ["_rookGhDispatchScope"] = "mutation",
                ["_rookExpectedGhDocumentId"] = IntendedId.ToString("D"),
                ["value"] = 12,
            });

            var result = NativeGhBridgeRegistrar.ExecuteGrasshopperDispatchForTests(
                requestJson,
                source,
                () =>
                {
                    Assert.Same(document, GrasshopperDispatchContext.Current!.Document);
                    return new ApiResponse
                    {
                        Success = true,
                        Data = new Dictionary<string, object?> { ["updated"] = true },
                    };
                });

            Assert.True(result.Success);
            Assert.Equal(1, source.CaptureCount);
            Assert.Equal(
                IntendedId.ToString("D"),
                Data(result).GetProperty("ghDocumentId").GetString());
        }

        [Fact]
        public void GrasshopperCore_ObservesTheCapturedDocumentWithoutReresolvingActiveCanvas()
        {
            var document = new FakeGhDocument(IntendedId);
            var source = new SwitchingSource(document);

            var result = GrasshopperDispatchContext.Execute(
                source,
                GhManagedDispatchScope.Observation,
                null,
                () =>
                {
                    var status = new GrasshopperCore().GetStatus();
                    Assert.True(status.Success);
                    Assert.Equal(IntendedId.ToString("D"), status.Data!.DocumentId);
                    return new ApiResponse { Success = true, Data = new Dictionary<string, object?>() };
                });

            Assert.True(result.Success);
            Assert.Equal(1, source.CaptureCount);
        }

        [Fact]
        public void GrasshopperCore_PreservesLegacyDocumentIdentityOutsidePanelCustody()
        {
            var legacyId = Guid.Parse("33333333-3333-3333-3333-333333333333");
            var document = new LegacyGhDocument(legacyId);
            var resolver = typeof(GrasshopperCore).GetMethod(
                "GetObservedDocumentId",
                BindingFlags.Static | BindingFlags.NonPublic);

            Assert.NotNull(resolver);
            Assert.Equal(
                legacyId.ToString(),
                resolver!.Invoke(null, new object?[] { document, null }));
            Assert.Equal(
                IntendedId.ToString("D"),
                resolver.Invoke(null, new object?[] { document, IntendedId }));
        }

        [Fact]
        public void GrasshopperHandler_ResolvesTheCapturedDocumentWithoutRereadingActiveCanvas()
        {
            var document = new FakeGhDocument(IntendedId);
            var source = new SwitchingSource(document);
            var handler = new GrasshopperHandler();
            var getGrasshopper = typeof(GrasshopperHandler).GetMethod(
                "GetGrasshopper",
                BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.NotNull(getGrasshopper);

            var result = GrasshopperDispatchContext.Execute(
                source,
                GhManagedDispatchScope.Observation,
                null,
                () =>
                {
                    var resolved = getGrasshopper!.Invoke(handler, new object[] { true });
                    Assert.NotNull(resolved);
                    Assert.Same(document, resolved!.GetType().GetProperty("Document")!.GetValue(resolved));
                    return new ApiResponse { Success = true, Data = new Dictionary<string, object?>() };
                });

            Assert.True(result.Success);
            Assert.Equal(1, source.CaptureCount);
        }

        private static JsonElement Data(ApiResponse response) =>
            JsonSerializer.SerializeToElement(response.Data);

        private sealed class SwitchingSource : IGrasshopperDispatchSource
        {
            private readonly object? _second;

            internal SwitchingSource(object? first, object? second = null)
            {
                Current = first;
                _second = second;
            }

            internal object? Current { get; set; }
            internal int CaptureCount { get; private set; }

            public GrasshopperDispatchCapture Capture()
            {
                CaptureCount++;
                var document = CaptureCount == 1 ? Current : _second;
                return document is null
                    ? GrasshopperDispatchCapture.Unavailable("no active document")
                    : GrasshopperDispatchCapture.Available(
                        typeof(SwitchingSource).Assembly,
                        new object(),
                        document);
            }
        }

        private sealed class FakeGhDocument
        {
            internal FakeGhDocument(Guid id)
            {
                DocumentID = id;
            }

            public Guid DocumentID { get; }
            public object[] Objects { get; } = Array.Empty<object>();
            public string FilePath { get; } = string.Empty;
            public string DisplayName { get; } = "Fixture";
        }

        private sealed class LegacyGhDocument
        {
            internal LegacyGhDocument(Guid id)
            {
                DocumentGuid = id;
            }

            public Guid DocumentGuid { get; }
        }
    }
}
