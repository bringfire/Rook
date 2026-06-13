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

        [Fact]
        public void GrasshopperStatusDto_IncludesSolverFlagAndRirRepairDiagnostics()
        {
            var dto = new GrasshopperStatusDto
            {
                SolverEnabled = false,
                SolverStateKnown = true,
                SolverGlobalEnableSolutions = true,
                SolverDocumentEnabled = false,
                RirRepairAttempted = true,
                RirRepairHeld = false,
                RirRepairReason = "schedule_time_repair_did_not_hold",
            };

            Assert.False(dto.SolverEnabled);
            Assert.True(dto.SolverGlobalEnableSolutions);
            Assert.False(dto.SolverDocumentEnabled);
            Assert.True(dto.RirRepairAttempted);
            Assert.False(dto.RirRepairHeld);
            Assert.Equal("schedule_time_repair_did_not_hold", dto.RirRepairReason);
        }
    }
}
