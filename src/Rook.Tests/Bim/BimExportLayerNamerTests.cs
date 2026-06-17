using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class BimExportLayerNamerTests
    {
        [Fact]
        public void Flat_AlwaysModelLayer()
        {
            Assert.Equal("RookBim::Model",
                BimExportLayerNamer.LayerPath(BimLayerScheme.Flat, "Walls", "Level 01"));
        }

        [Fact]
        public void ByCategory_UsesCategoryUnderRoot()
        {
            Assert.Equal("RookBim::Walls",
                BimExportLayerNamer.LayerPath(BimLayerScheme.ByCategory, "Walls", "Level 01"));
        }

        [Fact]
        public void ByLevelThenCategory_NestsLevelThenCategory()
        {
            Assert.Equal("RookBim::Level 01::Walls",
                BimExportLayerNamer.LayerPath(BimLayerScheme.ByLevelThenCategory, "Walls", "Level 01"));
        }

        [Fact]
        public void ByLevelThenCategory_MissingLevelUsesNoLevel()
        {
            Assert.Equal("RookBim::_NoLevel::Walls",
                BimExportLayerNamer.LayerPath(BimLayerScheme.ByLevelThenCategory, "Walls", null));
        }

        [Fact]
        public void MissingCategoryUsesOther()
        {
            Assert.Equal("RookBim::_Other",
                BimExportLayerNamer.LayerPath(BimLayerScheme.ByCategory, "  ", "Level 01"));
        }

        [Fact]
        public void NeverEmitsUppercaseRoot()
        {
            var path = BimExportLayerNamer.LayerPath(BimLayerScheme.ByCategory, "Walls", null);
            Assert.StartsWith("RookBim::", path);
            Assert.DoesNotContain("RookBIM", path);
        }

        [Fact]
        public void SanitizesSeparatorCollisionsInSegments()
        {
            // A category/level containing "::" must not break the path structure.
            var path = BimExportLayerNamer.LayerPath(BimLayerScheme.ByLevelThenCategory, "A::B", "L::1");
            Assert.Equal("RookBim::L__1::A__B", path);
        }
    }
}
