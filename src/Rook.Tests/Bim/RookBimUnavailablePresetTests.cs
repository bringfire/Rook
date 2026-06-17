using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class RookBimUnavailablePresetTests
    {
        [Fact]
        public void ExportPreset_ReturnsUnavailable()
        {
            var runtime = new RookBimUnavailableRuntime("rookbim_unavailable", "nope");
            var response = runtime.ExportPreset(new BimExportPresetRequest());
            Assert.False(response.Success);
            Assert.Equal(BimErrorCode.RookBimUnavailable, response.ErrorCode);
            Assert.Equal(503, response.HttpStatus);
        }
    }
}
