using System.IO;
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
        public void GrasshopperStatusDto_RetainsNeutralRepairCompatibilityFields()
        {
            var dto = new GrasshopperStatusDto
            {
                SolverEnabled = false,
                SolverStateKnown = true,
                SolverGlobalEnableSolutions = true,
                SolverDocumentEnabled = false,
                RirRepairAttempted = false,
                RirRepairHeld = false,
                RirRepairReason = null,
                RirRepairSource = null,
            };

            Assert.False(dto.SolverEnabled);
            Assert.True(dto.SolverGlobalEnableSolutions);
            Assert.False(dto.SolverDocumentEnabled);
            Assert.False(dto.RirRepairAttempted);
            Assert.False(dto.RirRepairHeld);
            Assert.Null(dto.RirRepairReason);
            Assert.Null(dto.RirRepairSource);

            var handlerSource = File.ReadAllText(Path.Combine(
                RepoRoot(), "src", "Rook", "Handlers", "GrasshopperHandler.cs"));
            Assert.Contains("status.Data.RirRepairAttempted = false", handlerSource);
            Assert.Contains("status.Data.RirRepairHeld = false", handlerSource);
            Assert.Contains("status.Data.RirRepairReason = null", handlerSource);
            Assert.Contains("status.Data.RirRepairSource = null", handlerSource);
        }

        private static string RepoRoot()
        {
            var dir = new DirectoryInfo(Directory.GetCurrentDirectory());
            while (dir != null && !File.Exists(Path.Combine(dir.FullName, "src", "Rook", "Handlers", "GrasshopperHandler.cs")))
                dir = dir.Parent;
            Assert.NotNull(dir);
            return dir!.FullName;
        }
    }
}
