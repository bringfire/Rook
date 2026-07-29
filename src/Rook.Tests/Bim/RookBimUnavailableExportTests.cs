using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class RookBimUnavailableExportTests
    {
        [Fact]
        public void ExportElements_ReturnsUnavailable()
        {
            var runtime = new RookBimUnavailableRuntime("rookbim_unavailable", "nope");
            var response = runtime.ExportElements(
                BimDiagnosticContext.Disabled,
                new BimExportElementsRequest());
            Assert.False(response.Success);
            Assert.Equal(BimErrorCode.RookBimUnavailable, response.ErrorCode);
            Assert.Equal(503, response.HttpStatus);
        }
    }
}
