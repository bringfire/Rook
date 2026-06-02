using Rook.InternalBridge;
using Xunit;

namespace Rook.Tests.InternalBridge
{
    public class GhSolverStateTests
    {
        private sealed class FakeEnabledDoc { public bool Enabled { get; set; } = true; }

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
    }
}
