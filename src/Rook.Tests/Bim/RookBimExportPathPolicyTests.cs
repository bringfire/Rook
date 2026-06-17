using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class RookBimExportPathPolicyTests
    {
        [Theory]
        [InlineData(null)]
        [InlineData("")]
        [InlineData("relative/dir")]
        [InlineData("C:fixtures")]   // drive-relative — Path.IsPathRooted returns true, but it is NOT absolute
        [InlineData("C:")]
        [InlineData(@"\\server\share\fixtures")]  // UNC — ambiguous local target
        public void ValidateRequestShape_RejectsNonAbsoluteOrNonLocalDirectory(string? dir)
        {
            var result = BimExportPathPolicy.ValidateRequestShape(
                new BimExportOutput { Directory = dir, Name = "walls" });
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.OutputPathInvalid, result.ErrorCode);
        }

        [Theory]
        [InlineData(null)]
        [InlineData("walls.")]
        [InlineData("walls/foo")]
        [InlineData("walls\\foo")]
        [InlineData("..walls")]
        [InlineData("wall:s")]
        [InlineData("")]
        [InlineData("CON")]       // reserved device name
        [InlineData("nul")]       // case-insensitive
        [InlineData("COM1")]
        [InlineData("LPT1")]
        [InlineData("PRN")]
        [InlineData("AUX")]
        [InlineData("CON.json")]  // reserved base name with extension
        public void ValidateRequestShape_RejectsUnsafeName(string? name)
        {
            var result = BimExportPathPolicy.ValidateRequestShape(
                new BimExportOutput { Directory = @"C:\fixtures", Name = name });
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.OutputPathInvalid, result.ErrorCode);
        }

        [Theory]
        [InlineData("meters")]
        [InlineData("Meters")]      // case-insensitive
        [InlineData("millimeters")]
        [InlineData("centimeters")]
        [InlineData("feet")]
        [InlineData("inches")]
        public void ValidateRequestShape_AcceptsSupportedUnits(string units)
        {
            var result = BimExportPathPolicy.ValidateRequestShape(
                new BimExportOutput { Directory = @"C:\fixtures", Name = "walls", Units = units });
            Assert.True(result.Success);
        }

        [Theory]
        [InlineData("cubits")]
        [InlineData("")]
        [InlineData("mm")]          // aliases are NOT part of the public unit contract
        public void ValidateRequestShape_RejectsUnsupportedUnits(string units)
        {
            var result = BimExportPathPolicy.ValidateRequestShape(
                new BimExportOutput { Directory = @"C:\fixtures", Name = "walls", Units = units });
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.OutputPathInvalid, result.ErrorCode);
        }

        [Fact]
        public void ValidateRequestShape_AcceptsAbsoluteDirAndSafeName()
        {
            var result = BimExportPathPolicy.ValidateRequestShape(
                new BimExportOutput { Directory = @"C:\fixtures", Name = "walls-01_v2" });
            Assert.True(result.Success);
        }

        [Fact]
        public void ResolveBundlePaths_BuildsDeterministicPrefixInsideDirectory()
        {
            var paths = BimExportPathPolicy.ResolveBundlePaths(@"C:\fixtures", "walls");
            Assert.EndsWith("walls.3dm", paths.Model3dm);
            Assert.EndsWith("walls.sidecar.json", paths.Sidecar);
            Assert.EndsWith("walls.validation.json", paths.Validation);
            Assert.StartsWith(@"C:\fixtures\", paths.Model3dm);
        }

        [Fact]
        public void EscapesIntendedDirectory_TrueWhenPathOutside()
        {
            Assert.True(BimExportPathPolicy.EscapesIntendedDirectory(@"C:\other\walls.3dm", @"C:\fixtures"));
            Assert.False(BimExportPathPolicy.EscapesIntendedDirectory(@"C:\fixtures\walls.3dm", @"C:\fixtures"));

            // prefix-escape: a sibling dir sharing a name prefix must NOT count as inside
            Assert.True(BimExportPathPolicy.EscapesIntendedDirectory(@"C:\fixtures-evil\walls.3dm", @"C:\fixtures"));
            // case-insensitive: same dir, different case, is inside
            Assert.False(BimExportPathPolicy.EscapesIntendedDirectory(@"C:\FIXTURES\walls.3dm", @"C:\fixtures"));
            // ..-traversal normalizes outside the intended dir
            Assert.True(BimExportPathPolicy.EscapesIntendedDirectory(@"C:\fixtures\..\other\walls.3dm", @"C:\fixtures"));
        }
    }
}
