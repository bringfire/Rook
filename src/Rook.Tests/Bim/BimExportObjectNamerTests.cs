using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class BimExportObjectNamerTests
    {
        [Fact]
        public void None_ReturnsNull()
        {
            Assert.Null(BimExportObjectNamer.ObjectName(BimNameScheme.None, "Walls", "Generic 200mm", 1, "x"));
        }

        [Fact]
        public void ReadableWithId_FormatsCategoryTypeAndId()
        {
            Assert.Equal("Walls - Generic 200mm [350123]",
                BimExportObjectNamer.ObjectName(BimNameScheme.ReadableWithId, "Walls", "Generic 200mm", 350123, "x"));
        }

        [Fact]
        public void Readable_OmitsId()
        {
            Assert.Equal("Walls - Generic 200mm",
                BimExportObjectNamer.ObjectName(BimNameScheme.Readable, "Walls", "Generic 200mm", 350123, "x"));
        }

        [Fact]
        public void TypeOnly_UsesType()
        {
            Assert.Equal("Generic 200mm",
                BimExportObjectNamer.ObjectName(BimNameScheme.TypeOnly, "Walls", "Generic 200mm", 1, "x"));
        }

        [Fact]
        public void RevitName_UsesRevitName()
        {
            Assert.Equal("My Wall",
                BimExportObjectNamer.ObjectName(BimNameScheme.RevitName, "Walls", "Generic 200mm", 1, "My Wall"));
        }

        [Fact]
        public void ReadableWithId_FallsBackToCategoryWhenTypeMissing()
        {
            Assert.Equal("Walls [42]",
                BimExportObjectNamer.ObjectName(BimNameScheme.ReadableWithId, "Walls", null, 42, null));
        }

        [Fact]
        public void ReadableWithId_FallsBackToRevitElementWhenAllMissing()
        {
            Assert.Equal("Revit Element [42]",
                BimExportObjectNamer.ObjectName(BimNameScheme.ReadableWithId, null, null, 42, null));
        }

        [Fact]
        public void ReadableWithId_OmitsSuffixWhenNoId()
        {
            Assert.Equal("Walls - Generic 200mm",
                BimExportObjectNamer.ObjectName(BimNameScheme.ReadableWithId, "Walls", "Generic 200mm", null, null));
        }
    }
}
