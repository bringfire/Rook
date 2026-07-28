using Rook.Handlers;
using Xunit;

namespace Rook.Tests.Handlers
{
    public sealed class GhMutationSolveSuspensionTests
    {
        [Fact]
        public void Begin_Rir_IsNoOpWithZeroWrites()
        {
            SuspensionDocument.EnableSolutions = true;
            SuspensionDocument.ResetGlobalWriteCount();
            var document = new SuspensionDocument { Enabled = true };
            document.ResetWriteCount();

            var suspension = GhMutationSolveSuspension.Begin(document, runningAsRhinoInside: true);

            Assert.False(suspension.Active);
            Assert.True(document.Enabled);
            Assert.Equal(0, document.EnabledSetCount);
            Assert.Equal(0, SuspensionDocument.GlobalEnableSolutionsSetCount);
            Assert.False(suspension.Restore().Attempted);
            Assert.Equal(0, SuspensionDocument.GlobalEnableSolutionsSetCount);
        }

        [Fact]
        public void Begin_StandaloneEnabledDocument_DisablesOnceAndRestoresOnce()
        {
            SuspensionDocument.EnableSolutions = true;
            var document = new SuspensionDocument { Enabled = true };
            document.ResetWriteCount();

            var suspension = GhMutationSolveSuspension.Begin(document, runningAsRhinoInside: false);

            Assert.True(suspension.Active);
            Assert.False(document.Enabled);
            Assert.Equal(1, document.EnabledSetCount);
            var first = suspension.Restore();
            var second = suspension.Restore();

            Assert.True(first.Attempted);
            Assert.True(first.Succeeded);
            Assert.Null(first.FailureCode);
            Assert.True(first.ObservedDocumentEnabled);
            Assert.False(second.Attempted);
            Assert.True(second.Succeeded);
            Assert.Equal(2, document.EnabledSetCount);
        }

        [Fact]
        public void Begin_AlreadyDisabledOrUnknownDocument_DoesNotWrite()
        {
            SuspensionDocument.EnableSolutions = true;
            var disabled = new SuspensionDocument { Enabled = false };
            disabled.ResetWriteCount();
            var unknown = new UnknownDocument();

            var disabledSuspension = GhMutationSolveSuspension.Begin(disabled, runningAsRhinoInside: false);
            var unknownSuspension = GhMutationSolveSuspension.Begin(unknown, runningAsRhinoInside: false);

            Assert.False(disabledSuspension.Active);
            Assert.Equal(0, disabled.EnabledSetCount);
            Assert.False(unknownSuspension.Active);
            Assert.False(disabledSuspension.Restore().Attempted);
            Assert.False(unknownSuspension.Restore().Attempted);
        }

        [Fact]
        public void Restore_ThrowingSetter_ReportsFailureAndDoesNotRetry()
        {
            ThrowingRestoreDocument.EnableSolutions = true;
            var document = new ThrowingRestoreDocument { Enabled = true };
            document.ResetWriteCount();
            var suspension = GhMutationSolveSuspension.Begin(document, runningAsRhinoInside: false);
            document.ThrowWhenEnabling = true;

            var first = suspension.Restore();
            var second = suspension.Restore();

            Assert.True(first.Attempted);
            Assert.False(first.Succeeded);
            Assert.Equal(GhScheduleFailureCode.StandaloneSolverRestoreFailed, first.FailureCode);
            Assert.False(first.ObservedDocumentEnabled);
            Assert.False(second.Attempted);
            Assert.Equal(2, document.EnabledSetCount);
        }

