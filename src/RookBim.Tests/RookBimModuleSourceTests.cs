using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Xml.Linq;
using Xunit;

namespace RookBim.Tests
{
    public class RookBimModuleSourceTests
    {
        private const string ModuleType =
            "public static class RookBimModule";
        private const string DispatcherType =
            "public sealed class RevitApiDispatcher";
        private const string WorkItemType =
            "private sealed class RevitApiWorkItem<T>";
        private const string RuntimeType =
            "public sealed class RevitRookBimRuntime : IRookBimRuntime";
        private const string IdentitySerializerType =
            "public static class RevitIdentitySerializer";
        private static readonly string RepoRoot = FindRepoRoot();

        [Fact]
        public void SourceExtractor_IgnoresCommentedOutDeclarationsAndCalls()
        {
            var source = @"
internal sealed class Fixture
{
    // public void Target(string value) { CommentOnly(); }
    public void Target(string value)
    {
        ActualCall();
    }
}";

            var target = ExtractExecutableMember(
                source,
                "internal sealed class Fixture",
                "public void Target(string value)");

            Assert.Contains("ActualCall();", target);
            Assert.DoesNotContain("CommentOnly();", target);
        }

        [Fact]
        public void SourceExtractor_BindsTheRequestedOverloadAndExcludesSiblingBodies()
        {
            var source = @"
internal sealed class Fixture
{
    public void Target(int value)
    {
        InertSiblingCall();
    }

    public void Target(string value)
    {
        RequestedOverloadCall();
    }
}";

            var target = ExtractExecutableMember(
                source,
                "internal sealed class Fixture",
                "public void Target(string value)");

            Assert.Contains("RequestedOverloadCall();", target);
            Assert.DoesNotContain("InertSiblingCall();", target);
        }

        [Fact]
        public void SourceExtractor_LiteralsDoNotCorruptExecutableMemberBoundaries()
        {
            var source = @"
internal sealed class Fixture
{
    public void Target(string value)
    {
        var text = ""} // not a comment /* still text {"";
        var close = '}';
        var slash = '/';
        ActualCall();
    }
}";

            var target = ExtractExecutableMember(
                source,
                "internal sealed class Fixture",
                "public void Target(string value)");

            Assert.DoesNotContain("// not a comment /* still text", target);
            Assert.DoesNotContain("var close = '}';", target);
            Assert.Contains("ActualCall();", target);
        }

        [Fact]
        public void SourceExtractor_CodeMaskDoesNotTreatStringContentAsAnExecutableCall()
        {
            var source = @"
internal sealed class Fixture
{
    public void Target()
    {
        var decoy = ""RequiredCall();"";
        ActualCall();
    }
}";

            var executableCode = ExtractExecutableMember(
                source,
                "internal sealed class Fixture",
                "public void Target()");

            Assert.Contains("ActualCall();", executableCode);
            Assert.DoesNotContain("RequiredCall();", executableCode);
        }

        [Fact]
        public void SourceExtractor_TargetMethodStringCannotSatisfyPositiveCallContract()
        {
            var source = @"
internal sealed class Fixture
{
    public void Target()
    {
        var decoy = ""RequiredCall();"";
        ActualCall();
    }
}";

            var target = ExtractExecutableMember(
                source,
                "internal sealed class Fixture",
                "public void Target()");

            Assert.DoesNotContain("RequiredCall();", target);
            Assert.Contains("ActualCall();", target);
        }

        [Fact]
        public void SourceExtractor_InertOverloadCannotSatisfyTargetOverloadContract()
        {
            var source = @"
internal sealed class Fixture
{
    public void Target(int value)
    {
        RequiredCall();
    }

    public void Target(string value)
    {
        ActualCall();
    }
}";

            var target = ExtractExecutableMember(
                source,
                "internal sealed class Fixture",
                "public void Target(string value)");

            Assert.DoesNotContain("RequiredCall();", target);
            Assert.Contains("ActualCall();", target);
        }

        [Fact]
        public void SourceExtractor_SiblingTypeCannotSatisfyTargetTypeContract()
        {
            var source = @"
internal sealed class SiblingFixture
{
    public void Target(string value)
    {
        RequiredCall();
    }
}

internal sealed class Fixture
{
    public void Target(string value)
    {
        ActualCall();
    }
}";

            var target = ExtractExecutableMember(
                source,
                "internal sealed class Fixture",
                "public void Target(string value)");

            Assert.DoesNotContain("RequiredCall();", target);
            Assert.Contains("ActualCall();", target);
        }

        [Fact]
        public void SourceExtractor_DuplicateMatchingDeclarationsFailClosed()
        {
            var source = @"
internal sealed class Fixture
{
    public void Target(string value)
    {
        FirstCall();
    }

    public void Target(string value)
    {
        SecondCall();
    }
}";

            Assert.Throws<InvalidOperationException>(() =>
                ExtractExecutableMember(
                    source,
                    "internal sealed class Fixture",
                    "public void Target(string value)"));
        }

        [Fact]
        public void RookBimProject_TargetsNet48AndReferencesRevitApisPrivately()
        {
            var project = LoadProject("src/RookBim/RookBim.csproj");
            var rookProject = LoadProject("src/Rook/Rook.csproj");
            var text = Read("src/RookBim/RookBim.csproj");

            Assert.Equal("net48", ValueOf(project, "TargetFramework"));
            Assert.Equal("enable", ValueOf(project, "Nullable"));
            Assert.Equal("latest", ValueOf(project, "LangVersion"));
            Assert.Equal(ValueOf(rookProject, "Version"), ValueOf(project, "Version"));
            Assert.Equal("RookBIM", ValueOf(project, "Title"));
            Assert.DoesNotContain("RhinoInside.Revit", text, StringComparison.OrdinalIgnoreCase);

            var projectReference = project.Descendants("ProjectReference").Single();
            Assert.Equal("../Rook/Rook.csproj", NormalizeProjectPath(AttributeValue(projectReference, "Include")));

            AssertRevitReference(project, "RevitAPI");
            AssertRevitReference(project, "RevitAPIUI");
        }

