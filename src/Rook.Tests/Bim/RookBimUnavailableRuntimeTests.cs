using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class RookBimUnavailableRuntimeTests
    {
        [Fact]
        public void Status_ReturnsStructuredUnavailableEvidence()
        {
            var runtime = new RookBimUnavailableRuntime(
                "not_rhino_inside",
                "Rhino is not running inside Revit.");

            var status = runtime.Status();

            Assert.False(status.Available);
            Assert.Equal("not_rhino_inside", status.ErrorCode);
            Assert.Equal("Rhino is not running inside Revit.", status.Message);
            Assert.Equal("unavailable", status.Runtime);
        }

        [Fact]
        public void DocumentBoundOperations_ReturnUnavailableResponse()
        {
            const string configuredMessage = "Configured unavailable runtime message.";
            var runtime = new RookBimUnavailableRuntime(
                "not_rhino_inside",
                configuredMessage);

            AssertUnavailable(runtime.ActiveDocument(), configuredMessage);
            AssertUnavailable(runtime.QueryElements(new BimQueryElementsRequest()), configuredMessage);
            AssertUnavailable(runtime.ElementInfo(new BimElementRequest()), configuredMessage);
            AssertUnavailable(runtime.ElementParameters(new BimElementRequest()), configuredMessage);
            AssertUnavailable(runtime.SelectElements(new BimSelectElementsRequest()), configuredMessage);
            AssertUnavailable(runtime.ClearSelection(), configuredMessage);
        }

        private static void AssertUnavailable(BimApiResponse response, string expectedMessage)
        {
            Assert.False(response.Success);
            Assert.Equal(BimErrorCode.RookBimUnavailable, response.ErrorCode);
            Assert.Equal(expectedMessage, response.Message);
        }
    }
}
