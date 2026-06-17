using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class BimHandlerExportPresetSourceTests
    {
        private static readonly string RepoRoot = FindRepoRoot();

        [Fact]
        public void BimHandler_RegistersExportPresetOpRouteAndCodes()
        {
            var src = Read("src/Rook/Handlers/BimHandler.cs");

            Assert.Contains("\"export_preset\"", src);
            Assert.Contains("runtime.ExportPreset(DeserializeRequest<BimExportPresetRequest>(body))", src);
            Assert.Contains("\"export_preset\" => \"POST /bim/export-preset\"", src);
            Assert.Contains("BimErrorCode.UnknownPreset => \"unknown_preset\"", src);
            Assert.Contains("BimErrorCode.NoCategoriesResolved => \"no_categories_resolved\"", src);
        }

        [Fact]
        public void Native_ExposesExportPresetRouteAndHandler()
        {
            var server = Read("src/RookNative/RookServer.cpp");
            var handlerH = Read("src/RookNative/Handlers/GrasshopperProxyHandler.h");
            var handlerCpp = Read("src/RookNative/Handlers/GrasshopperProxyHandler.cpp");

            Assert.Contains("/bim/export-preset", server);
            Assert.Contains("HandleBimExportPreset", server);
            Assert.Contains("HandleBimExportPreset", handlerH);
            Assert.Contains("export_preset", handlerCpp);
        }

        internal static string Read(string relativePath)
        {
            return File.ReadAllText(Path.Combine(RepoRoot, relativePath.Replace('/', Path.DirectorySeparatorChar)));
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
