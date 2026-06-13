using Rook.InternalBridge;
using Xunit;

namespace Rook.Tests.InternalBridge
{
    public class GhSolverStateTests
    {
        private sealed class FakeEnabledDoc { public bool Enabled { get; set; } = true; }

        private sealed class FakeFlagDocument
        {
            public static bool EnableSolutions { get; set; } = true;
            public bool Enabled { get; set; } = true;
            public string SolutionState { get; set; } = "PreProcess";
        }

        [Fact]
        public void Inspect_PlainObject_IsUnknownAndFailsOpen()
        {
            var s = GhSolverState.Inspect(new object());
            Assert.False(s.Known);          // nothing readable
            Assert.True(s.Enabled ?? true); // fail-open
        }

        [Fact]
        public void Inspect_ObjectWithEnabledFalse_IsKnownAndDisabled()
        {
            var s = GhSolverState.Inspect(new FakeEnabledDoc { Enabled = false });
            Assert.True(s.Known);
            Assert.False(s.Enabled ?? true);
        }

        [Fact]
        public void Inspect_ReportsStaticAndInstanceFlagsSeparately()
        {
            FakeFlagDocument.EnableSolutions = true;
            var document = new FakeFlagDocument { Enabled = false };

            var result = GhSolverState.Inspect(document);

            Assert.True(result.Known);
            Assert.True(result.GlobalEnableSolutions);
            Assert.False(result.DocumentEnabled);
            Assert.False(result.Enabled);
        }

        [Fact]
        public void Inspect_StaticSolverLockDisablesSolverWithoutChangingInstanceFlag()
        {
            FakeFlagDocument.EnableSolutions = false;
            var document = new FakeFlagDocument { Enabled = true };

            var result = GhSolverState.Inspect(document);

            Assert.True(result.Known);
            Assert.False(result.GlobalEnableSolutions);
            Assert.True(result.DocumentEnabled);
            Assert.False(result.Enabled);

            FakeFlagDocument.EnableSolutions = true;
        }
    }
}
