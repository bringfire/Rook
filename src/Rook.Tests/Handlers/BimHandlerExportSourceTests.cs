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
            Assert.Contains("runtime.ExportElements(diagnostics,", src);
            Assert.Contains("DeserializeRequest<BimExportElementsRequest>(body)", src);
            Assert.Contains("POST /bim/export-elements", src);

            Assert.Contains("BimErrorCode.QueryTruncated => \"query_truncated\"", src);
            Assert.Contains("BimErrorCode.OutputPathInvalid => \"output_path_invalid\"", src);
            Assert.Contains("BimErrorCode.NoExportableGeometry => \"no_exportable_geometry\"", src);
            Assert.Contains("BimErrorCode.ExportFailed => \"export_failed\"", src);
        }
    }
}
