using System;
using System.IO;
using System.Linq;
using System.Xml.Linq;
using Xunit;

namespace RookBim.Tests
{
    public class RookBimModuleSourceTests
    {
        private static readonly string RepoRoot = FindRepoRoot();

        [Fact]
        public void RookBimProject_TargetsNet48AndReferencesRevitApisPrivately()
        {
            var project = LoadProject("src/RookBim/RookBim.csproj");

            Assert.Equal("net48", ValueOf(project, "TargetFramework"));
            Assert.Equal("enable", ValueOf(project, "Nullable"));
            Assert.Equal("latest", ValueOf(project, "LangVersion"));

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

            Assert.DoesNotContain("RookBim.csproj", text, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("Autodesk.Revit", text, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("<Reference Include=\"RevitAPI", text, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain(
                project.Descendants("ProjectReference"),
                reference => AttributeValue(reference, "Include").IndexOf("RookBim", StringComparison.OrdinalIgnoreCase) >= 0);
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
            Assert.Contains("RookBimRuntimeRegistry.Install", text);
            Assert.Contains("new RevitRookBimRuntime()", text);
            Assert.Contains("\"RookBim.dll\"", text);
        }

        [Fact]
        public void RevitTask7_UsesExternalEventDispatcherWithoutTransactions()
        {
            var dispatcher = Read("src/RookBim/Revit/RevitApiDispatcher.cs");
            var revitFiles = Directory
                .GetFiles(Path.Combine(RepoRoot, "src", "RookBim", "Revit"), "*.cs")
                .Select(File.ReadAllText);
            var combined = string.Join(Environment.NewLine, revitFiles);

            Assert.Contains("IExternalEventHandler", dispatcher);
            Assert.Contains("ExternalEvent.Create", dispatcher);
            Assert.Contains(".Raise()", dispatcher);
            Assert.Contains("Execute(UIApplication uiapp)", dispatcher);
            Assert.Contains("TaskCompletionSource", dispatcher);
            Assert.DoesNotContain("Transaction", combined);
        }

        [Fact]
        public void RevitTask7_RuntimeUsesDispatcherForStatusAndActiveDocument()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var context = Read("src/RookBim/Revit/RevitContext.cs");
            var serializer = Read("src/RookBim/Revit/RevitIdentitySerializer.cs");

            Assert.Contains("RevitApiDispatcher", runtime);
            Assert.Contains("dispatcher.Invoke", runtime);
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

            Assert.Contains("View = SerializeActiveView(uidoc, document)", runtime);
            Assert.Contains("public BimViewIdentity? View { get; set; }", runtime);
            Assert.DoesNotContain("ActiveView = SerializeActiveView(uidoc, document)", runtime);
            Assert.DoesNotContain("public BimViewIdentity? ActiveView { get; set; }", runtime);
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
            Assert.Contains("var dispatch = dispatcher.InvokeAbandonable(work);", runtime);
            Assert.Contains("dispatch.Abandon();", runtime);
            Assert.Contains("throw new TimeoutException", runtime);
        }

        [Fact]
        public void RevitTask7_DispatchDoesNotMaskFaultedTasksWithAggregateException()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
            var dispatch = ExtractMethod(runtime, "private T Dispatch<T>(");

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
        public void RevitTask7_LaterToolsRemainCapabilityUnavailable()
        {
            var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");

            AssertLaterToolUnavailable(runtime, "QueryElements");
            AssertLaterToolUnavailable(runtime, "ElementInfo");
            AssertLaterToolUnavailable(runtime, "ElementParameters");
            AssertLaterToolUnavailable(runtime, "SelectElements");
            AssertLaterToolUnavailable(runtime, "ClearSelection");
        }

        [Fact]
        public void RevitTask7_DoesNotStartTask8QueryServiceOrCollectors()
        {
            var revitDirectory = Path.Combine(RepoRoot, "src", "RookBim", "Revit");
            var revitFiles = Directory.GetFiles(revitDirectory, "*.cs");
            var fileNames = revitFiles.Select(Path.GetFileName).ToArray();
            var combined = string.Join(Environment.NewLine, revitFiles.Select(File.ReadAllText));

            Assert.DoesNotContain(fileNames, name => name.IndexOf("Query", StringComparison.OrdinalIgnoreCase) >= 0);
            Assert.DoesNotContain("FilteredElementCollector", combined);
            Assert.DoesNotContain("ParameterFilterElement", combined);
            Assert.DoesNotContain("Selection.SetElementIds", combined);
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

        private static void AssertLaterToolUnavailable(string text, string methodName)
        {
            Assert.Contains(methodName, text);
            Assert.Contains("BimErrorCode.CapabilityUnavailable", text);
            Assert.Contains("501", text);
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

        private static string ExtractMethod(string source, string signatureStartText)
        {
            var signatureStart = source.IndexOf(
                signatureStartText,
                StringComparison.Ordinal);
            if (signatureStart < 0)
                throw new InvalidOperationException(
                    "Method not found: " + signatureStartText);

            var bodyStart = source.IndexOf('{', signatureStart);
            if (bodyStart < 0)
                throw new InvalidOperationException(
                    "Method body not found: " + signatureStartText);

            var depth = 0;
            for (var i = bodyStart; i < source.Length; i++)
            {
                if (source[i] == '{')
                    depth++;
                else if (source[i] == '}')
                {
                    depth--;
                    if (depth == 0)
                        return source.Substring(signatureStart, i - signatureStart + 1);
                }
            }

            throw new InvalidOperationException(
                "Brace did not close at index " + bodyStart);
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
