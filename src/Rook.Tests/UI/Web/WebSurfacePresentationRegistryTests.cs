using System;
using System.Collections.Generic;
using Rook.UI.Web;
using Xunit;

namespace Rook.Tests.UI.Web
{
    /// <summary>
    /// Coverage for the substrate-wide presentation registry. Surfaces
    /// register on content creation and deterministically deregister in
    /// Dispose; <c>ScheduleRepairAll</c> is accepted-and-scheduled — it
    /// returns <c>scheduled:&lt;n&gt;</c> immediately and never blocks
    /// on the gapped toggle.
    /// </summary>
    public class WebSurfacePresentationRegistryTests
    {
        private sealed class FakeSurface : RookWebSurface
        {
            protected override string ResourceRoot => "Rook.Tests.Registry";
            protected override string EntryPage => "test.html";
            protected override string MinimalFallbackHtml => "<html></html>";
            protected override void Log(string message) { }

            public List<string> ScheduledRepairReasons { get; } = new();

            internal override void SchedulePresentationRepair(string reason)
                => ScheduledRepairReasons.Add(reason);
        }

        [Fact]
        public void DumpAll_ContainsAllRegisteredSurfaces()
        {
            var a = new FakeSurface();
            var b = new FakeSurface();
            try
            {
                WebSurfacePresentationRegistry.Register(a);
                WebSurfacePresentationRegistry.Register(b);

                var dump = WebSurfacePresentationRegistry.DumpAll();

                Assert.Contains(a.SurfaceId, dump);
                Assert.Contains(b.SurfaceId, dump);
                Assert.NotEqual(a.SurfaceId, b.SurfaceId);
            }
            finally
            {
                a.Dispose();
                b.Dispose();
            }
        }

        [Fact]
        public void Dispose_Deregisters_DumpContainsOnlySurvivor()
        {
            var dead = new FakeSurface();
            var survivor = new FakeSurface();
            try
            {
                WebSurfacePresentationRegistry.Register(dead);
                WebSurfacePresentationRegistry.Register(survivor);

                dead.Dispose();

                var dump = WebSurfacePresentationRegistry.DumpAll();
                Assert.DoesNotContain(dead.SurfaceId, dump);
                Assert.Contains(survivor.SurfaceId, dump);
            }
            finally
            {
                dead.Dispose();
                survivor.Dispose();
            }
        }

        [Fact]
        public void Register_IsIdempotent_NoDuplicateEntries()
        {
            var s = new FakeSurface();
            try
            {
                WebSurfacePresentationRegistry.Register(s);
                WebSurfacePresentationRegistry.Register(s);

                Assert.Equal("scheduled:1",
                    WebSurfacePresentationRegistry.ScheduleRepairAll("test"));
            }
            finally
            {
                s.Dispose();
            }
        }

        [Fact]
        public void ScheduleRepairAll_ReturnsScheduledCount_AndSchedulesEachSurfaceOnce()
        {
            var a = new FakeSurface();
            var b = new FakeSurface();
            try
            {
                WebSurfacePresentationRegistry.Register(a);
                WebSurfacePresentationRegistry.Register(b);

                var result = WebSurfacePresentationRegistry.ScheduleRepairAll("test");

                Assert.Equal("scheduled:2", result);
                Assert.Equal(new[] { "test" }, a.ScheduledRepairReasons);
                Assert.Equal(new[] { "test" }, b.ScheduledRepairReasons);
            }
            finally
            {
                a.Dispose();
                b.Dispose();
            }
        }

        [Fact]
        public void ScheduleRepairAll_EmptyRegistry_ReturnsScheduledZero()
        {
            Assert.Equal("scheduled:0",
                WebSurfacePresentationRegistry.ScheduleRepairAll("test"));
        }
    }
}
