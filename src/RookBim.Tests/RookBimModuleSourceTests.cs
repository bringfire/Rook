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
        public void RevitRuntimeSkeleton_DelegatesEveryOperationToUnavailableRuntime()
        {
            var text = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");

            Assert.Contains("IRookBimRuntime", text);
            Assert.Contains("\"not_rhino_inside\"", text);
            Assert.Contains("\"RookBIM is loaded, but Rhino is not running inside Revit.\"", text);
            Assert.DoesNotContain("ExternalEvent", text);
            Assert.DoesNotContain("ActiveUIDocument", text);

            AssertMethodDelegates(text, "Status", "fallback.Status()");
            AssertMethodDelegates(text, "ActiveDocument", "fallback.ActiveDocument()");
            AssertMethodDelegates(text, "QueryElements", "fallback.QueryElements(request)");
            AssertMethodDelegates(text, "ElementInfo", "fallback.ElementInfo(request)");
            AssertMethodDelegates(text, "ElementParameters", "fallback.ElementParameters(request)");
            AssertMethodDelegates(text, "SelectElements", "fallback.SelectElements(request)");
            AssertMethodDelegates(text, "ClearSelection", "fallback.ClearSelection()");
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

        private static void AssertMethodDelegates(string text, string methodName, string delegation)
        {
            Assert.Contains(methodName, text);
            Assert.Contains(delegation, text);
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
