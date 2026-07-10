using System.IO;
using Xunit;

namespace Rook.Tests.Handlers
{
    public sealed class GrasshopperDocumentLifecycleSourceTests
    {
        [Fact]
        public void NewDocument_MarksRookManagedDocument()
        {
            var source = File.ReadAllText(Path.Combine(RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.cs"));

            Assert.Contains("_solveReadinessCoordinator.MarkRookManagedDocument(newDocument, \"gh_document_new\")", source);
            Assert.Contains("EnsureReadinessSession(newDocument, gh.Canvas!)", source);
        }

        [Fact]
        public void OpenDocument_MarksRookManagedDocument()
        {
            var source = File.ReadAllText(Path.Combine(RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.cs"));

            Assert.Contains("_solveReadinessCoordinator.MarkRookManagedDocument(newDocument, \"gh_document_open\")", source);
            Assert.Contains("EnsureReadinessSession(newDocument, gh.Canvas!)", source);
        }

        private static string RepoRoot()
        {
            var dir = new DirectoryInfo(Directory.GetCurrentDirectory());
            while (dir != null && !File.Exists(Path.Combine(dir.FullName, "src", "Rook", "Handlers", "GrasshopperHandler.cs")))
            {
                dir = dir.Parent;
            }

            Assert.NotNull(dir);
            return dir!.FullName;
        }
    }
}