        [Fact]
        public void RookProject_DoesNotReferenceRookBimProjectOrRevitApi()
        {
            var text = Read("src/Rook/Rook.csproj");
            var project = XDocument.Parse(text);
            var sourceFiles = Directory
                .GetFiles(Path.Combine(RepoRoot, "src", "Rook"), "*.cs", SearchOption.AllDirectories)
                .Where(path =>
                {
                    var normalized = path.Replace(Path.AltDirectorySeparatorChar, Path.DirectorySeparatorChar);
                    return normalized.IndexOf(Path.DirectorySeparatorChar + "obj" + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) < 0
                        && normalized.IndexOf(Path.DirectorySeparatorChar + "bin" + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) < 0;
                })
                .ToArray();
            var source = string.Join(Environment.NewLine, sourceFiles.Select(File.ReadAllText));

            Assert.DoesNotContain("RookBim.csproj", text, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("<Reference Include=\"Autodesk.Revit", text, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("<Reference Include=\"RevitAPI", text, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain(
                project.Descendants("ProjectReference"),
                reference => AttributeValue(reference, "Include").IndexOf("RookBim", StringComparison.OrdinalIgnoreCase) >= 0);
            Assert.DoesNotContain("using Autodesk.", source, StringComparison.Ordinal);
            Assert.DoesNotContain("Autodesk.Revit.", source, StringComparison.Ordinal);
            Assert.DoesNotContain("Type.GetType(\"RhinoInside.Revit", source, StringComparison.Ordinal);
            Assert.DoesNotContain("Assembly.Load(\"RhinoInside.Revit", source, StringComparison.Ordinal);
        }

        [Fact]
        public void RookSolution_DoesNotIncludeOptionalRookBimProjects()
        {
            var text = Read("Rook.sln");

            Assert.DoesNotContain("RookBim.csproj", text, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("RookBim.Tests.csproj", text, StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void RookBimModuleActivate_InstallsRevitRuntimeFromOptionalAssembly()
        {
            var text = Read("src/RookBim/RookBimModule.cs");

            Assert.Contains("public static class RookBimModule", text);
            Assert.Contains("public static void Activate()", text);
            Assert.Contains("IsLoaded(\"RevitAPIUI\")", text);
            Assert.Contains("IsLoaded(\"RhinoInside.Revit\")", text);
            Assert.Contains("new RookBimUnavailableRuntime", text);
            Assert.Contains("\"not_rhino_inside\"", text);
            Assert.Contains("RookBimRuntimeRegistry.Install", text);
            Assert.Contains("new RevitRookBimRuntime()", text);
            Assert.Contains("\"RookBim.dll\"", text);
        }

        [Fact]
        public void RookBimModuleActivate_RegistersModuleMetadataBeforeAnyLoadCheck()
        {
            var module = Read("src/RookBim/RookBimModule.cs");
            var activate = ExtractExecutableMember(
                module,
                ModuleType,
                "public static void Activate()");

            Assert.Equal(
                RemoveWhitespace(
                    "BimDiagnostics.RegisterModuleMetadata(typeof(RookBimModule).Assembly);"),
                RemoveWhitespace(FirstExecutableStatement(activate)));
            Assert.DoesNotContain("InitializeFromEnvironment", activate);
            Assert.DoesNotContain("GetEnvironmentVariable", activate);
        }

        [Fact]
        public void RevitDispatcher_CarriesExplicitContextThroughQueuedWorkItem()
        {
            var dispatcher = Read("src/RookBim/Revit/RevitApiDispatcher.cs");
            var invoke = ExtractExecutableMember(
                dispatcher,
                DispatcherType,
                "public Task<T> Invoke<T>(BimDiagnosticContext diagnostics, Func<UIApplication, T> work)");
            var invokeAbandonable = ExtractExecutableMember(
                dispatcher,
                DispatcherType,
                "internal RevitApiDispatch<T> InvokeAbandonable<T>(BimDiagnosticContext diagnostics, Func<UIApplication, T> work)");
            var workItemConstructor = ExtractExecutableMember(
                dispatcher,
                WorkItemType,
                "public RevitApiWorkItem(BimDiagnosticContext diagnostics, Func<UIApplication, T> work)");
            var execute = ExtractExecutableMember(
                dispatcher,
                WorkItemType,
                "public void Execute()");

            Assert.Contains("InvokeAbandonable(diagnostics, work).Task", invoke);
            Assert.Contains("new RevitApiWorkItem<T>(diagnostics, work)", invokeAbandonable);
            Assert.Contains("this.diagnostics = diagnostics", workItemConstructor);
            Assert.Contains("this.work = work", workItemConstructor);
            Assert.Contains("BimDiagnosticStage.RevitDispatchExecute", execute);
            Assert.Contains("work(ActiveUIApplication())", execute);
            Assert.Contains("BimDiagnostics.ObserveException(", execute);
            Assert.True(
                execute.IndexOf("BimDiagnosticOutcome.Start", StringComparison.Ordinal) <
                execute.IndexOf("work(ActiveUIApplication())", StringComparison.Ordinal));
            Assert.True(
                execute.IndexOf("work(ActiveUIApplication())", StringComparison.Ordinal) <
                execute.IndexOf("BimDiagnosticOutcome.Success", StringComparison.Ordinal));

            var executableDispatcher = ExecutableCode(dispatcher);
            Assert.DoesNotContain("AsyncLocal", executableDispatcher);
            Assert.DoesNotContain("[ThreadStatic]", executableDispatcher);
            Assert.DoesNotContain("ThreadLocal", executableDispatcher);
            Assert.DoesNotContain("CurrentCorrelation", executableDispatcher);
            Assert.DoesNotContain("CurrentDiagnostics", executableDispatcher);
            Assert.DoesNotContain("CurrentContext", executableDispatcher);
            Assert.DoesNotContain("GlobalCorrelation", executableDispatcher);
        }

        [Fact]
        public void RevitDispatcher_ObservesEnqueueAtTheExistingBoundaries()
        {
            var dispatcher = Read("src/RookBim/Revit/RevitApiDispatcher.cs");
            var invoke = ExtractExecutableMember(
                dispatcher,
                DispatcherType,
                "internal RevitApiDispatch<T> InvokeAbandonable<T>(BimDiagnosticContext diagnostics, Func<UIApplication, T> work)");

            var startIndex = invoke.IndexOf("BimDiagnosticOutcome.Start", StringComparison.Ordinal);
            var enqueueIndex = invoke.IndexOf("EnqueueIdlingAction", StringComparison.Ordinal);
            var successIndex = invoke.IndexOf("BimDiagnosticOutcome.Success", StringComparison.Ordinal);
            var catchIndex = invoke.IndexOf("catch (Exception ex)", StringComparison.Ordinal);
            var failureIndex = invoke.IndexOf("BimDiagnostics.ObserveException(", StringComparison.Ordinal);
            var completionIndex = invoke.IndexOf("item.TrySetException(ex);", StringComparison.Ordinal);

            Assert.Contains("BimDiagnosticStage.RevitDispatchEnqueue", invoke);
            Assert.True(startIndex >= 0 && enqueueIndex > startIndex);
            Assert.True(successIndex > enqueueIndex && catchIndex > successIndex);
            Assert.True(failureIndex > catchIndex && completionIndex > failureIndex);
        }

        [Fact]
        public void RevitTask7_UsesRhinoInsideHostContextDispatcherWithoutTransactions()
        {
            var dispatcher = Read("src/RookBim/Revit/RevitApiDispatcher.cs");
            var revitFiles = Directory
                .GetFiles(Path.Combine(RepoRoot, "src", "RookBim", "Revit"), "*.cs")
                .Select(File.ReadAllText);
            var combined = string.Join(Environment.NewLine, revitFiles);

            Assert.Contains("RhinoInside.Revit.Revit", dispatcher);
            Assert.Contains("EnqueueIdlingAction", dispatcher);
            Assert.Contains("ActiveUIApplication", dispatcher);
            Assert.Contains("Type.GetType", dispatcher);
            Assert.Contains("AppDomain.CurrentDomain", dispatcher);
            Assert.Contains("TargetInvocationException", dispatcher);
            Assert.Contains("TaskCompletionSource", dispatcher);
            Assert.Contains("new Action(item.Execute)", dispatcher);
            Assert.DoesNotContain("Task.Run", dispatcher);
            Assert.DoesNotContain("ExternalEvent.Create", dispatcher);
            Assert.DoesNotContain("IExternalEventHandler", dispatcher);
            Assert.DoesNotContain("Transaction", combined);
        }

        [Fact]
        public void RevitTask7_RuntimeUsesDispatcherForStatusAndActiveDocument()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var context = Read("src/RookBim/Revit/RevitContext.cs");
            var serializer = Read("src/RookBim/Revit/RevitIdentitySerializer.cs");

            Assert.Contains("RevitApiDispatcher", runtime);
            Assert.Contains("dispatcher.InvokeAbandonable", runtime);
            Assert.Contains("ActiveDocument(UIApplication", context);
            Assert.Contains("ActiveUiDocument(UIApplication", context);
            Assert.Contains("ActiveUIDocument", context);
            Assert.Contains("GetWorksharingCentralGUID", serializer);
            Assert.Contains("GuidSource", serializer);
            Assert.Contains("BimDocumentGuidSource.Unavailable", serializer);
            Assert.DoesNotContain("PathFallback", serializer);

            Assert.Contains("Available = true", runtime);
            Assert.Contains("Runtime = \"rookbim\"", runtime);
            Assert.Contains("Host = \"revit\"", runtime);
            Assert.Contains("Module = ModuleName", runtime);
            Assert.Contains("ErrorCode = \"no_active_document\"", runtime);
            Assert.Contains("BimErrorCode.NoActiveDocument", runtime);
            Assert.Contains("409", runtime);
        }

        [Fact]
        public void RevitTask7_ActiveDocumentResultUsesViewPropertyForCamelCaseContract()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");

            Assert.Contains("View = SerializeActiveView(uidoc, diagnostics)", runtime);
            Assert.Contains("public BimViewIdentity? View { get; set; }", runtime);
            Assert.DoesNotContain("ActiveView = SerializeActiveView(uidoc)", runtime);
            Assert.DoesNotContain("public BimViewIdentity? ActiveView { get; set; }", runtime);
        }

        [Fact]
        public void RevitRuntime_UsesOnlyActiveGraphicalViewForViewResolution()
        {
            var runtime = NormalizeLineEndings(
                Read("src/RookBim/Revit/RevitRookBimRuntime.cs"));
            var resolve = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private static View? ResolveActiveGraphicalView(UIDocument uidoc, BimQueryScope scope, BimDiagnosticContext diagnostics)");

            Assert.Contains("uidoc.ActiveGraphicalView", resolve);
            Assert.DoesNotContain("uidoc.ActiveView", ExecutableCode(runtime));
            Assert.DoesNotContain("document.ActiveView", ExecutableCode(runtime));
        }

        [Fact]
        public void RevitRuntime_ActiveViewProbeHasDisabledFastPathAndNoDocumentScopeViewRead()
        {
            var runtime = NormalizeLineEndings(
                Read("src/RookBim/Revit/RevitRookBimRuntime.cs"));
            var resolve = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private static View? ResolveActiveGraphicalView(UIDocument uidoc, BimQueryScope scope, BimDiagnosticContext diagnostics)");

            var documentReturnIndex = resolve.IndexOf(
                "if (scope != BimQueryScope.ActiveView)", StringComparison.Ordinal);
            var viewReadIndex = resolve.IndexOf("uidoc.ActiveGraphicalView", StringComparison.Ordinal);

            Assert.True(documentReturnIndex >= 0 && viewReadIndex > documentReturnIndex);
            Assert.Contains("return null;", resolve);
            Assert.Contains("return diagnostics.Enabled", resolve);
            Assert.Contains("BimDiagnosticProbe.Production(", resolve);
            Assert.Contains("BimDiagnosticStage.RevitViewActiveGraphical", resolve);
            Assert.Contains("() => uidoc.ActiveGraphicalView", resolve);
            Assert.Contains(": uidoc.ActiveGraphicalView;", resolve);
            Assert.Contains("BimDiagnosticDetailCode.NoActiveView", resolve);
            Assert.Equal(2, CountOccurrences(resolve, "uidoc.ActiveGraphicalView"));
            Assert.Equal(1, CountOccurrences(resolve, "() => uidoc.ActiveGraphicalView"));
            Assert.DoesNotContain("uidoc.ActiveView", resolve);
            Assert.DoesNotContain("document.ActiveView", resolve);
        }

        [Fact]
        public void RevitRuntime_CapturesContextBeforeQueueingAndPassesItThroughViewAndIdentity()
        {
            var runtime = NormalizeLineEndings(
                Read("src/RookBim/Revit/RevitRookBimRuntime.cs"));
            var dispatch = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private T Dispatch<T>(BimDiagnosticContext diagnostics, Func<UIApplication, T> work)");
            var dispatchWithTimeout = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private T DispatchWithTimeout<T>(BimDiagnosticContext diagnostics, Func<UIApplication, T> work, TimeSpan timeout)");
            var documentContext = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private BimApiResponse ExecuteInDocumentContext(BimDiagnosticContext diagnostics, string operation, Func<UIDocument, Document, BimApiResponse> work)");
            var activeDocument = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse ActiveDocument(BimDiagnosticContext diagnostics)");
            var queryElements = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse QueryElements(BimDiagnosticContext diagnostics, BimQueryElementsRequest request)");

            Assert.True(
                dispatch.IndexOf("var capturedDiagnostics = diagnostics;", StringComparison.Ordinal) <
                dispatch.IndexOf(
                    "dispatcher.InvokeAbandonable(capturedDiagnostics, work)",
                    StringComparison.Ordinal));
            Assert.True(
                dispatchWithTimeout.IndexOf("var capturedDiagnostics = diagnostics;", StringComparison.Ordinal) <
                dispatchWithTimeout.IndexOf(
                    "dispatcher.InvokeAbandonable(capturedDiagnostics, work)",
                    StringComparison.Ordinal));
            Assert.Contains(
                "return ExecuteInDocumentContext(\n" +
                "                diagnostics,",
                activeDocument);
            Assert.Contains(
                "DocumentIdentity(\n" +
                "                            document,\n" +
                "                            diagnostics,\n" +
                "                            includeAuxiliaryState: true)",
                activeDocument);
            Assert.Contains("SerializeActiveView(uidoc, diagnostics)", activeDocument);
            Assert.Contains(
                "return ExecuteInDocumentContext(\n" +
                "                diagnostics,",
                queryElements);
            Assert.Contains(
                "ResolveActiveGraphicalView(\n" +
                "                        uidoc, request.EffectiveScope, diagnostics)",
                queryElements);
            Assert.Contains("Dispatch(diagnostics, uiapp =>", documentContext);
            Assert.Contains("AcquireActiveUiDocument(uiapp, diagnostics)", documentContext);
            Assert.Contains("AcquireDocument(uidoc, diagnostics)", documentContext);

            var executableRuntime = ExecutableCode(runtime);
            Assert.DoesNotContain("AsyncLocal", executableRuntime);
            Assert.DoesNotContain("[ThreadStatic]", executableRuntime);
            Assert.DoesNotContain("ThreadLocal", executableRuntime);
            Assert.DoesNotContain("CurrentCorrelation", executableRuntime);
            Assert.DoesNotContain("CurrentDiagnostics", executableRuntime);
            Assert.DoesNotContain("CurrentContext", executableRuntime);
            Assert.DoesNotContain("GlobalCorrelation", executableRuntime);
        }

        [Fact]
        public void RevitRuntime_InstrumentsEveryExistingDocumentAcquisitionWithoutCachingReads()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var status = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimStatusResponse Status(BimDiagnosticContext diagnostics)");
            var elementInfo = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse ElementInfo(BimDiagnosticContext diagnostics, BimElementRequest request)");
            var parameters = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse ElementParameters(BimDiagnosticContext diagnostics, BimElementRequest request)");
            var select = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse SelectElements(BimDiagnosticContext diagnostics, BimSelectElementsRequest request)");
            var clear = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse ClearSelection(BimDiagnosticContext diagnostics)");
            var preset = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse ExportPreset(BimDiagnosticContext diagnostics, BimExportPresetRequest request)");
            var export = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse ExportElements(BimDiagnosticContext diagnostics, BimExportElementsRequest request)");
            var documentContext = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private BimApiResponse ExecuteInDocumentContext(BimDiagnosticContext diagnostics, string operation, Func<UIDocument, Document, BimApiResponse> work)");
            var acquireUiDocument = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private static UIDocument? AcquireActiveUiDocument(UIApplication uiapp, BimDiagnosticContext diagnostics)");
            var acquireDocument = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private static Document? AcquireDocument(UIDocument uidoc, BimDiagnosticContext diagnostics)");
            var acquireActiveDocument = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private static Document? AcquireActiveDocument(UIApplication uiapp, BimDiagnosticContext diagnostics)");

            Assert.Equal(1, CountOccurrences(status, "AcquireActiveDocument(uiapp, diagnostics)"));
            AssertAcquisitionCounts(documentContext, expectedUiDocument: 1, expectedDocument: 2);
            AssertAcquisitionCounts(elementInfo, expectedUiDocument: 1, expectedDocument: 2);
            AssertAcquisitionCounts(parameters, expectedUiDocument: 1, expectedDocument: 2);
            AssertAcquisitionCounts(select, expectedUiDocument: 1, expectedDocument: 1);
            AssertAcquisitionCounts(clear, expectedUiDocument: 1, expectedDocument: 1);
            AssertAcquisitionCounts(preset, expectedUiDocument: 1, expectedDocument: 2);
            AssertAcquisitionCounts(export, expectedUiDocument: 1, expectedDocument: 2);

            AssertDisabledProductionFastPath(
                acquireUiDocument,
                "() => RevitContext.ActiveUiDocument(uiapp)",
                "RevitContext.ActiveUiDocument(uiapp)");
            AssertDisabledProductionFastPath(
                acquireDocument,
                "() => uidoc.Document",
                "uidoc.Document");
            AssertDisabledProductionFastPath(
                acquireActiveDocument,
                "() => RevitContext.ActiveDocument(uiapp)",
                "RevitContext.ActiveDocument(uiapp)");
            Assert.Contains("BimDiagnosticStage.RevitDocumentAcquire", acquireUiDocument);
            Assert.Contains("BimDiagnosticStage.RevitDocumentAcquire", acquireDocument);
            Assert.Contains("BimDiagnosticStage.RevitDocumentAcquire", acquireActiveDocument);
        }

        [Fact]
        public void RevitIdentitySerializer_DetailedPathPreservesReadOrderAndIndependentWorksharedReads()
        {
            var serializer = NormalizeLineEndings(
                Read("src/RookBim/Revit/RevitIdentitySerializer.cs"));
            var detailed = ExtractExecutableMember(
                serializer,
                IdentitySerializerType,
                "public static BimDocumentIdentity DocumentIdentity(Document document, BimDiagnosticContext diagnostics, bool includeAuxiliaryState)");
            var central = ExtractExecutableMember(
                serializer,
                IdentitySerializerType,
                "private static Guid? GetWorksharingCentralGUID(Document document, BimDiagnosticContext diagnostics)");

            var centralCall = detailed.IndexOf(
                "GetWorksharingCentralGUID(document, diagnostics)", StringComparison.Ordinal);
            var title = detailed.IndexOf("BimDiagnosticStage.RevitDocumentTitle", StringComparison.Ordinal);
            var path = detailed.IndexOf("BimDiagnosticStage.RevitDocumentPath", StringComparison.Ordinal);
            var family = detailed.IndexOf("BimDiagnosticStage.RevitDocumentIsFamily", StringComparison.Ordinal);
            var outputWorkshared = detailed.IndexOf(
                "BimDiagnosticStage.RevitDocumentOutputIsWorkshared", StringComparison.Ordinal);

            Assert.True(centralCall >= 0 && title > centralCall);
            Assert.True(path > title && family > path && outputWorkshared > family);
            Assert.True(
                central.IndexOf(
                    "BimDiagnosticStage.RevitDocumentCentralIsWorkshared",
                    StringComparison.Ordinal) <
                central.IndexOf(
                    "BimDiagnosticStage.RevitDocumentCentralGuid",
                    StringComparison.Ordinal));
            Assert.Contains("() => document.IsWorkshared", central);
            Assert.Contains("() => document.IsWorkshared", detailed);
            Assert.DoesNotContain("IsWorkshared = centralIsWorkshared", detailed);
            Assert.DoesNotContain("IsWorkshared = isWorkshared", detailed);

            Assert.Equal(1, CountOccurrences(
                central,
                "catch (Autodesk.Revit.Exceptions.InapplicableDataException)"));
            Assert.Equal(1, CountOccurrences(
                central,
                "catch (Autodesk.Revit.Exceptions.InvalidOperationException)"));
            Assert.DoesNotContain("InternalException", central);
            Assert.DoesNotContain("InternalException", ExecutableCode(serializer));
        }

        [Fact]
        public void RevitIdentitySerializer_KeepsOneArgumentElementPathsUntraced()
        {
            var serializer = NormalizeLineEndings(
                Read("src/RookBim/Revit/RevitIdentitySerializer.cs"));
            var untraced = ExtractExecutableMember(
                serializer,
                IdentitySerializerType,
                "public static BimDocumentIdentity DocumentIdentity(Document document)");
            var element = ExtractExecutableMember(
                serializer,
                IdentitySerializerType,
                "public static BimElementIdentity ElementIdentity(Element element)");
            var resolve = ExtractExecutableMember(
                serializer,
                IdentitySerializerType,
                "public static BimElementResolveResult Resolve(Document document, BimElementIdentity? identity)");

            Assert.DoesNotContain("BimDiagnostic", untraced);
            Assert.Contains("DocumentIdentity(document)", element);
            Assert.Contains("DocumentMatches(DocumentIdentity(document), identity)", resolve);
            Assert.DoesNotContain("diagnostics", element);
            Assert.DoesNotContain("diagnostics", resolve);
        }

        [Fact]
        public void RevitIdentitySerializer_AuxiliaryStateIsGatedIndependentAndBehaviorNeutral()
        {
            var serializer = NormalizeLineEndings(
                Read("src/RookBim/Revit/RevitIdentitySerializer.cs"));
            var detailed = ExtractExecutableMember(
                serializer,
                IdentitySerializerType,
                "public static BimDocumentIdentity DocumentIdentity(Document document, BimDiagnosticContext diagnostics, bool includeAuxiliaryState)");
            var state = ExtractExecutableMember(
                serializer,
                IdentitySerializerType,
                "private static void ProbeDocumentState(Document document, BimDiagnosticContext diagnostics)");
            var classify = ExtractExecutableMember(
                serializer,
                IdentitySerializerType,
                "private static BimDiagnosticDetailCode ClassifyDocumentState(BimAuxiliaryProbeResult<bool> isModelInCloud, BimAuxiliaryProbeResult<bool> isDetached, BimAuxiliaryProbeResult<ModelPath> centralModelPath, BimAuxiliaryProbeResult<bool>? empty, BimAuxiliaryProbeResult<bool>? serverPath, BimAuxiliaryProbeResult<bool>? cloudPath)");

            var dtoIndex = detailed.IndexOf("var result = new BimDocumentIdentity", StringComparison.Ordinal);
            var probeIndex = detailed.IndexOf("ProbeDocumentState(document, diagnostics);", StringComparison.Ordinal);
            var returnIndex = detailed.IndexOf("return result;", StringComparison.Ordinal);
            Assert.True(dtoIndex >= 0 && probeIndex > dtoIndex && returnIndex > probeIndex);
            Assert.Contains("if (includeAuxiliaryState)", detailed);

            var disabledIndex = state.IndexOf("if (!diagnostics.Enabled)", StringComparison.Ordinal);
            var firstAuxiliary = state.IndexOf("BimDiagnosticProbe.Auxiliary", StringComparison.Ordinal);
            Assert.True(disabledIndex >= 0 && firstAuxiliary > disabledIndex);
            Assert.Contains("return;", state.Substring(disabledIndex, firstAuxiliary - disabledIndex));
            Assert.DoesNotContain("BimDiagnosticProbe.Production", state);
            Assert.Contains("() => document.IsModelInCloud", state);
            Assert.Contains("() => document.IsDetached", state);
            Assert.Contains("() => document.GetWorksharingCentralModelPath()", state);
            Assert.Contains("() => modelPath.Empty", state);
            Assert.Contains("() => modelPath.ServerPath", state);
            Assert.Contains("() => modelPath.CloudPath", state);
            Assert.Equal(6, CountOccurrences(state, "BimDiagnosticProbe.Auxiliary"));
            Assert.Equal(1, CountOccurrences(state, "GetWorksharingCentralModelPath()"));
            Assert.DoesNotContain("document.Title", state);
            Assert.DoesNotContain("document.PathName", state);
            Assert.DoesNotContain("CentralServerPath", state);

            var unknownGateIndex = classify.IndexOf(
                "if (!isModelInCloud.Known ||", StringComparison.Ordinal);
            var detachedIndex = classify.IndexOf(
                "return BimDiagnosticDetailCode.Detached;", StringComparison.Ordinal);
            Assert.True(unknownGateIndex >= 0 && detachedIndex > unknownGateIndex);
            Assert.Contains("!isDetached.Known", classify);
            Assert.Contains("!centralModelPath.Known", classify);
            Assert.Contains("!empty.HasValue || !empty.Value.Known", classify);
            Assert.Contains("!serverPath.HasValue || !serverPath.Value.Known", classify);
            Assert.Contains("!cloudPath.HasValue || !cloudPath.Value.Known", classify);
        }

        [Fact]
        public void RevitRuntime_ResolvesGraphicalViewOnlyWhenTheOperationRequiresIt()
        {
            var runtime = NormalizeLineEndings(
                Read("src/RookBim/Revit/RevitRookBimRuntime.cs"));
            var queryElements = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse QueryElements(BimDiagnosticContext diagnostics, BimQueryElementsRequest request)");
            var exportPreset = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse ExportPreset(BimDiagnosticContext diagnostics, BimExportPresetRequest request)");
            var exportElements = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse ExportElements(BimDiagnosticContext diagnostics, BimExportElementsRequest request)");

            Assert.Contains(
                "ResolveActiveGraphicalView(\n" +
                "                        uidoc, request.EffectiveScope, diagnostics)",
                queryElements);
            Assert.Contains(
                "ResolveActiveGraphicalView(\n" +
                "                            uidoc, request.EffectiveScope, diagnostics)",
                exportPreset);
            Assert.Contains(
                "request.HasSelector\n" +
                "                            ? ResolveActiveGraphicalView(\n" +
                "                                uidoc, request.Selector!.EffectiveScope, diagnostics)\n" +
                "                            : null",
                exportElements);

            var presetDocumentIndex = exportPreset.IndexOf(
                "var document = AcquireDocument(uidoc, diagnostics)!;",
                StringComparison.Ordinal);
            var presetOperationTryIndex = exportPreset.IndexOf("try", presetDocumentIndex, StringComparison.Ordinal);
            var presetViewIndex = exportPreset.IndexOf("ResolveActiveGraphicalView", StringComparison.Ordinal);
            Assert.True(
                presetDocumentIndex >= 0 &&
                presetOperationTryIndex > presetDocumentIndex &&
                presetViewIndex > presetOperationTryIndex);

            var exportDocumentIndex = exportElements.IndexOf(
                "var document = AcquireDocument(uidoc, diagnostics)!;",
                StringComparison.Ordinal);
            var exportOperationTryIndex = exportElements.IndexOf("try", exportDocumentIndex, StringComparison.Ordinal);
            var exportViewIndex = exportElements.IndexOf("ResolveActiveGraphicalView", StringComparison.Ordinal);
            Assert.True(
                exportDocumentIndex >= 0 &&
                exportOperationTryIndex > exportDocumentIndex &&
                exportViewIndex > exportOperationTryIndex);
        }

        [Fact]
        public void RevitRuntime_ActiveDocumentSerializesItsViewInsideTheOperationBoundary()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var activeDocument = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse ActiveDocument(BimDiagnosticContext diagnostics)");

            Assert.Contains("return ExecuteInDocumentContext", activeDocument);
            Assert.Contains("View = SerializeActiveView(uidoc, diagnostics)", activeDocument);
        }

        [Fact]
        public void RevitTask7_ElementIdSerializationUsesBoundedNullableConversion()
        {
            var serializer = Read("src/RookBim/Revit/RevitIdentitySerializer.cs");

            Assert.Contains("private const int InvalidElementIdValue = -1;", serializer);
            Assert.Contains("Id = ToInt32OrNull(view.Id) ?? InvalidElementIdValue", serializer);
            Assert.Contains("ElementId = ToInt32OrNull(element.Id)", serializer);
            Assert.Contains("private static int? ToInt32OrNull(ElementId? id)", serializer);
            Assert.Contains("if (value < int.MinValue || value > int.MaxValue)", serializer);
            Assert.Contains("return null;", serializer);
            Assert.DoesNotContain("Convert.ToInt32", serializer);
        }

        [Fact]
        public void RevitTask7_DispatchTimeoutAbandonsPendingWork()
        {
            var dispatcher = Read("src/RookBim/Revit/RevitApiDispatcher.cs");
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");

            Assert.Contains("InvokeAbandonable", dispatcher);
            Assert.Contains("public bool Abandon()", dispatcher);
            Assert.Contains("TryAbandon()", dispatcher);
            Assert.Contains("CompareExchange(ref state, Running, Pending)", dispatcher);
            Assert.Contains("CompareExchange(ref state, Abandoned, Pending)", dispatcher);
            Assert.Contains("TrySetCanceled", dispatcher);
            Assert.Contains(
                "var dispatch = dispatcher.InvokeAbandonable(capturedDiagnostics, work);",
                runtime);
            Assert.Contains("dispatch.Abandon();", runtime);
            Assert.Contains("throw new TimeoutException", runtime);
            Assert.Contains("Timed out waiting for RhinoInside Revit idling-queue execution.", runtime);
            Assert.DoesNotContain("Timed out waiting for Revit ExternalEvent execution.", runtime);
        }

        [Fact]
        public void RevitTask7_DispatchDoesNotMaskFaultedTasksWithAggregateException()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var dispatch = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private T Dispatch<T>(BimDiagnosticContext diagnostics, Func<UIApplication, T> work)");

            Assert.DoesNotContain(".Wait(DispatchTimeout)", dispatch);
            Assert.Contains("Task.WaitAny", dispatch);
            Assert.Contains("dispatch.Task.GetAwaiter().GetResult();", dispatch);
            Assert.Contains("DescribeDispatchException", runtime);
            Assert.Contains("AggregateException", runtime);
        }

        [Fact]
        public void RevitTask7_StatusDispatchFailureKeepsRookBimRuntime()
        {
            var runtime = NormalizeLineEndings(Read("src/RookBim/Revit/RevitRookBimRuntime.cs"));

            Assert.Contains(
                "catch (Exception ex)\n" +
                "            {\n" +
                "                return new BimStatusResponse\n" +
                "                {\n" +
                "                    Available = false,\n" +
                "                    Runtime = \"rookbim\",\n" +
                "                    ErrorCode = \"not_rhino_inside\",\n" +
                    "                    Message = $\"RookBIM could not enter the Revit API context: {DescribeDispatchException(ex)}\",\n" +
                "                    Host = \"unknown\",\n" +
                "                    Module = ModuleName\n" +
                "                };\n" +
                "            }",
                runtime);
            Assert.DoesNotContain("Runtime = \"unavailable\"", runtime);
        }

        [Fact]
        public void RevitTask10_SelectionServiceUsesResolvedIdentitiesAndUiSelectionOnly()
        {
            var service = Read("src/RookBim/Revit/RevitSelectionService.cs");
            var select = ExtractMethod(service, "public BimApiResponse Select(");
            var clear = ExtractMethod(service, "public BimApiResponse Clear(");

            Assert.Contains("internal sealed class RevitSelectionService", service);
            Assert.Contains("if (request == null || request.Identities == null || request.Identities.Count == 0)", select);
            Assert.Contains("BimErrorCode.InvalidScope", select);
            Assert.True(
                select.IndexOf("BimErrorCode.InvalidScope", StringComparison.Ordinal) <
                select.IndexOf("uiDocument.Selection.SetElementIds(ids)", StringComparison.Ordinal));
            Assert.Contains("RevitIdentitySerializer.Resolve(uiDocument.Document, identity)", select);
            Assert.Contains("if (!resolved.Success)", select);
            Assert.Contains("return BimApiResponse.Fail(", select);
            Assert.Contains("resolved.ErrorCode", select);
            Assert.Contains("uiDocument.Selection.SetElementIds(ids)", select);
            Assert.Contains("selectedCount = ids.Count", select);
            Assert.Contains("identities = selectedIdentities", select);
            Assert.Contains("document = RevitIdentitySerializer.DocumentIdentity(uiDocument.Document)", select);
            Assert.Contains("uiDocument.Selection.SetElementIds(new List<ElementId>())", clear);
            Assert.Contains("selectedCount = 0", clear);
            Assert.DoesNotContain("Transaction", service);
            Assert.DoesNotContain("OverrideGraphicSettings", service);
            Assert.DoesNotContain("TemporaryView", service);
        }

        [Fact]
        public void RevitTask10_RuntimeWiresSelectionThroughDispatcher()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var select = ExtractMethod(runtime, "public BimApiResponse SelectElements(");
            var clear = ExtractMethod(runtime, "public BimApiResponse ClearSelection(");

            Assert.Contains("private readonly RevitSelectionService selection;", runtime);
            Assert.Contains("this.selection = new RevitSelectionService();", runtime);
            Assert.Contains("return Dispatch(diagnostics, uiapp =>", select);
            Assert.Contains("return Dispatch(diagnostics, uiapp =>", clear);
            Assert.Contains("AcquireActiveUiDocument(uiapp, diagnostics)", select);
            Assert.Contains("AcquireActiveUiDocument(uiapp, diagnostics)", clear);
            Assert.Contains("BimErrorCode.NoActiveDocument", select);
            Assert.Contains("BimErrorCode.NoActiveDocument", clear);
            Assert.Contains("selection.Select(uidoc, request)", select);
            Assert.Contains("selection.Clear(uidoc)", clear);
            Assert.DoesNotContain("LaterToolUnavailable", select);
            Assert.DoesNotContain("LaterToolUnavailable", clear);
        }

