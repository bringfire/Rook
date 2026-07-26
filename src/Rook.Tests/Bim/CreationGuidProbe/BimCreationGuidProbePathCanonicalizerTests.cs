using System;
using System.Text;
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim.CreationGuidProbe
{
    public sealed class BimCreationGuidProbePathCanonicalizerTests
    {
        [Theory]
        [InlineData(@"C:\", @"C:\", "433a5c")]
        [InlineData(@"c:/Models/../A.rvt", @"C:\A.RVT", "433a5c412e525654")]
        [InlineData(@"\\server\share", @"\\SERVER\SHARE", "5c5c5345525645525c5348415245")]
        [InlineData(@"\\server\share\", @"\\SERVER\SHARE", "5c5c5345525645525c5348415245")]
        [InlineData(@"\\server\share\folder\..\", @"\\SERVER\SHARE", "5c5c5345525645525c5348415245")]
        public void TryCanonicalize_ProducesApprovedCanonicalTextAndUtf8Bytes(
            string input, string expectedCanonical, string expectedHex)
        {
            // Break caught: changing the canonical byte contract used for equality aliasing.
            Assert.True(BimCreationGuidProbePathCanonicalizer.TryCanonicalize(
                input, out var canonical));
            Assert.Equal(expectedCanonical, canonical);
            Assert.Equal(expectedHex, ToHex(Encoding.UTF8.GetBytes(canonical)));
        }

        [Theory]
        [InlineData("")]
        [InlineData("   ")]
        [InlineData("C:\\bad\0name.rvt")]
        [InlineData("relative\\model.rvt")]
        [InlineData("\\root-relative.rvt")]
        [InlineData("C:model.rvt")]
        [InlineData("https://example.test/model.rvt")]
        [InlineData("\\\\server")]
        [InlineData("\\\\server\\")]
        [InlineData("\\\\?\\C:\\model.rvt")]
        [InlineData("\\\\.\\C:\\model.rvt")]
        [InlineData("\\??\\C:\\model.rvt")]
        public void TryCanonicalize_RejectsUnsafeOrNonAbsoluteInputs(string input)
        {
            // Break caught: accepting a path outside the explicitly supported Windows forms.
            Assert.False(BimCreationGuidProbePathCanonicalizer.TryCanonicalize(
                input, out var canonical));
            Assert.Equal(string.Empty, canonical);
        }

        private static string ToHex(byte[] bytes)
        {
            var result = new StringBuilder(bytes.Length * 2);
            foreach (var value in bytes)
            {
                result.Append(value.ToString("x2"));
            }

            return result.ToString();
        }
    }
}
