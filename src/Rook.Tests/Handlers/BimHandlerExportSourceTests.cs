using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class BimHandlerExportSourceTests
    {
        private static string Read(string rel)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null)
            {
                var candidate = Path.Combine(dir.FullName, rel.Replace('/', Path.DirectorySeparatorChar));
                if (File.Exists(candidate)) return File.ReadAllText(candidate);
                dir = dir.Parent;
            }
            throw new FileNotFoundException(rel);
        }

        [Fact]
        public void BimHandler_RegistersExportElementsOpRouteAndErrorCodes()
        {
            var src = Read("src/Rook/Handlers/BimHandler.cs");

            Assert.Contains("\"export_elements\"", src);
            Assert.Contains("\"export_elements\" => DispatchTypedRequest<BimExportElementsRequest>(", src);
            Assert.Contains("request => runtime.ExportElements(diagnostics, request)", src);
            Assert.Contains("POST /bim/export-elements", src);

            var typedDispatch = ExtractFunction(src,
                "private ApiResponse DispatchTypedRequest<T>(");
            Assert.Contains("DeserializeRequest<T>(diagnostics, body)", typedDispatch);
            Assert.Contains("InvokeRuntime(diagnostics, () => runtimeCall(request))", typedDispatch);
            Assert.True(
                typedDispatch.IndexOf("DeserializeRequest<T>", StringComparison.Ordinal) <
                typedDispatch.IndexOf("InvokeRuntime", StringComparison.Ordinal));

            Assert.Contains("BimErrorCode.QueryTruncated => \"query_truncated\"", src);
            Assert.Contains("BimErrorCode.OutputPathInvalid => \"output_path_invalid\"", src);
            Assert.Contains("BimErrorCode.NoExportableGeometry => \"no_exportable_geometry\"", src);
            Assert.Contains("BimErrorCode.ExportFailed => \"export_failed\"", src);
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
