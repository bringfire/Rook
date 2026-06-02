using Rook.InternalBridge;
using Xunit;

namespace Rook.Tests.InternalBridge
{
    public class GrasshopperStatusDtoTests
    {
        [Fact]
        public void Dto_CarriesSolverFields_AndReadyForEditIsIndependent()
        {
            var dto = new GrasshopperStatusDto
            {
                ReadyForEdit = true,
                SolverEnabled = false,      // locked
                SolverStateKnown = true,
                SolutionState = "Off",
            };
            Assert.True(dto.ReadyForEdit);  // editing still allowed while locked
            Assert.False(dto.SolverEnabled);
            Assert.True(dto.SolverStateKnown);
            Assert.Equal("Off", dto.SolutionState);
        }
    }
}