        [Fact]
        public void Begin_DisableSetterMutatesThenThrows_RetainsOneShotRestorationOwnership()
        {
            MutateThenThrowDisableDocument.EnableSolutions = true;
            var document = new MutateThenThrowDisableDocument { Enabled = true };
            document.ResetWriteCount();
            document.ThrowAfterDisabling = true;

            var suspension = GhMutationSolveSuspension.Begin(document, runningAsRhinoInside: false);
            document.ThrowAfterDisabling = false;
            var restore = suspension.Restore();
            var retry = suspension.Restore();

            Assert.True(suspension.Active);
            Assert.True(restore.Attempted);
            Assert.True(restore.Succeeded);
            Assert.True(restore.ObservedDocumentEnabled);
            Assert.True(document.Enabled);
            Assert.False(retry.Attempted);
            Assert.Equal(2, document.EnabledSetCount);
        }

        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public void Restore_ReturningSetterThatLeavesObservedFalse_ReportsFailure(bool transientlyEnables)
        {
            FalseRestoreDocument.EnableSolutions = true;
            var document = new FalseRestoreDocument { Enabled = true };
            document.ResetWriteCount();
            var suspension = GhMutationSolveSuspension.Begin(document, runningAsRhinoInside: false);
            document.TransientlyEnableThenRevert = transientlyEnables;
            document.IgnoreOrRevertEnable = true;

            var restore = suspension.Restore();
            var retry = suspension.Restore();

            Assert.True(restore.Attempted);
            Assert.False(restore.Succeeded);
            Assert.Equal(GhScheduleFailureCode.StandaloneSolverRestoreFailed, restore.FailureCode);
            Assert.False(restore.ObservedDocumentEnabled);
            Assert.False(retry.Attempted);
            Assert.Equal(2, document.EnabledSetCount);
        }

        private sealed class SuspensionDocument
        {
            private static bool _enableSolutions;
            public static int GlobalEnableSolutionsSetCount { get; private set; }
            public static bool EnableSolutions
            {
                get => _enableSolutions;
                set { GlobalEnableSolutionsSetCount++; _enableSolutions = value; }
            }
            private bool _enabled;
            public int EnabledSetCount { get; private set; }
            public bool Enabled
            {
                get => _enabled;
                set { EnabledSetCount++; _enabled = value; }
            }
            public void ResetWriteCount() => EnabledSetCount = 0;
            public static void ResetGlobalWriteCount() => GlobalEnableSolutionsSetCount = 0;
        }

        private sealed class ThrowingRestoreDocument
        {
            public static bool EnableSolutions { get; set; }
            private bool _enabled;
            public int EnabledSetCount { get; private set; }
            public bool ThrowWhenEnabling { get; set; }
            public bool Enabled
            {
                get => _enabled;
                set
                {
                    EnabledSetCount++;
                    if (value && ThrowWhenEnabling) throw new System.InvalidOperationException("restore failed");
                    _enabled = value;
                }
            }
            public void ResetWriteCount() => EnabledSetCount = 0;
        }

        private sealed class UnknownDocument { }

        private sealed class MutateThenThrowDisableDocument
        {
            public static bool EnableSolutions { get; set; }
            private bool _enabled;
            public int EnabledSetCount { get; private set; }
            public bool ThrowAfterDisabling { get; set; }
            public bool Enabled
            {
                get => _enabled;
                set
                {
                    EnabledSetCount++;
                    _enabled = value;
                    if (!value && ThrowAfterDisabling)
                        throw new System.InvalidOperationException("disabled then threw");
                }
            }
            public void ResetWriteCount() => EnabledSetCount = 0;
        }

        private sealed class FalseRestoreDocument
        {
            public static bool EnableSolutions { get; set; }
            private bool _enabled;
            public int EnabledSetCount { get; private set; }
            public bool IgnoreOrRevertEnable { get; set; }
            public bool TransientlyEnableThenRevert { get; set; }
            public bool Enabled
            {
                get => _enabled;
                set
                {
                    EnabledSetCount++;
                    if (value && IgnoreOrRevertEnable)
                    {
                        if (TransientlyEnableThenRevert) _enabled = true;
                        _enabled = false;
                        return;
                    }
                    _enabled = value;
                }
            }
            public void ResetWriteCount() => EnabledSetCount = 0;
        }
    }
}
