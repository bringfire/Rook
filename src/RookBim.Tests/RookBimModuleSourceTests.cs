using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
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
        private const string CategoryResolverType =
            "internal sealed class RevitCategoryResolver";
        private const string QueryServiceType =
            "internal sealed class RevitQueryService";
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
        public void SourceContracts_HaveNoLegacyPrefixExtractor()
        {
            var source = Read(
                "src/RookBim.Tests/RookBimModuleSourceTests.cs");

            AssertNoLegacySourceMatchingIdentifiers(source);
        }

        [Fact]
        public void SourceIdentifierAudit_RejectsWhitespaceSeparatedLegacyDeclarationsAndReferences()
        {
            var declaration = @"
internal sealed class Fixture
{
    private static string ExtractMethod
    /* layout */
    (
        string source)
    {
        return source;
    }
}";
            var reference = @"
internal sealed class Fixture
{

    public void Target()
    {
        var reference = FindIgnoringWhitespace;
    }
}";

            Assert.ThrowsAny<Exception>(() =>
                AssertNoLegacySourceMatchingIdentifiers(declaration));
            Assert.ThrowsAny<Exception>(() =>
                AssertNoLegacySourceMatchingIdentifiers(reference));
        }

        [Fact]
        public void SourceIdentifierAudit_IgnoresLegacyNamesInCommentsAndLiterals()
        {
            var source = @"
internal sealed class Fixture
{
    // ExtractMethod (source)
    /* FindIgnoringWhitespace */
    public void Target()
    {
        var call = ""ExtractMethod (source)"";
        var reference = @""FindIgnoringWhitespace"";
        var longerNames = ExtractMethodology + FindIgnoringWhitespaceSuffix;
    }
}";

            AssertNoLegacySourceMatchingIdentifiers(source);
        }

        [Theory]
        [InlineData("var value = $\"{ExtractMethod (source)}\";")]
        [InlineData("var value = $@\"{FindIgnoringWhitespace}\";")]
        [InlineData("var value = @$\"{FindIgnoringWhitespace}\";")]
        [InlineData("var value = $\"\"\"{ExtractMethod(source)}\"\"\";")]
        [InlineData("var value = $$\"\"\"{{FindIgnoringWhitespace}}\"\"\";")]
        public void SourceIdentifierAudit_RejectsLegacyNamesInInterpolatedExpressions(
            string source)
        {
            Assert.ThrowsAny<Exception>(() =>
                AssertNoLegacySourceMatchingIdentifiers(source));
        }

        [Fact]
        public void SourceIdentifierAudit_IgnoresLegacyNamesInInterpolatedLiteralText()
        {
            var source =
                "var ordinary = $\"ExtractMethod {actual}\";\n" +
                "var verbatim = $@\"FindIgnoringWhitespace {actual}\";\n" +
                "var raw = $\"\"\"ExtractMethod FindIgnoringWhitespace {actual}\"\"\";";

            AssertNoLegacySourceMatchingIdentifiers(source);
        }

        [Fact]
        public void SourceContractAudit_DistinguishesWholeSourcePositivesFromNegativesAndLiterals()
        {
            var source = @"
Assert.Contains(
    ""required"",
    runtime);
Assert.DoesNotContain(""forbidden"", runtime);
var decoy = ""Assert.Contains(\""required\"", runtime);"";
Assert.Contains(""required"", member);";

            Assert.ThrowsAny<Exception>(() =>
                AssertNoWholeSourcePositiveContains(source, "runtime"));
            AssertNoWholeSourcePositiveContains(source, "dispatcher");

            var moduleSource = "Assert.Contains(\"required\", module);";
            Assert.ThrowsAny<Exception>(() =>
                AssertNoWholeSourcePositiveContains(moduleSource, "module"));
        }

        [Theory]
        [InlineData("Assert.Contains(\"required\", (runtime));")]
        [InlineData("Assert.Contains(\"required\", NormalizeLineEndings(runtime));")]
        public void SourceContractAudit_RejectsWrappedWholeSourceActualArguments(
            string source)
        {
            Assert.ThrowsAny<Exception>(() =>
                AssertNoWholeSourcePositiveContains(source, "runtime"));
        }

        [Theory]
        [InlineData(
            "var alias = runtime;\n" +
            "Assert.Contains(\"required\", alias);")]
        [InlineData(
            "var first = (runtime);\n" +
            "var alias = first;\n" +
            "Assert.Contains(\"required\", NormalizeLineEndings((alias)));")]
        [InlineData(
            "var alias = (NormalizeLineEndings(runtime));\n" +
            "Assert.Contains(\"required\", alias);")]
        public void SourceContractAudit_RejectsDirectWholeSourceAliasChains(
            string source)
        {
            Assert.ThrowsAny<Exception>(() =>
                AssertNoWholeSourcePositiveContains(source, "runtime"));
        }

        [Theory]
        [InlineData(
            "var sourceText = Read(\"src/RookBim/Revit/RevitRookBimRuntime.cs\");\n" +
            "Assert.Contains(\"required\", sourceText);")]
        [InlineData(
            "var sourceText = Read(\"src/RookBim/Revit/RevitRookBimRuntime.cs\");\n" +
            "var alias = (sourceText);\n" +
            "Assert.Contains(\"required\", NormalizeLineEndings((alias)));")]
        [InlineData(
            "var sourceText = (Read(\"src/RookBim/Revit/RevitRookBimRuntime.cs\"));\n" +
            "Assert.Contains(\"required\", sourceText);")]
        public void SourceContractAudit_RejectsRenamedProductionSourceReads(
            string source)
        {
            Assert.ThrowsAny<Exception>(() =>
                AssertNoWholeSourcePositiveContains(source));
        }

        [Fact]
        public void SourceContractAudit_IgnoresAliasAndReadOriginsInCommentsAndLiterals()
        {
            var source =
                "var literal = \"var sourceText = Read(" +
                "\\\"src/RookBim/Revit/RevitRookBimRuntime.cs\\\");\";\n" +
                "// var alias = runtime;\n" +
                "var interpolation = $\"var alias = runtime; {member}\";\n" +
                "Assert.Contains(\"required\", member);";

            AssertNoWholeSourcePositiveContains(source, "runtime");
        }

        [Fact]
        public void SourceContracts_Task8PositivesBindExactMembers()
        {
            var source = Read(
                "src/RookBim.Tests/RookBimModuleSourceTests.cs");

            AssertNoWholeSourcePositiveContains(
                ExtractSourceMember(
                    source,
                    "public class RookBimModuleSourceTests",
                    "public void RookBimModuleActivate_InstallsRevitRuntimeFromOptionalAssembly()"),
                "module");
            AssertNoWholeSourcePositiveContains(
                ExtractSourceMember(
                    source,
                    "public class RookBimModuleSourceTests",
                    "public void RevitTask7_UsesRhinoInsideHostContextDispatcherWithoutTransactions()"),
                "dispatcher");
            AssertNoWholeSourcePositiveContains(
                ExtractSourceMember(
                    source,
                    "public class RookBimModuleSourceTests",
                    "public void RevitTask7_RuntimeUsesDispatcherForStatusAndActiveDocument()"),
                "runtime",
                "context",
                "serializer");
            AssertNoWholeSourcePositiveContains(
                ExtractSourceMember(
                    source,
                    "public class RookBimModuleSourceTests",
                    "public void RevitTask7_ElementIdSerializationUsesBoundedNullableConversion()"),
                "serializer");
            AssertNoWholeSourcePositiveContains(
                ExtractSourceMember(
                    source,
                    "public class RookBimModuleSourceTests",
                    "public void RevitTask7_DispatchDoesNotMaskFaultedTasksWithAggregateException()"),
                "runtime");
            AssertNoWholeSourcePositiveContains(
                ExtractSourceMember(
                    source,
                    "public class RookBimModuleSourceTests",
                    "public void RevitTask7_StatusDispatchFailureKeepsRookBimRuntime()"),
                "runtime");
        }

        [Fact]
        public void SourceContracts_ActiveDocumentResultDoesNotSearchWholeRuntime()
        {
            var source = Read(
                "src/RookBim.Tests/RookBimModuleSourceTests.cs");
            var contract = ExtractExecutableMember(
                source,
                "public class RookBimModuleSourceTests",
                "public void RevitTask7_ActiveDocumentResultUsesViewPropertyForCamelCaseContract()");

            Assert.DoesNotContain(", runtime);", contract);
        }

        [Fact]
        public void SourceContracts_DispatchTimeoutDoesNotSearchWholeSourceFiles()
        {
            var source = Read(
                "src/RookBim.Tests/RookBimModuleSourceTests.cs");
            var contract = ExtractExecutableMember(
                source,
                "public class RookBimModuleSourceTests",
                "public void RevitTask7_DispatchTimeoutAbandonsPendingWork()");

            Assert.DoesNotContain(", dispatcher);", contract);
            Assert.DoesNotContain(", runtime);", contract);
        }

        [Fact]
        public void SourceContracts_SelectionWiringDoesNotUsePrefixExtraction()
        {
            var source = Read(
                "src/RookBim.Tests/RookBimModuleSourceTests.cs");
            var contract = ExtractExecutableMember(
                source,
                "public class RookBimModuleSourceTests",
                "public void RevitTask10_RuntimeWiresSelectionThroughDispatcher()");

            Assert.DoesNotContain("ExtractMethod(", contract);
        }

        [Fact]
        public void SourceContracts_ElementWiringDoesNotUsePrefixExtraction()
        {
            var source = Read(
                "src/RookBim.Tests/RookBimModuleSourceTests.cs");
            var contract = ExtractExecutableMember(
                source,
                "public class RookBimModuleSourceTests",
                "public void RevitTask9_RuntimeWiresElementInfoAndParametersThroughDispatcher()");

            Assert.DoesNotContain("ExtractMethod(", contract);
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
            var module = Read("src/RookBim/RookBimModule.cs");
            var activate = ExtractExecutableMember(
                module,
                ModuleType,
                "public static void Activate()");
            var activateSource = ExtractSourceMember(
                module,
                ModuleType,
                "public static void Activate()");

            Assert.Equal(2, CountOccurrences(activate, "IsLoaded("));
            Assert.Contains("IsLoaded(\"RevitAPIUI\")", activateSource);
            Assert.Contains("IsLoaded(\"RhinoInside.Revit\")", activateSource);
            Assert.Contains("new RookBimUnavailableRuntime", activate);
            Assert.Contains("\"not_rhino_inside\"", activateSource);
            Assert.Contains("RookBimRuntimeRegistry.Install", activate);
            Assert.Contains("new RevitRookBimRuntime()", activate);
            Assert.Contains("\"RookBim.dll\"", activateSource);
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
            var revitTypeName = ExtractSourceDirectMember(
                dispatcher,
                DispatcherType,
                "private const string RevitTypeName = \"RhinoInside.Revit.Revit\";");
            var invokeAbandonable = ExtractExecutableMember(
                dispatcher,
                DispatcherType,
                "internal RevitApiDispatch<T> InvokeAbandonable<T>(BimDiagnosticContext diagnostics, Func<UIApplication, T> work)");
            var enqueue = ExtractExecutableMember(
                dispatcher,
                DispatcherType,
                "private static void EnqueueIdlingAction(Action action)");
            var activeApplication = ExtractExecutableMember(
                dispatcher,
                DispatcherType,
                "private static UIApplication ActiveUIApplication()");
            var resolveType = ExtractExecutableMember(
                dispatcher,
                DispatcherType,
                "private static Type ResolveRhinoInsideType(string typeName)");
            var completion = ExtractExecutableDirectMember(
                dispatcher,
                WorkItemType,
                "private readonly TaskCompletionSource<T> completion = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);");
            var revitFiles = Directory
                .GetFiles(Path.Combine(RepoRoot, "src", "RookBim", "Revit"), "*.cs")
                .Select(File.ReadAllText);
            var combined = string.Join(Environment.NewLine, revitFiles);

            Assert.Equal(
                "private const string RevitTypeName = \"RhinoInside.Revit.Revit\";",
                revitTypeName.Trim());
            Assert.Contains("EnqueueIdlingAction(new Action(item.Execute))", invokeAbandonable);
            Assert.Contains("ResolveRhinoInsideType(RevitTypeName)", enqueue);
            Assert.Contains("ResolveRhinoInsideType(RevitTypeName)", activeApplication);
            Assert.Contains("Type.GetType", resolveType);
            Assert.Contains("AppDomain.CurrentDomain", resolveType);
            Assert.Contains("TargetInvocationException", enqueue);
            Assert.Contains("TargetInvocationException", activeApplication);
            Assert.Equal(
                RemoveWhitespace(
                    "private readonly TaskCompletionSource<T> completion = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);"),
                RemoveWhitespace(completion));
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
            var dispatcherField = ExtractExecutableDirectMember(
                runtime,
                RuntimeType,
                "private readonly RevitApiDispatcher dispatcher;");
            var dispatch = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private T Dispatch<T>(BimDiagnosticContext diagnostics, Func<UIApplication, T> work)");
            var status = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimStatusResponse Status(BimDiagnosticContext diagnostics)");
            var statusSource = ExtractSourceMember(
                runtime,
                RuntimeType,
                "public BimStatusResponse Status(BimDiagnosticContext diagnostics)");
            var documentContext = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private BimApiResponse ExecuteInDocumentContext(BimDiagnosticContext diagnostics, string operation, Func<UIDocument, Document, BimApiResponse> work)");
            var activeUiDocument = ExtractExecutableMember(
                context,
                "public static class RevitContext",
                "public static UIDocument? ActiveUiDocument(UIApplication uiapp)");
            var activeDocument = ExtractExecutableMember(
                context,
                "public static class RevitContext",
                "public static Document? ActiveDocument(UIApplication uiapp)");
            var legacyIdentity = ExtractExecutableMember(
                serializer,
                IdentitySerializerType,
                "public static BimDocumentIdentity DocumentIdentity(Document document)");

            Assert.Equal(
                RemoveWhitespace("private readonly RevitApiDispatcher dispatcher;"),
                RemoveWhitespace(dispatcherField));
            Assert.Contains("dispatcher.InvokeAbandonable", dispatch);
            Assert.Contains("ActiveUiDocument(uiapp)?.Document", activeDocument);
            Assert.Contains("uiapp?.ActiveUIDocument", activeUiDocument);
            Assert.Contains("GetWorksharingCentralGUID(document)", legacyIdentity);
            Assert.Contains("GuidSource", legacyIdentity);
            Assert.Contains("BimDocumentGuidSource.Unavailable", legacyIdentity);
            Assert.DoesNotContain("PathFallback", ExecutableCode(serializer));

            Assert.Contains("Available = true", status);
            Assert.Contains("Runtime = \"rookbim\"", statusSource);
            Assert.Contains("Host = \"revit\"", statusSource);
            Assert.Contains("Module = ModuleName", status);
            Assert.Contains("ErrorCode = \"no_active_document\"", statusSource);
            Assert.Contains("BimErrorCode.NoActiveDocument", documentContext);
            Assert.Contains("409", documentContext);
        }

        [Fact]
        public void RevitTask7_ActiveDocumentResultUsesViewPropertyForCamelCaseContract()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var activeDocument = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse ActiveDocument(BimDiagnosticContext diagnostics)");
            var viewProperty = ExtractExecutableDirectMember(
                runtime,
                "private sealed class ActiveDocumentResult",
                "public BimViewIdentity? View { get; set; }");

            Assert.Contains(
                "View = SerializeActiveView(uidoc, diagnostics)",
                activeDocument);
            Assert.Equal(
                RemoveWhitespace("public BimViewIdentity? View { get; set; }"),
                RemoveWhitespace(viewProperty));
            Assert.DoesNotContain(
                "ActiveView = SerializeActiveView(uidoc)",
                activeDocument);
            Assert.DoesNotContain(
                "public BimViewIdentity? ActiveView { get; set; }",
                ExecutableCode(runtime));
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
            var invalidElementId = ExtractExecutableDirectMember(
                serializer,
                IdentitySerializerType,
                "private const int InvalidElementIdValue = -1;");
            var viewIdentity = ExtractExecutableMember(
                serializer,
                IdentitySerializerType,
                "public static BimViewIdentity ViewIdentity(View view)");
            var elementIdentity = ExtractExecutableMember(
                serializer,
                IdentitySerializerType,
                "public static BimElementIdentity ElementIdentity(Element element)");
            var toInt32OrNull = ExtractExecutableMember(
                serializer,
                IdentitySerializerType,
                "private static int? ToInt32OrNull(ElementId? id)");

            Assert.Equal(
                RemoveWhitespace("private const int InvalidElementIdValue = -1;"),
                RemoveWhitespace(invalidElementId));
            Assert.Contains(
                "Id = ToInt32OrNull(view.Id) ?? InvalidElementIdValue",
                viewIdentity);
            Assert.Contains(
                "ElementId = ToInt32OrNull(element.Id)",
                elementIdentity);
            Assert.Contains(
                "if (value < int.MinValue || value > int.MaxValue)",
                toInt32OrNull);
            Assert.Contains("return null;", toInt32OrNull);
            Assert.DoesNotContain("Convert.ToInt32", ExecutableCode(serializer));
        }

        [Fact]
        public void RevitTask7_DispatchTimeoutAbandonsPendingWork()
        {
            var dispatcher = Read("src/RookBim/Revit/RevitApiDispatcher.cs");
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var invokeAbandonable = ExtractExecutableMember(
                dispatcher,
                DispatcherType,
                "internal RevitApiDispatch<T> InvokeAbandonable<T>(BimDiagnosticContext diagnostics, Func<UIApplication, T> work)");
            var abandon = ExtractExecutableMember(
                dispatcher,
                "internal sealed class RevitApiDispatch<T>",
                "public bool Abandon()");
            var execute = ExtractExecutableMember(
                dispatcher,
                WorkItemType,
                "public void Execute()");
            var tryAbandon = ExtractExecutableMember(
                dispatcher,
                WorkItemType,
                "public bool TryAbandon()");
            var dispatchWithTimeout = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private T DispatchWithTimeout<T>(BimDiagnosticContext diagnostics, Func<UIApplication, T> work, TimeSpan timeout)");

            Assert.Contains(
                "var dispatch = dispatcher.InvokeAbandonable(capturedDiagnostics, work);",
                dispatchWithTimeout);
            Assert.Contains("new RevitApiWorkItem<T>(diagnostics, work)", invokeAbandonable);
            Assert.Contains("item.TryAbandon", invokeAbandonable);
            Assert.Contains("return abandon();", abandon);
            Assert.Contains("CompareExchange(ref state, Running, Pending)", execute);
            Assert.Contains("CompareExchange(ref state, Abandoned, Pending)", tryAbandon);
            Assert.Contains("completion.TrySetCanceled();", tryAbandon);
            Assert.Contains("dispatch.Abandon();", dispatchWithTimeout);
            Assert.Contains("throw new TimeoutException(", dispatchWithTimeout);
            Assert.DoesNotContain("ExternalEvent", ExecutableCode(runtime));
        }

        [Fact]
        public void RevitTask7_DispatchDoesNotMaskFaultedTasksWithAggregateException()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var dispatch = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private T Dispatch<T>(BimDiagnosticContext diagnostics, Func<UIApplication, T> work)");
            var describeException = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private static string DescribeDispatchException(Exception ex)");

            Assert.DoesNotContain(".Wait(DispatchTimeout)", dispatch);
            Assert.Contains("Task.WaitAny", dispatch);
            Assert.Contains("dispatch.Task.GetAwaiter().GetResult();", dispatch);
            Assert.Contains("AggregateException", describeException);
            Assert.Contains("aggregate.Flatten()", describeException);
        }

        [Fact]
        public void RevitTask7_StatusDispatchFailureKeepsRookBimRuntime()
        {
            var runtime = NormalizeLineEndings(Read("src/RookBim/Revit/RevitRookBimRuntime.cs"));
            var status = ExtractSourceMember(
                runtime,
                RuntimeType,
                "public BimStatusResponse Status(BimDiagnosticContext diagnostics)");

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
                status);
            Assert.DoesNotContain("Runtime = \"unavailable\"", status);
        }

        [Fact]
        public void RevitTask10_SelectionServiceUsesResolvedIdentitiesAndUiSelectionOnly()
        {
            var service = Read("src/RookBim/Revit/RevitSelectionService.cs");
            var select = ExtractExecutableMember(
                service,
                "internal sealed class RevitSelectionService",
                "public BimApiResponse Select(UIDocument uiDocument, BimSelectElementsRequest? request)");
            var clear = ExtractExecutableMember(
                service,
                "internal sealed class RevitSelectionService",
                "public BimApiResponse Clear(UIDocument uiDocument)");

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
            Assert.DoesNotContain("Transaction", ExecutableCode(service));
            Assert.DoesNotContain("OverrideGraphicSettings", ExecutableCode(service));
            Assert.DoesNotContain("TemporaryView", ExecutableCode(service));
        }

        [Fact]
        public void RevitTask10_RuntimeWiresSelectionThroughDispatcher()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var selectionField = ExtractExecutableDirectMember(
                runtime,
                RuntimeType,
                "private readonly RevitSelectionService selection;");
            var constructor = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "internal RevitRookBimRuntime(RevitApiDispatcher dispatcher)");
            var select = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse SelectElements(BimDiagnosticContext diagnostics, BimSelectElementsRequest request)");
            var clear = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse ClearSelection(BimDiagnosticContext diagnostics)");

            Assert.Equal(
                RemoveWhitespace("private readonly RevitSelectionService selection;"),
                RemoveWhitespace(selectionField));
            Assert.Contains("this.selection = new RevitSelectionService();", constructor);
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
            var liveCategories = ExtractExecutableMember(
                resolver,
                CategoryResolverType,
                "private static LiveCategoryTable LiveCategories(Document document, BimDiagnosticContext diagnostics)");

            Assert.Contains("BimDiagnosticEnumerator.ForEach<Category>", liveCategories);
            Assert.Contains("TryBuildCategoryEntry", liveCategories);
            Assert.Contains("SkippedCount", liveCategories);
            Assert.Contains("DegradedCount", liveCategories);
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
            Assert.Contains("SafeCategoryId", resolver);
            Assert.Contains("SafeCategoryName", resolver);
            Assert.Contains("SafeCategoryType", resolver);
            Assert.Contains("catch (Autodesk.Revit.Exceptions.InternalException)", resolver);
            Assert.Contains("catch (Autodesk.Revit.Exceptions.InvalidOperationException)", resolver);
            Assert.Contains("Diagnostics", resolver);
            Assert.Contains("RecordSkip", liveCategories);
            Assert.Contains("RecordDegradation", liveCategories);
            Assert.Contains("SafeBuiltInCategory", resolver);
            Assert.Contains("ResolveBuiltIn(document, builtIn)", resolver);
            Assert.DoesNotContain("BuiltInsByCategoryId", resolver);
            Assert.DoesNotContain("SafeCategoryParent", resolver);
            Assert.DoesNotContain(".Where(entry => string.IsNullOrEmpty(normalizedInput)", resolver);
            Assert.DoesNotContain("knowledge", resolver, StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void RevitCategoryResolver_ProbesCategoryMapAndDelegatesAllTraversal()
        {
            var resolver = NormalizeLineEndings(
                Read("src/RookBim/Revit/RevitCategoryResolver.cs"));
            var liveCategories = ExtractExecutableMember(
                resolver,
                CategoryResolverType,
                "private static LiveCategoryTable LiveCategories(Document document, BimDiagnosticContext diagnostics)");

            Assert.Contains("var settings = diagnostics.Enabled", liveCategories);
            Assert.Contains("BimDiagnosticStage.RevitCategoriesSettings", liveCategories);
            Assert.Contains("() => document.Settings", liveCategories);
            Assert.Contains(": document.Settings;", liveCategories);
            Assert.Equal(2, CountOccurrences(liveCategories, "document.Settings"));
            Assert.Equal(1, CountOccurrences(liveCategories, "() => document.Settings"));

            Assert.Contains("var categoryMap = diagnostics.Enabled", liveCategories);
            Assert.Contains("BimDiagnosticStage.RevitCategoriesCollection", liveCategories);
            Assert.Contains("() => settings.Categories", liveCategories);
            Assert.Contains(": settings.Categories;", liveCategories);
            Assert.Equal(2, CountOccurrences(liveCategories, "settings.Categories"));
            Assert.Equal(1, CountOccurrences(liveCategories, "() => settings.Categories"));
            Assert.Equal(2, CountOccurrences(liveCategories, "BimDiagnosticFields.None"));

            Assert.Contains(
                "BimDiagnosticEnumerator.ForEach<Category>(",
                liveCategories);
            Assert.Contains("diagnostics,", liveCategories);
            Assert.Contains("categoryMap,", liveCategories);
            Assert.Contains("(category, itemIndex) =>", liveCategories);
            Assert.Contains(
                "TryBuildCategoryEntry(category, diagnostics, itemIndex, out var entry)",
                liveCategories);
            Assert.DoesNotContain("foreach", liveCategories);
            Assert.DoesNotContain("GetEnumerator", liveCategories);
            Assert.DoesNotContain("MoveNext", liveCategories);
            Assert.DoesNotContain("Dispose", liveCategories);
            Assert.DoesNotContain("finally", liveCategories);
            Assert.DoesNotContain("catch", liveCategories);
        }

        [Fact]
        public void RevitCategoryResolver_IsolatesEachCategoryPropertyWithOnlyTheItemIndex()
        {
            var resolver = NormalizeLineEndings(
                Read("src/RookBim/Revit/RevitCategoryResolver.cs"));
            var buildEntry = ExtractExecutableMember(
                resolver,
                CategoryResolverType,
                "private static bool TryBuildCategoryEntry(Category category, BimDiagnosticContext diagnostics, long itemIndex, out CategoryEntry entry)");
            var safeId = ExtractExecutableMember(
                resolver,
                CategoryResolverType,
                "private static int? SafeCategoryId(Category category, BimDiagnosticContext diagnostics, long itemIndex)");
            var safeName = ExtractExecutableMember(
                resolver,
                CategoryResolverType,
                "private static string? SafeCategoryName(Category category, BimDiagnosticContext diagnostics, long itemIndex)");
            var safeBuiltIn = ExtractExecutableMember(
                resolver,
                CategoryResolverType,
                "private static string? SafeBuiltInCategory(Category category, BimDiagnosticContext diagnostics, long itemIndex)");
            var safeType = ExtractExecutableMember(
                resolver,
                CategoryResolverType,
                "private static string? SafeCategoryType(Category category, BimDiagnosticContext diagnostics, long itemIndex)");

            Assert.Contains("SafeCategoryId(category, diagnostics, itemIndex)", buildEntry);
            Assert.Contains("SafeCategoryName(category, diagnostics, itemIndex)", buildEntry);
            Assert.Contains("SafeBuiltInCategory(category, diagnostics, itemIndex)", buildEntry);
            Assert.Contains("SafeCategoryType(category, diagnostics, itemIndex)", buildEntry);

            AssertCategoryPropertyProbe(
                safeId,
                "BimDiagnosticStage.RevitCategoryId",
                "() => ToInt32OrNull(category.Id)",
                "ToInt32OrNull(category.Id)");
            AssertCategoryPropertyProbe(
                safeName,
                "BimDiagnosticStage.RevitCategoryName",
                "() => category.Name",
                "category.Name");
            AssertCategoryPropertyProbe(
                safeBuiltIn,
                "BimDiagnosticStage.RevitCategoryBuiltIn",
                "() => category.BuiltInCategory",
                "category.BuiltInCategory");
            AssertCategoryPropertyProbe(
                safeType,
                "BimDiagnosticStage.RevitCategoryType",
                "() => category.CategoryType.ToString()",
                "category.CategoryType.ToString()");
        }

        [Fact]
        public void RevitCategoryResolver_ThreadsContextAndLimitsDetailedIdentityToCategoryResults()
        {
            var resolver = NormalizeLineEndings(
                Read("src/RookBim/Revit/RevitCategoryResolver.cs"));
            var runtime = NormalizeLineEndings(
                Read("src/RookBim/Revit/RevitRookBimRuntime.cs"));
            var service = NormalizeLineEndings(
                Read("src/RookBim/Revit/RevitQueryService.cs"));
            var list = ExtractExecutableMember(
                resolver,
                CategoryResolverType,
                "public BimListCategoriesResult List(Document document, BimDiagnosticContext diagnostics)");
            var resolve = ExtractExecutableMember(
                resolver,
                CategoryResolverType,
                "public BimCategoryResolution Resolve(Document document, string? input, BimDiagnosticContext diagnostics)");
            var listCategories = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse ListCategories(BimDiagnosticContext diagnostics)");
            var queryElements = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse QueryElements(BimDiagnosticContext diagnostics, BimQueryElementsRequest request)");
            var query = ExtractExecutableMember(
                service,
                QueryServiceType,
                "public BimApiResponse Query(Document document, View? activeView, BimQueryElementsRequest request, BimDiagnosticContext diagnostics)");
            var untracedQuery = ExtractExecutableMember(
                service,
                QueryServiceType,
                "public BimApiResponse Query(Document document, View? activeView, BimQueryElementsRequest request)");
            var buildResult = ExtractExecutableMember(
                service,
                QueryServiceType,
                "private static BimQueryElementsResult BuildResult(Document document, View? activeView, BimQueryElementsRequest request, IReadOnlyCollection<Element> elements, bool truncated, Dictionary<string, int> missingCounts, BimCategoryResolution? categoryResolution)");

            Assert.Contains("LiveCategories(document, diagnostics)", list);
            Assert.Contains("LiveCategories(document, diagnostics)", resolve);
            Assert.Contains(
                RemoveWhitespace(
                    "RevitIdentitySerializer.DocumentIdentity(document, diagnostics, includeAuxiliaryState: false)"),
                RemoveWhitespace(list));
            Assert.Contains(
                RemoveWhitespace(
                    "RevitIdentitySerializer.DocumentIdentity(document, diagnostics, includeAuxiliaryState: false)"),
                RemoveWhitespace(resolve));
            Assert.Contains("categories.List(document, diagnostics)", listCategories);
            Assert.Contains("query.Query(document, view, request, diagnostics)", queryElements);
            Assert.Contains("categories.Resolve(document, categoryName, diagnostics)", query);
            Assert.Contains(
                "return Query(document, activeView, request, BimDiagnosticContext.Disabled);",
                untracedQuery);
            Assert.Contains(
                "Document = RevitIdentitySerializer.DocumentIdentity(document)",
                buildResult);
            Assert.DoesNotContain("diagnostics", buildResult);
        }

        [Fact]
        public void RevitCategoryResolver_TreatsInvalidBuiltInAsUnavailable()
        {
            var resolver = Read("src/RookBim/Revit/RevitCategoryResolver.cs");
            var safeBuiltIn = ExtractExecutableMember(
                resolver,
                "internal sealed class RevitCategoryResolver",
                "private static string? SafeBuiltInCategory(Category category, BimDiagnosticContext diagnostics, long itemIndex)");

            Assert.Contains("builtIn == BuiltInCategory.INVALID", safeBuiltIn);
            Assert.Contains("return null;", safeBuiltIn);
        }

        [Fact]
        public void RevitCategoryResolver_CatchesRevitInvalidOperationDuringExplicitBuiltInLookup()
        {
            var resolver = Read("src/RookBim/Revit/RevitCategoryResolver.cs");
            var tryGetBuiltIn = ExtractExecutableMember(
                resolver,
                "internal sealed class RevitCategoryResolver",
                "private static bool TryGetBuiltInCategory(Document document, BuiltInCategory builtIn, out Category category)");

            Assert.Contains("catch (Autodesk.Revit.Exceptions.InvalidOperationException)", tryGetBuiltIn);
        }

        [Fact]
        public void RevitRuntime_WiresListCategoriesThroughDispatcher()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var categoriesField = ExtractExecutableDirectMember(
                runtime,
                RuntimeType,
                "private readonly RevitCategoryResolver categories;");
            var constructor = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "internal RevitRookBimRuntime(RevitApiDispatcher dispatcher)");
            var listCategories = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse ListCategories(BimDiagnosticContext diagnostics)");
            var documentContext = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private BimApiResponse ExecuteInDocumentContext(BimDiagnosticContext diagnostics, string operation, Func<UIDocument, Document, BimApiResponse> work)");

            Assert.Equal(
                RemoveWhitespace("private readonly RevitCategoryResolver categories;"),
                RemoveWhitespace(categoriesField));
            Assert.Contains("this.categories = new RevitCategoryResolver();", constructor);
            Assert.Contains("return ExecuteInDocumentContext", listCategories);
            Assert.Contains("AcquireActiveUiDocument(uiapp, diagnostics)", documentContext);
            Assert.Contains("BimErrorCode.NoActiveDocument", documentContext);
            Assert.Contains("categories.List(document, diagnostics)", listCategories);
            Assert.DoesNotContain("BimErrorCode.NotRhinoInside", listCategories);
            Assert.Contains("BimErrorCode.InternalError", documentContext);
        }

        [Fact]
        public void RevitQueryService_UsesCategoryResolverAndReturnsResolutionEvidence()
        {
            var service = Read("src/RookBim/Revit/RevitQueryService.cs");
            var query = ExtractExecutableMember(
                service,
                "internal sealed class RevitQueryService",
                "public BimApiResponse Query(Document document, View? activeView, BimQueryElementsRequest request, BimDiagnosticContext diagnostics)");

            Assert.Contains("private readonly RevitCategoryResolver categories", service);
            Assert.Contains("categories.Resolve(document, categoryName, diagnostics)", query);
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
            var elementInfo = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse ElementInfo(BimDiagnosticContext diagnostics, BimElementRequest request)");
            var elementParameters = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse ElementParameters(BimDiagnosticContext diagnostics, BimElementRequest request)");

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
            var queryField = ExtractExecutableDirectMember(
                runtime,
                RuntimeType,
                "private readonly RevitQueryService query;");
            var constructor = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "internal RevitRookBimRuntime(RevitApiDispatcher dispatcher)");
            var queryElements = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "public BimApiResponse QueryElements(BimDiagnosticContext diagnostics, BimQueryElementsRequest request)");
            var documentContext = ExtractExecutableMember(
                runtime,
                RuntimeType,
                "private BimApiResponse ExecuteInDocumentContext(BimDiagnosticContext diagnostics, string operation, Func<UIDocument, Document, BimApiResponse> work)");

            Assert.Equal(
                RemoveWhitespace("private readonly RevitQueryService query;"),
                RemoveWhitespace(queryField));
            Assert.Contains("this.query = new RevitQueryService();", constructor);
            Assert.Contains("return ExecuteInDocumentContext", queryElements);
            Assert.Contains("AcquireActiveUiDocument(uiapp, diagnostics)", documentContext);
            Assert.Contains("BimErrorCode.NoActiveDocument", documentContext);
            Assert.Contains("query.Query(document, view, request, diagnostics)", queryElements);
            Assert.DoesNotContain("LaterToolUnavailable", queryElements);
        }

        [Fact]
        public void RevitTask8_QueryServiceUsesBoundedCollectorsAndEffectiveFilters()
        {
            var service = Read("src/RookBim/Revit/RevitQueryService.cs");
            var query = ExtractExecutableMember(
                service,
                "internal sealed class RevitQueryService",
                "public BimApiResponse Query(Document document, View? activeView, BimQueryElementsRequest request, BimDiagnosticContext diagnostics)");
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
            var query = ExtractExecutableMember(
                service,
                "internal sealed class RevitQueryService",
                "public BimApiResponse Query(Document document, View? activeView, BimQueryElementsRequest request, BimDiagnosticContext diagnostics)");
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
            var query = ExtractExecutableMember(
                service,
                "internal sealed class RevitQueryService",
                "public BimApiResponse Query(Document document, View? activeView, BimQueryElementsRequest request, BimDiagnosticContext diagnostics)");
            var collect = ExtractExecutableMember(
                service,
                "internal sealed class RevitQueryService",
                "private static CappedElementCollection CollectUnfilteredResults(FilteredElementCollector collector, int limit)");

            Assert.Contains("if (filters.Count == 0)", query);
            Assert.Contains("CollectUnfilteredResults(collector, request.EffectiveLimit)", query);
            Assert.Contains("return BimApiResponse.Ok(BuildResult(", query);
            Assert.Contains("limit + 1", service);
            Assert.Contains("break;", collect);
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
            var query = ExtractExecutableMember(
                service,
                QueryServiceType,
                "public BimApiResponse Query(Document document, View? activeView, BimQueryElementsRequest request, BimDiagnosticContext diagnostics)");

            Assert.Contains("categories.Resolve(document, categoryName, diagnostics)", query);
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

        private static void AssertCategoryPropertyProbe(
            string source,
            string stage,
            string enabledExpression,
            string directExpression)
        {
            var compact = RemoveWhitespace(source);
            var fields = RemoveWhitespace(
                "new BimDiagnosticFields(BimDiagnosticDetailCode.None, itemIndex, " +
                "BimDiagnosticFailureImpact.Production)");

            Assert.Contains("diagnostics.Enabled", source);
            Assert.Contains("BimDiagnosticProbe.Production(", source);
            Assert.Contains(stage, source);
            Assert.Contains(enabledExpression, source);
            Assert.Contains(": " + directExpression + ";", source);
            Assert.Equal(2, CountOccurrences(source, directExpression));
            Assert.Equal(1, CountOccurrences(source, enabledExpression));
            Assert.Equal(1, CountOccurrences(compact, fields));
            Assert.Equal(1, CountOccurrences(compact, "newBimDiagnosticFields("));
            Assert.DoesNotContain("BimDiagnosticFields.None", source);
            Assert.DoesNotContain("Parent", source);
            Assert.Equal(2, CountOccurrences(source, "catch ("));
            Assert.Contains(
                "catch (Autodesk.Revit.Exceptions.InvalidOperationException)",
                source);
            Assert.Contains("catch (InvalidOperationException)", source);
        }

        private static void AssertNoLegacySourceMatchingIdentifiers(string source)
        {
            var identifiers = ExecutableIdentifierTokens(source);
            Assert.DoesNotContain("ExtractMethod", identifiers);
            Assert.DoesNotContain("FindIgnoringWhitespace", identifiers);
        }

        private static IReadOnlyList<string> ExecutableIdentifierTokens(
            string source)
        {
            var identifiers = new List<string>();
            AddIdentifierTokens(ExecutableCode(source), identifiers);
            foreach (var expression in InterpolatedExpressions(source))
            {
                identifiers.AddRange(ExecutableIdentifierTokens(expression));
            }

            return identifiers;
        }

        private static void AddIdentifierTokens(
            string code,
            ICollection<string> identifiers)
        {
            for (var index = 0; index < code.Length;)
            {
                var identifierStart = index;
                if (code[index] == '@' &&
                    index + 1 < code.Length &&
                    IsIdentifierStart(code[index + 1]))
                {
                    identifierStart = ++index;
                }
                else if (!IsIdentifierStart(code[index]))
                {
                    index++;
                    continue;
                }

                index++;
                while (index < code.Length &&
                       IsIdentifierCharacter(code[index]))
                {
                    index++;
                }

                identifiers.Add(code.Substring(
                    identifierStart,
                    index - identifierStart));
            }
        }

        private static IReadOnlyList<string> InterpolatedExpressions(
            string source)
        {
            var expressions = new List<string>();
            var outsideCode = ExecutableCode(source);
            for (var index = 0; index < source.Length;)
            {
                if (outsideCode[index] == '$' &&
                    TryCollectInterpolatedExpressions(
                        source,
                        outsideCode,
                        index,
                        expressions,
                        out var stringEnd))
                {
                    index = stringEnd;
                    continue;
                }

                index++;
            }

            return expressions;
        }

        private static bool TryCollectInterpolatedExpressions(
            string source,
            string outsideCode,
            int dollarStart,
            ICollection<string> expressions,
            out int stringEnd)
        {
            var dollarCount = CountRun(source, dollarStart, '$');
            var quoteIndex = dollarStart + dollarCount;
            var verbatim = false;
            if (quoteIndex < source.Length && source[quoteIndex] == '@')
            {
                verbatim = true;
                quoteIndex++;
            }
            else if (dollarStart > 0 &&
                     source[dollarStart - 1] == '@' &&
                     outsideCode[dollarStart - 1] == '@')
            {
                verbatim = true;
            }

            if (quoteIndex >= source.Length || source[quoteIndex] != '"')
            {
                stringEnd = dollarStart + 1;
                return false;
            }

            var quoteCount = CountRun(source, quoteIndex, '"');
            if (quoteCount >= 3 && !verbatim)
            {
                stringEnd = CollectRawInterpolatedExpressions(
                    source,
                    quoteIndex,
                    quoteCount,
                    dollarCount,
                    expressions);
                return true;
            }

            if (quoteCount != 1 || dollarCount != 1)
            {
                stringEnd = dollarStart + 1;
                return false;
            }

            stringEnd = CollectQuotedInterpolatedExpressions(
                source,
                quoteIndex,
                verbatim,
                expressions);
            return true;
        }

        private static int CollectQuotedInterpolatedExpressions(
            string source,
            int quoteIndex,
            bool verbatim,
            ICollection<string> expressions)
        {
            var index = quoteIndex + 1;
            while (index < source.Length)
            {
                if (source[index] == '"')
                {
                    if (verbatim &&
                        index + 1 < source.Length &&
                        source[index + 1] == '"')
                    {
                        index += 2;
                        continue;
                    }

                    return index + 1;
                }

                if (!verbatim && source[index] == '\\')
                {
                    index = Math.Min(index + 2, source.Length);
                    continue;
                }

                if (source[index] == '{')
                {
                    if (index + 1 < source.Length &&
                        source[index + 1] == '{')
                    {
                        index += 2;
                        continue;
                    }

                    var expressionStart = index + 1;
                    var expressionEnd = FindInterpolationExpressionEnd(
                        source,
                        expressionStart,
                        closingBraceCount: 1);
                    if (expressionEnd < 0)
                    {
                        return source.Length;
                    }

                    expressions.Add(source.Substring(
                        expressionStart,
                        expressionEnd - expressionStart));
                    index = expressionEnd + 1;
                    continue;
                }

                index++;
            }

            return source.Length;
        }

        private static int CollectRawInterpolatedExpressions(
            string source,
            int quoteIndex,
            int quoteCount,
            int dollarCount,
            ICollection<string> expressions)
        {
            var index = quoteIndex + quoteCount;
            while (index < source.Length)
            {
                if (source[index] == '"' &&
                    CountRun(source, index, '"') >= quoteCount)
                {
                    return index + quoteCount;
                }

                if (source[index] == '{' &&
                    CountRun(source, index, '{') >= dollarCount)
                {
                    var expressionStart = index + dollarCount;
                    var expressionEnd = FindInterpolationExpressionEnd(
                        source,
                        expressionStart,
                        dollarCount);
                    if (expressionEnd < 0)
                    {
                        return source.Length;
                    }

                    expressions.Add(source.Substring(
                        expressionStart,
                        expressionEnd - expressionStart));
                    index = expressionEnd + dollarCount;
                    continue;
                }

                index++;
            }

            return source.Length;
        }

        private static int FindInterpolationExpressionEnd(
            string source,
            int expressionStart,
            int closingBraceCount)
        {
            var remainder = source.Substring(expressionStart);
            var code = ExecutableCode(remainder);
            var braces = 0;
            for (var offset = 0; offset < code.Length; offset++)
            {
                if (code[offset] == '{')
                {
                    braces++;
                    continue;
                }

                if (code[offset] != '}')
                {
                    continue;
                }

                if (braces > 0)
                {
                    braces--;
                    continue;
                }

                if (CountRun(code, offset, '}') >= closingBraceCount)
                {
                    return expressionStart + offset;
                }
            }

            return -1;
        }

        private static void AssertNoWholeSourcePositiveContains(
            string source,
            params string[] wholeSourceIdentifiers)
        {
            var lexed = Lex(source);
            var identifiers = new HashSet<string>(
                wholeSourceIdentifiers.Select(NormalizeIdentifier),
                StringComparer.Ordinal);
            AddProductionSourceOrigins(lexed, identifiers);

            foreach (var identifier in identifiers)
            {
                var pattern =
                    @"\bAssert\s*\.\s*Contains\s*\([^;]*" +
                    @"(?<![A-Za-z0-9_])@?" +
                    Regex.Escape(identifier) +
                    @"(?![A-Za-z0-9_])[^;]*\)\s*;";
                Assert.False(
                    Regex.IsMatch(
                        lexed.CodeMask,
                        pattern,
                        RegexOptions.CultureInvariant |
                        RegexOptions.Singleline),
                    "Positive Assert.Contains references whole-source identifier '" +
                    identifier + "'.");
            }
        }

        private static void AddProductionSourceOrigins(
            LexedSource source,
            ISet<string> identifiers)
        {
            var assignments = Regex.Matches(
                source.CodeMask,
                @"(?<![A-Za-z0-9_])var\s+" +
                @"(?<target>@?[A-Za-z_][A-Za-z0-9_]*)\s*=\s*" +
                @"(?<expression>[^;]*);",
                RegexOptions.CultureInvariant);

            foreach (Match assignment in assignments)
            {
                var expression = assignment.Groups["expression"];
                if (IsProductionSourceRead(
                        source.WithoutComments.Substring(
                            expression.Index,
                            expression.Length),
                        expression.Value))
                {
                    identifiers.Add(NormalizeIdentifier(
                        assignment.Groups["target"].Value));
                }
            }

            var addedAlias = true;
            while (addedAlias)
            {
                addedAlias = false;
                foreach (Match assignment in assignments)
                {
                    if (TryGetDirectSourceIdentifier(
                            assignment.Groups["expression"].Value,
                            out var sourceIdentifier) &&
                        identifiers.Contains(sourceIdentifier))
                    {
                        addedAlias |= identifiers.Add(NormalizeIdentifier(
                            assignment.Groups["target"].Value));
                    }
                }
            }
        }

        private static bool IsProductionSourceRead(
            string sourceExpression,
            string codeExpression)
        {
            var expression = StripOuterParentheses(
                RemoveWhitespace(codeExpression));
            const string normalizePrefix = "NormalizeLineEndings(";
            if (expression.StartsWith(
                    normalizePrefix,
                    StringComparison.Ordinal) &&
                expression.EndsWith(")", StringComparison.Ordinal))
            {
                expression = StripOuterParentheses(expression.Substring(
                    normalizePrefix.Length,
                    expression.Length - normalizePrefix.Length - 1));
            }

            if (expression != "Read()")
            {
                return false;
            }

            var paths = Regex.Matches(
                sourceExpression,
                "\"(?<path>[^\"]+)\"",
                RegexOptions.CultureInvariant);
            if (paths.Count != 1)
            {
                return false;
            }

            var path = paths[0]
                .Groups["path"]
                .Value
                .Replace('\\', '/');
            return path.StartsWith(
                    "src/RookBim/",
                    StringComparison.OrdinalIgnoreCase) &&
                path.EndsWith(".cs", StringComparison.OrdinalIgnoreCase);
        }

        private static bool TryGetDirectSourceIdentifier(
            string codeExpression,
            out string identifier)
        {
            var expression = StripOuterParentheses(
                RemoveWhitespace(codeExpression));
            const string normalizePrefix = "NormalizeLineEndings(";
            if (expression.StartsWith(
                    normalizePrefix,
                    StringComparison.Ordinal) &&
                expression.EndsWith(")", StringComparison.Ordinal))
            {
                expression = StripOuterParentheses(expression.Substring(
                    normalizePrefix.Length,
                    expression.Length - normalizePrefix.Length - 1));
            }

            if (!Regex.IsMatch(
                    expression,
                    @"^@?[A-Za-z_][A-Za-z0-9_]*$",
                    RegexOptions.CultureInvariant))
            {
                identifier = string.Empty;
                return false;
            }

            identifier = NormalizeIdentifier(expression);
            return true;
        }

        private static string StripOuterParentheses(string expression)
        {
            while (expression.Length >= 2 && expression[0] == '(')
            {
                var depth = 0;
                var closingParenthesis = -1;
                for (var index = 0; index < expression.Length; index++)
                {
                    if (expression[index] == '(')
                    {
                        depth++;
                    }
                    else if (expression[index] == ')' && --depth == 0)
                    {
                        closingParenthesis = index;
                        break;
                    }
                }

                if (closingParenthesis != expression.Length - 1)
                {
                    break;
                }

                expression = expression.Substring(
                    1,
                    expression.Length - 2);
            }

            return expression;
        }

        private static string NormalizeIdentifier(string identifier)
        {
            return identifier.Length > 0 && identifier[0] == '@'
                ? identifier.Substring(1)
                : identifier;
        }

        private static string ExtractSourceMember(
            string source,
            string typeDeclaration,
            string memberDeclaration)
        {
            var lexed = Lex(source);
            var type = FindUniqueBlockDeclaration(
                lexed.CodeMask,
                typeDeclaration,
                0,
                lexed.CodeMask.Length,
                containingBodyStart: null);
            var member = FindUniqueBlockDeclaration(
                lexed.CodeMask,
                memberDeclaration,
                type.BodyStart + 1,
                type.BodyEnd,
                type.BodyStart);

            return lexed.WithoutComments.Substring(
                member.DeclarationStart,
                member.BodyEnd - member.DeclarationStart + 1);
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

        private static string ExtractExecutableDirectMember(
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
            var member = FindUniqueDirectMemberDeclaration(
                code,
                code,
                type,
                memberDeclaration);

            return code.Substring(
                member.Start,
                member.End - member.Start);
        }

        private static string ExtractSourceDirectMember(
            string source,
            string typeDeclaration,
            string memberDeclaration)
        {
            var lexed = Lex(source);
            var type = FindUniqueBlockDeclaration(
                lexed.CodeMask,
                typeDeclaration,
                0,
                lexed.CodeMask.Length,
                containingBodyStart: null);
            var member = FindUniqueDirectMemberDeclaration(
                lexed.CodeMask,
                lexed.WithoutComments,
                type,
                memberDeclaration);

            return lexed.WithoutComments.Substring(
                member.Start,
                member.End - member.Start);
        }

        private static SourceSpan FindUniqueDirectMemberDeclaration(
            string code,
            string declarationSource,
            SourceBlock type,
            string memberDeclaration)
        {
            var significantDeclaration = new string(memberDeclaration
                .Where(character => !char.IsWhiteSpace(character))
                .ToArray());
            if (significantDeclaration.Length == 0)
            {
                throw new ArgumentException(
                    "Declaration must contain a non-whitespace character.",
                    nameof(memberDeclaration));
            }

            var matches = new List<SourceSpan>();
            for (var candidate = type.BodyStart + 1;
                 candidate < type.BodyEnd;
                 candidate++)
            {
                if (char.IsWhiteSpace(declarationSource[candidate]) ||
                    declarationSource[candidate] != significantDeclaration[0] ||
                    HasIdentifierPrefix(
                        declarationSource,
                        candidate,
                        significantDeclaration[0]) ||
                    BraceDepth(code, type.BodyStart + 1, candidate) != 0)
                {
                    continue;
                }

                if (TryMatchIgnoringWhitespace(
                        declarationSource,
                        candidate,
                        type.BodyEnd,
                        significantDeclaration,
                        out var declarationEnd))
                {
                    matches.Add(new SourceSpan(candidate, declarationEnd));
                }
            }

            if (matches.Count != 1)
            {
                throw new InvalidOperationException(
                    "Expected exactly one direct member declaration for '" +
                    memberDeclaration + "' but found " + matches.Count + ".");
            }

            return matches[0];
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

        private static bool IsIdentifierStart(char value)
        {
            return char.IsLetter(value) || value == '_';
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

        private sealed class SourceSpan
        {
            public SourceSpan(int start, int end)
            {
                Start = start;
                End = end;
            }

            public int Start { get; }

            public int End { get; }
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
