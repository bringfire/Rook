using System;
using System.Linq;
using Rook.UI.Vision;
using Rook.UI.Web;
using Xunit;

namespace Rook.Tests.UI.Vision
{
    public class VisionPresentationStateStoreTests
    {
        [Fact]
        public void Snapshot_WhenEmpty_ReturnsSurfaceAbsentMetadata()
        {
            var store = new VisionPresentationStateStore();

            var snapshot = store.Snapshot();

            Assert.False(snapshot.SurfacePresent);
            Assert.Empty(snapshot.Entries);
        }

        [Fact]
        public void SurfaceRegistration_ControlsSurfacePresentMetadata()
        {
            var store = new VisionPresentationStateStore();
            var registration = store.RegisterSurface();

            Assert.True(store.Snapshot().SurfacePresent);

            registration.Dispose();
            Assert.False(store.Snapshot().SurfacePresent);

            registration.Dispose();
            Assert.False(store.Snapshot().SurfacePresent);
        }

        [Fact]
        public void Append_EvictsOldestEntriesAtCapacity()
        {
            var store = new VisionPresentationStateStore(capacity: 2);

            store.Append(CreateRecord("first"));
            store.Append(CreateRecord("second"));
            store.Append(CreateRecord("third"));

            var entries = store.Snapshot().Entries;
            Assert.Equal(2, entries.Count);
            Assert.Equal(new[] { "second", "third" }, entries.Select(e => e.Reason).ToArray());
        }

        [Fact]
        public void Append_AssignsMonotonicSequence()
        {
            var store = new VisionPresentationStateStore(capacity: 4);

            store.Append(CreateRecord("first"));
            store.Append(CreateRecord("second"));
            store.Append(CreateRecord("third"));

            var entries = store.Snapshot().Entries;
            Assert.Equal(new long[] { 1, 2, 3 }, entries.Select(e => e.Sequence).ToArray());
            Assert.True(entries[0].Utc <= entries[1].Utc);
            Assert.True(entries[1].Utc <= entries[2].Utc);
            Assert.All(entries, entry => Assert.True(entry.ThreadId > 0));
        }

        [Fact]
        public void Entries_ArePlainDtoFields()
        {
            var store = new VisionPresentationStateStore();

            store.Append(CreateRecord("dto"));

            var entry = Assert.Single(store.Snapshot().Entries);
            Assert.Equal("dto", entry.Reason);
            Assert.Equal(WebViewHostPresentationState.Hidden, entry.OldState);
            Assert.Equal(WebViewHostPresentationState.Presenting, entry.NewState);
            Assert.Equal(WebViewHostPresentationAction.PresentController, entry.Action);
            Assert.Equal(WebViewHostNotPresentableReason.None, entry.NotPresentableReason);
            Assert.True(entry.DesiredVisible);
            Assert.True(entry.AppActive);
            Assert.True(entry.PanelVisible);
            Assert.False(entry.TemporaryDeactivateHidden);
            Assert.False(entry.RequiresSelectedPanel);
            Assert.True(entry.PanelSelectedVisible);
            Assert.True(entry.EtoLoaded);
            Assert.True(entry.EtoVisible);
            Assert.Equal(640, entry.EtoWidth);
            Assert.Equal(480, entry.EtoHeight);
            Assert.True(entry.ParentWindowPresent);
            Assert.True(entry.HwndChainVisible);
            Assert.True(entry.HwndClientRectNonZero);
            Assert.True(entry.ControllerAvailable);
            Assert.True(entry.ControllerParentWindowPresent);
            Assert.False(entry.ControllerVisible);
            Assert.False(entry.ControllerBoundsMatchHostTarget);
            Assert.True(entry.ShouldSetControllerBounds);
            Assert.True(entry.ShouldSetControllerVisible);
            Assert.True(entry.ShouldNotifyParentPositionChanged);
            Assert.Equal("applied", entry.ActionResult);
            Assert.True(entry.Sequence > 0);
            Assert.NotEqual(default, entry.Utc);
            Assert.True(entry.ElapsedMilliseconds >= 0);
            Assert.True(entry.ThreadId > 0);
        }

        private static WebViewHostPresentationRecord CreateRecord(string reason)
            => new WebViewHostPresentationRecord
            {
                Reason = reason,
                OldState = WebViewHostPresentationState.Hidden,
                NewState = WebViewHostPresentationState.Presenting,
                Action = WebViewHostPresentationAction.PresentController,
                NotPresentableReason = WebViewHostNotPresentableReason.None,
                DesiredVisible = true,
                AppActive = true,
                TemporaryDeactivateHidden = false,
                PanelVisible = true,
                RequiresSelectedPanel = false,
                PanelSelectedVisible = true,
                EtoLoaded = true,
                EtoVisible = true,
                EtoWidth = 640,
                EtoHeight = 480,
                ParentWindowPresent = true,
                HwndChainVisible = true,
                HwndClientRectNonZero = true,
                ControllerAvailable = true,
                ControllerParentWindowPresent = true,
                ControllerVisible = false,
                ControllerBoundsMatchHostTarget = false,
                ShouldSetControllerBounds = true,
                ShouldSetControllerVisible = true,
                ShouldNotifyParentPositionChanged = true,
                ActionResult = "applied"
            };
    }
}