        [Fact]
        public void RevitCategoryResolver_UsesLiveDocumentCategoryTableAsAuthority()
        {
            var resolver = Read("src/RookBim/Revit/RevitCategoryResolver.cs");

            Assert.Contains("internal sealed class RevitCategoryResolver", resolver);
            Assert.Contains("document.Settings.Categories", resolver);
            Assert.Contains("BimCategoryResolution", resolver);
            Assert.Contains("BimCategoryResolutionStrategy.BuiltInExact", resolver);
            Assert.Contains("BimCategoryResolutionStrategy.CategoryIdExact", resolver);
            Assert.Contains("BimCategoryResolutionStrategy.DocumentDisplayNameExact", resolver);
            Assert.Contains("BimCategoryResolutionStrategy.DocumentDisplayNameNormalized", resolver);
            Assert.Contains("BimCategoryResolutionStrategy.BuiltInTolerant", resolver);
            Assert.Contains("BimCategoryResolutionStrategy.CuratedAlias", resolver);
            Assert.Contains("MaxSuggestions = 5", resolver);
            Assert.Contains("BimCategoryResolutionStatus.Ambiguous", resolver);
            Assert.Contains("Queryable = entry.Summary.Id.HasValue", resolver);
            Assert.Contains("TrimTrailingPluralS(entry.NormalizedName), singularInput", resolver);
            Assert.Contains("private static int SuggestionRank(", resolver);
            Assert.Contains("private static int EditDistance(", resolver);
            Assert.Contains("OrderBy(candidate => candidate.Rank)", resolver);
            Assert.Contains("TryGetBuiltInCategory", resolver);
            Assert.Contains("TryBuildCategoryEntry", resolver);
            Assert.Contains("SafeCategoryId", resolver);
            Assert.Contains("SafeCategoryName", resolver);
            Assert.Contains("SafeCategoryType", resolver);
            Assert.Contains("catch (Autodesk.Revit.Exceptions.InternalException)", resolver);
            Assert.Contains("catch (Autodesk.Revit.Exceptions.InvalidOperationException)", resolver);
            Assert.Contains("SkippedCount", resolver);
            Assert.Contains("DegradedCount", resolver);
            Assert.Contains("Diagnostics", resolver);
            Assert.Contains("RecordSkip", resolver);
            Assert.Contains("RecordDegradation", resolver);
            Assert.Contains("SafeBuiltInCategory", resolver);
            Assert.Contains("ResolveBuiltIn(document, builtIn)", resolver);
            Assert.DoesNotContain("BuiltInsByCategoryId", resolver);
            Assert.DoesNotContain("SafeCategoryParent", resolver);
            Assert.DoesNotContain(".Where(entry => string.IsNullOrEmpty(normalizedInput)", resolver);
            Assert.DoesNotContain("knowledge", resolver, StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void RevitCategoryResolver_TreatsInvalidBuiltInAsUnavailable()
        {
            var resolver = Read("src/RookBim/Revit/RevitCategoryResolver.cs");
            var safeBuiltIn = ExtractMethod(resolver, "private static string? SafeBuiltInCategory(");

            Assert.Contains("builtIn == BuiltInCategory.INVALID", safeBuiltIn);
            Assert.Contains("return null;", safeBuiltIn);
        }

        [Fact]
        public void RevitCategoryResolver_CatchesRevitInvalidOperationDuringExplicitBuiltInLookup()
        {
            var resolver = Read("src/RookBim/Revit/RevitCategoryResolver.cs");
            var tryGetBuiltIn = ExtractMethod(resolver, "private static bool TryGetBuiltInCategory(");

            Assert.Contains("catch (Autodesk.Revit.Exceptions.InvalidOperationException)", tryGetBuiltIn);
        }

        [Fact]
        public void RevitRuntime_WiresListCategoriesThroughDispatcher()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var listCategories = ExtractMethod(runtime, "public BimApiResponse ListCategories(");

            Assert.Contains("private readonly RevitCategoryResolver categories;", runtime);
            Assert.Contains("this.categories = new RevitCategoryResolver();", runtime);
            Assert.Contains("return ExecuteInDocumentContext", listCategories);
            Assert.Contains("RevitContext.ActiveUiDocument(uiapp)", runtime);
            Assert.Contains("BimErrorCode.NoActiveDocument", runtime);
            Assert.Contains("categories.List(document)", runtime);
            Assert.DoesNotContain("BimErrorCode.NotRhinoInside", listCategories);
            Assert.Contains("BimErrorCode.InternalError", runtime);
        }

        [Fact]
        public void RevitQueryService_UsesCategoryResolverAndReturnsResolutionEvidence()
        {
            var service = Read("src/RookBim/Revit/RevitQueryService.cs");
            var query = ExtractMethod(service, "public BimApiResponse Query(");

            Assert.Contains("private readonly RevitCategoryResolver categories", service);
            Assert.Contains("categories.Resolve(document, categoryName)", query);
            Assert.Contains("BimErrorCode.AmbiguousCategory", query);
            Assert.Contains("BimErrorCode.CategoryNotQueryable", query);
            Assert.Contains("Data = new { resolution = resolution }", service);
            Assert.Contains("CategoryResolution = categoryResolution", service);
            Assert.Contains("TryResolvedCategoryFilter", service);
            Assert.Contains("new ElementCategoryFilter(new ElementId((long)id.Value))", service);
            Assert.Contains("collector.WherePasses(categoryFilter);", query);
            Assert.DoesNotContain("ResolveBuiltInCategory", service);
        }

        [Fact]
        public void RevitTask9_RuntimeWiresElementInfoAndParametersThroughDispatcher()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var elementInfo = ExtractMethod(runtime, "public BimApiResponse ElementInfo(");
            var elementParameters = ExtractMethod(runtime, "public BimApiResponse ElementParameters(");

            Assert.Contains("return Dispatch(diagnostics, uiapp =>", elementInfo);
            Assert.Contains("return Dispatch(diagnostics, uiapp =>", elementParameters);
            Assert.Contains("AcquireActiveUiDocument(uiapp, diagnostics)", elementInfo);
            Assert.Contains("AcquireActiveUiDocument(uiapp, diagnostics)", elementParameters);
            Assert.Contains("ResolveElementOrFailure(document, request?.Identity)", elementInfo);
            Assert.Contains("ResolveElementOrFailure(document, request?.Identity)", elementParameters);
            Assert.Contains("BuildElementInfo(document, resolved.Element!)", elementInfo);
            Assert.Contains("RevitParameterSerializer.Serialize(resolved.Element!)", elementParameters);
            Assert.DoesNotContain("LaterToolUnavailable", elementInfo);
            Assert.DoesNotContain("LaterToolUnavailable", elementParameters);
        }

