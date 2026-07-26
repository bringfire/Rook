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
            Assert.Contains("\"export_preset\" => DispatchTypedRequest<BimExportPresetRequest>(", src);
            Assert.Contains("request => runtime.ExportPreset(diagnostics, request)", src);
            Assert.Contains("\"export_preset\" => \"POST /bim/export-preset\"", src);
            Assert.Contains("BimErrorCode.UnknownPreset => \"unknown_preset\"", src);
            Assert.Contains("BimErrorCode.NoCategoriesResolved => \"no_categories_resolved\"", src);

            var typedDispatch = ExtractFunction(src,
                "private ApiResponse DispatchTypedRequest<T>(");
            Assert.Contains("DeserializeRequest<T>(diagnostics, body)", typedDispatch);
            Assert.Contains("InvokeRuntime(diagnostics, () => runtimeCall(request))", typedDispatch);
            Assert.True(
                typedDispatch.IndexOf("DeserializeRequest<T>", StringComparison.Ordinal) <
                typedDispatch.IndexOf("InvokeRuntime", StringComparison.Ordinal));
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

        private static string ExtractFunction(string source, string signature)
        {
            var start = source.IndexOf(signature, StringComparison.Ordinal);
            Assert.True(start >= 0, $"Could not find '{signature}'.");
            var bodyStart = source.IndexOf('{', start);
            var depth = 0;
            for (var index = bodyStart; index < source.Length; index++)
            {
                if (source[index] == '{') depth++;
                if (source[index] != '}') continue;
                depth--;
                if (depth == 0) return source.Substring(start, index - start + 1);
            }

            throw new InvalidOperationException($"Could not extract '{signature}'.");
        }
    }
}
