using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Handlers
{
    public sealed class GrasshopperDocumentLifecycleSourceTests
    {
        [Fact]
        public void ContextLookup_IsObservationalAndNeverCreatesDocuments()
        {
            var handler = ReadSource("src", "Rook", "Handlers", "GrasshopperHandler.cs");
            var handlerLookup = MethodSource(handler, "private GrasshopperContext GetGrasshopper", "private (bool Success");
            var core = ReadSource("src", "Rook", "InternalBridge", "GrasshopperCore.cs");
            var coreLookup = MethodSource(core, "private ResolvedGrasshopperContext ResolveContext", "private static string BuildNotReadyMessage");

            Assert.Contains("GetGrasshopper(bool requireDocument = true)", handlerLookup);
            Assert.DoesNotContain("createDocumentIfMissing", handler);
            Assert.DoesNotContain("Activator.CreateInstance", handlerLookup);
            Assert.Contains("private ResolvedGrasshopperContext ResolveContext()", coreLookup);
            Assert.DoesNotContain("createDocumentIfMissing", core);
            Assert.DoesNotContain("Activator.CreateInstance", coreLookup);
        }

        [Fact]
        public void OpenDocument_PreflightsBeforeTheExistingUiCallbackAndRepeatsDefensively()
        {
            var handler = ReadSource("src", "Rook", "Handlers", "GrasshopperHandler.cs");
            var open = MethodSource(handler, "public ApiResponse OpenDocument", "public ApiResponse NewDocument");
            var registrar = ReadSource("src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs");
            var callback = MethodSource(registrar, "private static int HandleOpenDocument", "private static int HandleNewDocument");

            Assert.Contains("internal readonly struct GhOpenDocumentPreflightResult", handler);
            Assert.Contains("public bool Success { get; init; }", handler);
            Assert.Contains("public string? Path { get; init; }", handler);
            Assert.Contains("public string? ErrorCode { get; init; }", handler);
            Assert.Contains("internal static GhOpenDocumentPreflightResult PreflightOpenDocument(string? body)", handler);
            Assert.DoesNotContain("public Exception", handler);

            AssertOrder(callback,
                "ReadUtf8(requestJsonUtf8, requestJsonLength)",
                "GrasshopperHandler.PreflightOpenDocument(requestJson)",
                "ExecuteApiResponseCallback(");
            Assert.Contains("WriteUtf8Response(", callback);
            Assert.Contains("PreflightOpenDocument(body)", open);
            Assert.DoesNotContain("RhinoApp.InvokeOnUiThread", open);
        }

        [Fact]
        public void NewDocument_UsesTheTransactionalLifecycleAndRunsAuxiliaryWorkOnlyAfterCommit()
        {
            var source = ReadSource("src", "Rook", "Handlers", "GrasshopperHandler.cs");
            var method = MethodSource(source, "public ApiResponse NewDocument", "public ApiResponse ExploreSelection");

            Assert.Contains("GetGrasshopper(requireDocument: false)", method);
            Assert.Contains("new GhDocumentLifecycle()", method);
            Assert.Contains("CreateNew()", method);
            Assert.DoesNotContain("AddNewDocument", method);
            Assert.DoesNotContain("Activator.CreateInstance", method);
            AssertOrder(method,
                "CreateNew()",
                "if (!lifecycleResult.Committed)",
                "EnsureReadinessSession(",
                "_idRegistry.Clear()",
                "RefreshCanvas(capturedCanvas, scheduleSolution: false)");
            Assert.Contains("GhDocumentLifecycleWarning.ReadinessAttachmentFailed", method);
            Assert.Contains("GhDocumentLifecycleWarning.IdRegistryResetFailed", method);
            Assert.Contains("GhDocumentLifecycleWarning.CanvasRefreshFailed", method);
            Assert.Contains("GhDocumentLifecycleWarning.TelemetryProjectionFailed", method);
            Assert.Contains("Success = true", method);
        }

        [Fact]
        public void OpenDocument_UsesTheTransactionalLifecycleWithoutTemporaryDocuments()
        {
            var source = ReadSource("src", "Rook", "Handlers", "GrasshopperHandler.cs");
            var method = MethodSource(source, "public ApiResponse OpenDocument", "public ApiResponse NewDocument");

            Assert.Contains("GetGrasshopper(requireDocument: false)", method);
            Assert.Contains("new GhDocumentLifecycle()", method);
            Assert.Contains("Open(preflight.Path!)", method);
            Assert.DoesNotContain("GH_DocumentIO", method);
            Assert.DoesNotContain("Activator.CreateInstance", method);
            Assert.DoesNotContain("SetValue(gh.Canvas", method);
            AssertOrder(method,
                "Open(preflight.Path!)",
                "if (!lifecycleResult.Committed)",
                "EnsureReadinessSession(",
                "_idRegistry.Clear()",
                "RefreshCanvas(capturedCanvas, scheduleSolution: false)",
                "ObjectCount");
            Assert.Contains("GhDocumentLifecycleWarning.ObjectCountFailed", method);
            Assert.Contains("Success = true", method);
        }

        [Fact]
        public void LifecycleFailuresExposeObservedFinalStateAndWarningsCannotReverseCommit()
        {
            var source = ReadSource("src", "Rook", "Handlers", "GrasshopperHandler.cs");
            var open = MethodSource(source, "public ApiResponse OpenDocument", "public ApiResponse NewDocument");
            var create = MethodSource(source, "public ApiResponse NewDocument", "public ApiResponse ExploreSelection");

            foreach (var method in new[] { open, create })
            {
                Assert.Contains("document_registered = lifecycleResult.DocumentRegistered", method);
                Assert.Contains("document_active = lifecycleResult.DocumentActive", method);
                Assert.Contains("rollback_attempted = lifecycleResult.RollbackAttempted", method);
                Assert.Contains("rollback_incomplete = lifecycleResult.RollbackIncomplete", method);
                Assert.Contains("lifecycleResult.AddWarning", method);
                Assert.Contains("Success = true", method);
            }
        }

        [Fact]
        public void LifecycleSuccessReportsUnknownObjectCountAndDuplicateReuseTruthfully()
        {
            var source = ReadSource("src", "Rook", "Handlers", "GrasshopperHandler.cs");
            var open = MethodSource(source, "public ApiResponse OpenDocument", "public ApiResponse NewDocument");
            var create = MethodSource(source, "public ApiResponse NewDocument", "public ApiResponse ExploreSelection");

            foreach (var method in new[] { open, create })
            {
                Assert.Contains("int? ObjectCount = null", method);
                Assert.Contains("if (objectsProp == null)", method);
                Assert.Contains("GhDocumentLifecycleWarning.ObjectCountFailed", method);
            }

            Assert.Contains("existingDocumentReused = lifecycleResult.PathAlreadyRegistered", open);
        }

        [Fact]
        public void NativeBridge_RoutesNewAndOpenThroughTheExistingUiBoundary()
        {
            var source = ReadSource("src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs");
            var open = MethodSource(source, "private static int HandleOpenDocument", "private static int HandleNewDocument");
            var create = MethodSource(source, "private static int HandleNewDocument", "private static int HandleSetReference");

            Assert.Contains("ExecuteApiResponseCallback(", open);
            Assert.Contains("requestJson => Handler.OpenDocument(requestJson)", open);
            Assert.Contains("ExecuteApiResponseCallback(", create);
            Assert.Contains("_ => Handler.NewDocument()", create);
        }

        [Fact]
        public void SupersededSolverRaceSpec_LinksToTheNormativeLifecycleDesign()
        {
            var source = ReadSource(
                "docs", "superpowers", "specs",
                "2026-06-13-rir-gh-solver-enabled-race-design.md");

            Assert.Contains(
                "[July 26 Grasshopper document lifecycle design](2026-07-26-rir-grasshopper-document-lifecycle-design.md)",
                source);
        }

        private static string ReadSource(params string[] path) => File.ReadAllText(Path.Combine(RepoRoot(), Path.Combine(path)));

        private static string MethodSource(string source, string startMarker, string endMarker)
        {
            var start = source.IndexOf(startMarker, StringComparison.Ordinal);
            Assert.True(start >= 0, $"Missing method marker: {startMarker}");
            var end = source.IndexOf(endMarker, start + startMarker.Length, StringComparison.Ordinal);
            Assert.True(end > start, $"Missing end marker: {endMarker}");
            return source.Substring(start, end - start);
        }

        private static void AssertOrder(string source, params string[] markers)
        {
            var prior = -1;
            foreach (var marker in markers)
            {
                var index = source.IndexOf(marker, prior + 1, StringComparison.Ordinal);
                Assert.True(index > prior, $"Expected '{marker}' after index {prior}.");
                prior = index;
            }
        }

        private static string RepoRoot()
        {
            var dir = new DirectoryInfo(Directory.GetCurrentDirectory());
            while (dir != null && !File.Exists(Path.Combine(dir.FullName, "src", "Rook", "Handlers", "GrasshopperHandler.cs")))
                dir = dir.Parent;
            Assert.NotNull(dir);
            return dir!.FullName;
        }
    }
}