        [Fact]
        public void RevitTask9_ElementResolverPreservesIdentityEnvelopeBoundaries()
        {
            var serializer = Read("src/RookBim/Revit/RevitIdentitySerializer.cs");

            Assert.Contains("public static BimElementResolveResult Resolve(Document document, BimElementIdentity? identity)", serializer);
            Assert.Contains("HasLinkedEvidence(identity)", serializer);
            Assert.Contains("identity.LinkInstanceId.HasValue", serializer);
            Assert.Contains("identity.LinkedElementUniqueId", serializer);
            Assert.Contains("BimErrorCode.LinkedElementUnsupported", serializer);
            Assert.Contains("DocumentMatches(DocumentIdentity(document), identity)", serializer);
            Assert.Contains("BimErrorCode.DocumentMismatch", serializer);
            Assert.Contains("document.GetElement(identity.UniqueId)", serializer);
            Assert.Contains("if (identity.ElementId.HasValue && !ElementIdMatches(byUniqueId.Id, identity.ElementId.Value))", serializer);
            Assert.Contains("Only use elementId fallback when uniqueId is absent.", serializer);
            Assert.Contains("document.GetElement(new ElementId((long)identity.ElementId.Value))", serializer);
            Assert.Contains("BimErrorCode.ElementNotFound", serializer);
        }

        [Fact]
        public void RevitTask9_ParameterSerializerReturnsStorageAndValueEvidence()
        {
            var serializer = Read("src/RookBim/Revit/RevitParameterSerializer.cs");

            Assert.Contains("internal static class RevitParameterSerializer", serializer);
            Assert.Contains("public static IReadOnlyList<object> Serialize(Element element)", serializer);
            Assert.Contains("SerializeParameters(result, element, \"instance\")", serializer);
            Assert.Contains("SerializeParameters(result, type, \"type\")", serializer);
            Assert.Contains("source = source", serializer);
            Assert.Contains("ownerElementId = ToInt32OrNull(owner.Id)", serializer);
            Assert.Contains("ownerUniqueId = NullIfWhiteSpace(owner.UniqueId)", serializer);
            Assert.Contains("name = definition?.Name ?? string.Empty", serializer);
            Assert.Contains("storageType = parameter.StorageType.ToString()", serializer);
            Assert.Contains("displayValue = DisplayValue(parameter)", serializer);
            Assert.Contains("rawValue = RawValue(parameter)", serializer);
            Assert.Contains("isReadOnly = parameter.IsReadOnly", serializer);
            Assert.Contains("builtIn = TryBuiltInName(parameter)", serializer);
            Assert.Contains("guid = TryGuid(parameter)", serializer);
            Assert.Contains("canCompareNumeric = false", serializer);
            Assert.Contains("StorageType.String", serializer);
            Assert.Contains("StorageType.Integer", serializer);
            Assert.Contains("StorageType.Double", serializer);
            Assert.Contains("StorageType.ElementId", serializer);
            Assert.Contains("parameter.Definition as InternalDefinition", serializer);
        }

        [Fact]
        public void RevitTask8_RuntimeWiresOnlyQueryElementsThroughDispatcher()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var queryElements = ExtractMethod(runtime, "public BimApiResponse QueryElements(");

            Assert.Contains("private readonly RevitQueryService query;", runtime);
            Assert.Contains("this.query = new RevitQueryService();", runtime);
            Assert.Contains("return ExecuteInDocumentContext", queryElements);
            Assert.Contains("RevitContext.ActiveUiDocument(uiapp)", runtime);
            Assert.Contains("BimErrorCode.NoActiveDocument", runtime);
            Assert.Contains("query.Query(document, view, request)", runtime);
            Assert.DoesNotContain("LaterToolUnavailable", queryElements);
        }

        [Fact]
        public void RevitTask8_QueryServiceUsesBoundedCollectorsAndEffectiveFilters()
        {
            var service = Read("src/RookBim/Revit/RevitQueryService.cs");
            var query = ExtractMethod(service, "public BimApiResponse Query(");
            var validationIndex = query.IndexOf("var validation = request.Validate();", StringComparison.Ordinal);
            var collectorIndex = query.IndexOf("new FilteredElementCollector", StringComparison.Ordinal);

            Assert.True(validationIndex >= 0);
            Assert.True(collectorIndex > validationIndex);
            Assert.Contains("request.EffectiveScope == BimQueryScope.ActiveView && activeView == null", query);
            Assert.Contains("BimErrorCode.NoActiveView", query);
            Assert.Contains("new FilteredElementCollector(document, activeView!.Id)", query);
            Assert.Contains("catch (Autodesk.Revit.Exceptions.ArgumentException)", query);
            Assert.Contains("catch (ArgumentException)", query);
            Assert.Contains("new FilteredElementCollector(document)", query);
            Assert.Contains("collector.WhereElementIsNotElementType();", query);
            Assert.Contains("collector.WherePasses(categoryFilter);", query);
            Assert.Contains("var filters = request.EffectiveFilters;", query);
            Assert.DoesNotContain("request.Filters", service);
        }

        [Fact]
        public void RevitTask8_QueryServicePreflightsAmbiguousParametersAcrossCandidateSet()
        {
            var service = Read("src/RookBim/Revit/RevitQueryService.cs");
            var query = ExtractMethod(service, "public BimApiResponse Query(");
            var preflightIndex = query.IndexOf("PreflightFilterParameterAmbiguity(document, candidates, filters)", StringComparison.Ordinal);
            var filterIndex = query.IndexOf("MatchesAllFilters(element, document, filters, missingCounts)", StringComparison.Ordinal);

            Assert.True(preflightIndex >= 0);
            Assert.True(filterIndex > preflightIndex);
            Assert.Contains("private static BimApiResponse? PreflightFilterParameterAmbiguity(", service);
            Assert.Contains("ICollection<Element> candidates", service);
            Assert.Contains("foreach (var element in candidates)", service);
            Assert.Contains("GetElementAndTypeParameters(document, element)", service);
            Assert.Contains("parameter.Definition as InternalDefinition", service);
            Assert.Contains("BimErrorCode.AmbiguousParameter", service);
            Assert.Contains("error = \"ambiguous_parameter\"", service);
            Assert.Contains("candidates = identities.Values.ToList()", service);
        }

        [Fact]
        public void RevitTask8_QueryServiceCapsUnfilteredCollectionBeforeFullMaterialization()
        {
            var service = Read("src/RookBim/Revit/RevitQueryService.cs");
            var query = ExtractMethod(service, "public BimApiResponse Query(");

            Assert.Contains("if (filters.Count == 0)", query);
            Assert.Contains("CollectUnfilteredResults(collector, request.EffectiveLimit)", query);
            Assert.Contains("return BimApiResponse.Ok(BuildResult(", query);
            Assert.Contains("limit + 1", service);
            Assert.Contains("break;", ExtractMethod(service, "private static CappedElementCollection CollectUnfilteredResults("));
        }

        [Fact]
        public void RevitTask8_QueryServiceReturnsApprovedSummaryShape()
        {
            var service = Read("src/RookBim/Revit/RevitQueryService.cs");

            Assert.Contains("new BimQueryElementsResult", service);
            Assert.Contains("Document = RevitIdentitySerializer.DocumentIdentity(document)", service);
            Assert.Contains("Scope = request.EffectiveScope", service);
            Assert.Contains("View = request.EffectiveScope == BimQueryScope.ActiveView", service);
            Assert.Contains("Query = new BimQuerySummary", service);
            Assert.Contains("MissingParameterCounts = missingCounts", service);
            Assert.Contains("new BimElementSummary", service);
            Assert.Contains("Identity = RevitIdentitySerializer.ElementIdentity(element)", service);
            Assert.Contains("new BimCategorySummary", service);
            Assert.Contains("new BimElementTypeSummary", service);
        }

        [Fact]
        public void RevitTask8_QueryServiceAcceptsDisplayNamePluralCategories()
        {
            var service = Read("src/RookBim/Revit/RevitQueryService.cs");

            Assert.Contains("categories.Resolve(document, categoryName)", service);
            Assert.DoesNotContain("NormalizeCategoryCandidate", service);
            Assert.DoesNotContain("TrimTrailingPluralS", service);
            Assert.DoesNotContain("ResolveBuiltInCategory", service);
        }

        [Fact]
        public void RevitTask10_DoesNotStartWritesGraphicsOrTemporaryViewIsolation()
        {
            var revitDirectory = Path.Combine(RepoRoot, "src", "RookBim", "Revit");
            var revitFiles = Directory.GetFiles(revitDirectory, "*.cs");
            var combined = string.Join(Environment.NewLine, revitFiles.Select(File.ReadAllText));

            Assert.DoesNotContain("ParameterFilterElement", combined);
            Assert.DoesNotContain("OverrideGraphicSettings", combined);
            Assert.DoesNotContain("TemporaryView", combined);
            Assert.DoesNotContain("Transaction", combined);
        }

        [Fact]
        public void RookBimProject_CopiesBuiltModuleToExistingRookRuntimeDirectoryOnly()
        {
            var text = Read("src/RookBim/RookBim.csproj");

            Assert.Contains("CopyRookBimToRookRuntime", text);
            Assert.Contains("AfterTargets=\"Build\"", text);
            Assert.Contains("../Rook/bin/$(Configuration)/$(TargetFramework)", NormalizeProjectPath(text));
            Assert.Contains("Exists('$(RookRuntimeDir)')", text);
            Assert.Contains("$(TargetPath)", text);
            Assert.Contains("$(TargetDir)$(TargetName).pdb", text);
        }

        [Fact]
        public void RookProject_OptionallyIncludesAlreadyBuiltRookBimArtifacts()
        {
            var text = Read("src/Rook/Rook.csproj");

            Assert.Contains("../RookBim/bin/$(Configuration)/$(TargetFramework)/RookBim.dll", NormalizeProjectPath(text));
            Assert.Contains("../RookBim/bin/$(Configuration)/$(TargetFramework)/RookBim.pdb", NormalizeProjectPath(text));
            Assert.Contains("Exists('../RookBim/bin/$(Configuration)/$(TargetFramework)/RookBim.dll')", NormalizeProjectPath(text));
            Assert.Contains("Exists('../RookBim/bin/$(Configuration)/$(TargetFramework)/RookBim.pdb')", NormalizeProjectPath(text));
            Assert.Contains("<Link>RookBim.dll</Link>", text);
            Assert.Contains("<Link>RookBim.pdb</Link>", text);
            Assert.Contains("<CopyToOutputDirectory>PreserveNewest</CopyToOutputDirectory>", text);
        }

        private static void AssertRevitReference(XDocument project, string include)
        {
            var reference = project
                .Descendants("Reference")
                .Single(element => string.Equals(AttributeValue(element, "Include"), include, StringComparison.OrdinalIgnoreCase));

            Assert.Contains("$(RevitInstallDir)", ValueOf(reference, "HintPath"));
            Assert.Equal("false", ValueOf(reference, "Private"));
        }

        private static XDocument LoadProject(string relativePath)
        {
            return XDocument.Load(Path.Combine(RepoRoot, relativePath.Replace('/', Path.DirectorySeparatorChar)));
        }

        private static string Read(string relativePath)
        {
            return File.ReadAllText(Path.Combine(RepoRoot, relativePath.Replace('/', Path.DirectorySeparatorChar)));
        }

        private static string ValueOf(XContainer container, string elementName)
        {
            return container.Descendants(elementName).Select(element => element.Value).FirstOrDefault() ?? string.Empty;
        }

        private static string AttributeValue(XElement element, string attributeName)
        {
            return element.Attribute(attributeName)?.Value ?? string.Empty;
        }

        private static string NormalizeProjectPath(string value)
        {
            return value.Replace('\\', '/');
        }

        private static string NormalizeLineEndings(string value)
        {
            return value.Replace("\r\n", "\n");
        }

        private static int CountOccurrences(string source, string value)
        {
            var count = 0;
            var index = 0;
            while ((index = source.IndexOf(value, index, StringComparison.Ordinal)) >= 0)
            {
                count++;
                index += value.Length;
            }

            return count;
        }

        private static void AssertAcquisitionCounts(
            string source,
            int expectedUiDocument,
            int expectedDocument)
        {
            Assert.Equal(
                expectedUiDocument,
                CountOccurrences(source, "AcquireActiveUiDocument(uiapp, diagnostics)"));
            Assert.Equal(
                expectedDocument,
                CountOccurrences(source, "AcquireDocument(uidoc, diagnostics)"));
        }

        private static void AssertDisabledProductionFastPath(
            string source,
            string enabledExpression,
            string directExpression)
        {
            Assert.Contains("return diagnostics.Enabled", source);
            Assert.Contains("BimDiagnosticProbe.Production(", source);
            Assert.Contains(enabledExpression, source);
            Assert.Contains(": " + directExpression + ";", source);
            Assert.Equal(2, CountOccurrences(source, directExpression));
            Assert.Equal(1, CountOccurrences(source, enabledExpression));
        }

        private static string ExtractExecutableMember(
            string source,
            string typeDeclaration,
            string memberDeclaration)
        {
            var code = Lex(source).CodeMask;
            var type = FindUniqueBlockDeclaration(
                code,
                typeDeclaration,
                0,
                code.Length,
                containingBodyStart: null);
            var member = FindUniqueBlockDeclaration(
                code,
                memberDeclaration,
                type.BodyStart + 1,
                type.BodyEnd,
                type.BodyStart);

            return code.Substring(
                member.DeclarationStart,
                member.BodyEnd - member.DeclarationStart + 1);
        }

        private static SourceBlock FindUniqueBlockDeclaration(
            string code,
            string declaration,
            int searchStart,
            int searchEnd,
            int? containingBodyStart)
        {
            var significantDeclaration = new string(declaration
                .Where(character => !char.IsWhiteSpace(character))
                .ToArray());
            if (significantDeclaration.Length == 0)
            {
                throw new ArgumentException(
                    "Declaration must contain a non-whitespace character.",
                    nameof(declaration));
            }

            var matches = new List<SourceBlock>();
            for (var candidate = searchStart; candidate < searchEnd; candidate++)
            {
                if (char.IsWhiteSpace(code[candidate]) ||
                    code[candidate] != significantDeclaration[0] ||
                    HasIdentifierPrefix(code, candidate, significantDeclaration[0]))
                {
                    continue;
                }

                if (!TryMatchIgnoringWhitespace(
                        code,
                        candidate,
                        searchEnd,
                        significantDeclaration,
                        out var declarationEnd))
                {
                    continue;
                }

                var bodyStart = NextNonWhitespace(code, declarationEnd, searchEnd);
                if (bodyStart < 0 || code[bodyStart] != '{')
                {
                    continue;
                }

                if (containingBodyStart.HasValue &&
                    BraceDepth(
                        code,
                        containingBodyStart.Value + 1,
                        candidate) != 0)
                {
                    continue;
                }

                var bodyEnd = FindClosingBrace(code, bodyStart, searchEnd);
                matches.Add(new SourceBlock(candidate, bodyStart, bodyEnd));
            }

            if (matches.Count != 1)
            {
                throw new InvalidOperationException(
                    "Expected exactly one declaration for '" + declaration +
                    "' but found " + matches.Count + ".");
            }

            return matches[0];
        }

        private static bool TryMatchIgnoringWhitespace(
            string source,
            int candidate,
            int searchEnd,
            string significantPattern,
            out int matchEnd)
        {
            var sourceIndex = candidate;
            var patternIndex = 0;
            while (sourceIndex < searchEnd &&
                   patternIndex < significantPattern.Length)
            {
                if (char.IsWhiteSpace(source[sourceIndex]))
                {
                    sourceIndex++;
                    continue;
                }

                if (source[sourceIndex] != significantPattern[patternIndex])
                {
                    matchEnd = -1;
                    return false;
                }

                sourceIndex++;
                patternIndex++;
            }

            matchEnd = sourceIndex;
            return patternIndex == significantPattern.Length;
        }

        private static bool HasIdentifierPrefix(
            string source,
            int candidate,
            char patternStart)
        {
            if (!IsIdentifierCharacter(patternStart))
            {
                return false;
            }

            for (var index = candidate - 1; index >= 0; index--)
            {
                if (char.IsWhiteSpace(source[index]))
                {
                    continue;
                }

                return IsIdentifierCharacter(source[index]);
            }

            return false;
        }

        private static bool IsIdentifierCharacter(char value)
        {
            return char.IsLetterOrDigit(value) || value == '_';
        }

        private static int NextNonWhitespace(
            string source,
            int start,
            int searchEnd)
        {
            for (var index = start; index < searchEnd; index++)
            {
                if (!char.IsWhiteSpace(source[index]))
                {
                    return index;
                }
            }

            return -1;
        }

        private static int BraceDepth(
            string source,
            int start,
            int end)
        {
            var depth = 0;
            for (var index = start; index < end; index++)
            {
                if (source[index] == '{')
                {
                    depth++;
                }
                else if (source[index] == '}')
                {
                    depth--;
                }
            }

            return depth;
        }

        private static int FindClosingBrace(
            string source,
            int bodyStart,
            int searchEnd)
        {
            var depth = 0;
            for (var index = bodyStart; index < searchEnd; index++)
            {
                if (source[index] == '{')
                {
                    depth++;
                }
                else if (source[index] == '}')
                {
                    depth--;
                    if (depth == 0)
                    {
                        return index;
                    }
                }
            }

            throw new InvalidOperationException(
                "Brace did not close at index " + bodyStart + ".");
        }

        private static string ExtractMethod(string source, string declaration)
        {
            var lexed = Lex(source);
            var declarationStart = FindIgnoringWhitespace(
                lexed.CodeMask, declaration);
            if (declarationStart < 0)
            {
                throw new InvalidOperationException(
                    "Method not found: " + declaration);
            }

            var bodyStart = lexed.CodeMask.IndexOf(
                '{', declarationStart);
            if (bodyStart < 0)
            {
                throw new InvalidOperationException(
                    "Method body not found: " + declaration);
            }

            var declarationTerminator = lexed.CodeMask.IndexOf(
                ';', declarationStart, bodyStart - declarationStart);
            if (declarationTerminator >= 0)
            {
                throw new InvalidOperationException(
                    "Declaration has no block body: " + declaration);
            }

            var depth = 0;
            for (var index = bodyStart; index < lexed.CodeMask.Length; index++)
            {
                if (lexed.CodeMask[index] == '{')
                {
                    depth++;
                }
                else if (lexed.CodeMask[index] == '}')
                {
                    depth--;
                    if (depth == 0)
                    {
                        return lexed.WithoutComments.Substring(
                            declarationStart,
                            index - declarationStart + 1);
                    }
                }
            }

            throw new InvalidOperationException(
                "Brace did not close at index " + bodyStart);
        }

        private static string FirstExecutableStatement(string method)
        {
            var lexed = Lex(method);
            var bodyStart = lexed.CodeMask.IndexOf('{');
            if (bodyStart < 0)
            {
                throw new InvalidOperationException("Method body not found.");
            }

            var statementStart = bodyStart + 1;
            while (statementStart < lexed.CodeMask.Length &&
                   char.IsWhiteSpace(lexed.CodeMask[statementStart]))
            {
                statementStart++;
            }

            var parentheses = 0;
            var brackets = 0;
            var braces = 0;
            for (var index = statementStart; index < lexed.CodeMask.Length; index++)
            {
                switch (lexed.CodeMask[index])
                {
                    case '(':
                        parentheses++;
                        break;
                    case ')':
                        parentheses--;
                        break;
                    case '[':
                        brackets++;
                        break;
                    case ']':
                        brackets--;
                        break;
                    case '{':
                        braces++;
                        break;
                    case '}':
                        if (braces == 0)
                        {
                            throw new InvalidOperationException(
                                "Method has no executable statement.");
                        }

                        braces--;
                        break;
                    case ';':
                        if (parentheses == 0 && brackets == 0 && braces == 0)
                        {
                            return lexed.WithoutComments.Substring(
                                statementStart,
                                index - statementStart + 1).Trim();
                        }

                        break;
                }
            }

            throw new InvalidOperationException(
                "First executable statement did not terminate.");
        }

        private static string RemoveWhitespace(string value)
        {
            return new string(value
                .Where(character => !char.IsWhiteSpace(character))
                .ToArray());
        }

        private static string ExecutableCode(string source)
        {
            return Lex(source).CodeMask;
        }

        private static int FindIgnoringWhitespace(
            string source,
            string pattern)
        {
            var significantPattern = new string(pattern
                .Where(character => !char.IsWhiteSpace(character))
                .ToArray());
            if (significantPattern.Length == 0)
            {
                throw new ArgumentException(
                    "Declaration must contain a non-whitespace character.",
                    nameof(pattern));
            }

            for (var candidate = 0; candidate < source.Length; candidate++)
            {
                if (char.IsWhiteSpace(source[candidate]) ||
                    source[candidate] != significantPattern[0])
                {
                    continue;
                }

                var sourceIndex = candidate;
                var patternIndex = 0;
                while (sourceIndex < source.Length &&
                       patternIndex < significantPattern.Length)
                {
                    if (char.IsWhiteSpace(source[sourceIndex]))
                    {
                        sourceIndex++;
                        continue;
                    }

                    if (source[sourceIndex] != significantPattern[patternIndex])
                    {
                        break;
                    }

                    sourceIndex++;
                    patternIndex++;
                }

                if (patternIndex == significantPattern.Length)
                {
                    return candidate;
                }
            }

            return -1;
        }

        private static LexedSource Lex(string source)
        {
            if (source == null)
            {
                throw new ArgumentNullException(nameof(source));
            }

            var withoutComments = source.ToCharArray();
            var codeMask = source.ToCharArray();
            var index = 0;
            while (index < source.Length)
            {
                if (source[index] == '/' && index + 1 < source.Length &&
                    source[index + 1] == '/')
                {
                    Blank(withoutComments, index);
                    Blank(withoutComments, index + 1);
                    Blank(codeMask, index);
                    Blank(codeMask, index + 1);
                    index += 2;
                    while (index < source.Length &&
                           source[index] != '\r' &&
                           source[index] != '\n')
                    {
                        Blank(withoutComments, index);
                        Blank(codeMask, index);
                        index++;
                    }

                    continue;
                }

                if (source[index] == '/' && index + 1 < source.Length &&
                    source[index + 1] == '*')
                {
                    Blank(withoutComments, index);
                    Blank(withoutComments, index + 1);
                    Blank(codeMask, index);
                    Blank(codeMask, index + 1);
                    index += 2;
                    while (index < source.Length)
                    {
                        if (source[index] == '*' && index + 1 < source.Length &&
                            source[index + 1] == '/')
                        {
                            Blank(withoutComments, index);
                            Blank(withoutComments, index + 1);
                            Blank(codeMask, index);
                            Blank(codeMask, index + 1);
                            index += 2;
                            break;
                        }

                        Blank(withoutComments, index);
                        Blank(codeMask, index);
                        index++;
                    }

                    continue;
                }

                if (source[index] == '"')
                {
                    var quoteCount = CountRun(source, index, '"');
                    if (quoteCount >= 3)
                    {
                        index = MaskRawString(codeMask, source, index, quoteCount);
                    }
                    else
                    {
                        index = IsVerbatimString(source, index)
                            ? MaskVerbatimString(codeMask, source, index)
                            : MaskEscapedLiteral(codeMask, source, index, '"');
                    }

                    continue;
                }

                if (source[index] == '\'')
                {
                    index = MaskEscapedLiteral(codeMask, source, index, '\'');
                    continue;
                }

                index++;
            }

            return new LexedSource(
                new string(withoutComments),
                new string(codeMask));
        }

        private static int MaskEscapedLiteral(
            char[] codeMask,
            string source,
            int start,
            char terminator)
        {
            var index = start;
            Blank(codeMask, index++);
            while (index < source.Length)
            {
                var current = source[index];
                Blank(codeMask, index++);
                if (current == '\\' && index < source.Length)
                {
                    Blank(codeMask, index++);
                }
                else if (current == terminator)
                {
                    break;
                }
            }

            return index;
        }

        private static int MaskVerbatimString(
            char[] codeMask,
            string source,
            int start)
        {
            var index = start;
            Blank(codeMask, index++);
            while (index < source.Length)
            {
                if (source[index] == '"')
                {
                    Blank(codeMask, index++);
                    if (index < source.Length && source[index] == '"')
                    {
                        Blank(codeMask, index++);
                        continue;
                    }

                    break;
                }

                Blank(codeMask, index++);
            }

            return index;
        }

        private static int MaskRawString(
            char[] codeMask,
            string source,
            int start,
            int delimiterLength)
        {
            var index = start;
            for (var offset = 0; offset < delimiterLength; offset++)
            {
                Blank(codeMask, index++);
            }

            while (index < source.Length)
            {
                if (source[index] == '"' &&
                    CountRun(source, index, '"') >= delimiterLength)
                {
                    for (var offset = 0; offset < delimiterLength; offset++)
                    {
                        Blank(codeMask, index++);
                    }

                    break;
                }

                Blank(codeMask, index++);
            }

            return index;
        }

        private static bool IsVerbatimString(string source, int quoteIndex)
        {
            return quoteIndex > 0 && source[quoteIndex - 1] == '@' ||
                quoteIndex > 1 &&
                source[quoteIndex - 2] == '@' &&
                source[quoteIndex - 1] == '$';
        }

        private static int CountRun(
            string source,
            int start,
            char value)
        {
            var index = start;
            while (index < source.Length && source[index] == value)
            {
                index++;
            }

            return index - start;
        }

        private static void Blank(char[] value, int index)
        {
            if (value[index] != '\r' && value[index] != '\n')
            {
                value[index] = ' ';
            }
        }

        private sealed class LexedSource
        {
            public LexedSource(string withoutComments, string codeMask)
            {
                WithoutComments = withoutComments;
                CodeMask = codeMask;
            }

            public string WithoutComments { get; }

            public string CodeMask { get; }
        }

        private sealed class SourceBlock
        {
            public SourceBlock(
                int declarationStart,
                int bodyStart,
                int bodyEnd)
            {
                DeclarationStart = declarationStart;
                BodyStart = bodyStart;
                BodyEnd = bodyEnd;
            }

            public int DeclarationStart { get; }

            public int BodyStart { get; }

            public int BodyEnd { get; }
        }

        private static string FindRepoRoot()
        {
            var directory = new DirectoryInfo(AppContext.BaseDirectory);
            while (directory != null)
            {
                if (File.Exists(Path.Combine(directory.FullName, "Rook.sln")))
                {
                    return directory.FullName;
                }

                directory = directory.Parent;
            }

            throw new InvalidOperationException("Could not find repository root.");
        }
    }
}
