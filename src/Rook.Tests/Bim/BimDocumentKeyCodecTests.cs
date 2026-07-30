using System;
using System.Linq;
using System.Text;
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public sealed class BimDocumentKeyCodecTests
    {
        [Theory]
        [InlineData(@"C:\", @"C:\", "433a5c")]
        [InlineData(@"c:/Models/../A.rvt", @"C:\A.RVT", "433a5c412e525654")]
        [InlineData(@"\\server\share", @"\\SERVER\SHARE", "5c5c5345525645525c5348415245")]
        [InlineData(@"\\server\share\", @"\\SERVER\SHARE", "5c5c5345525645525c5348415245")]
        [InlineData(@"\\server\share\folder\..\", @"\\SERVER\SHARE", "5c5c5345525645525c5348415245")]
        public void TryCanonicalizeWindowsPath_ProducesNormativeTextAndBytes(
            string input, string expected, string expectedHex)
        {
            Assert.True(BimDocumentKeyCodec.TryCanonicalizeWindowsPath(input, out var actual));
            Assert.Equal(expected, actual);
            Assert.Equal(expectedHex, Hex(new UTF8Encoding(false, true).GetBytes(actual)));
        }

        [Theory]
        [InlineData(null)]
        [InlineData("")]
        [InlineData("   ")]
        [InlineData("C:\\bad\0path")]
        [InlineData("relative\\path.rvt")]
        [InlineData("\\root-relative.rvt")]
        [InlineData("C:drive-relative.rvt")]
        [InlineData("https://server/model.rvt")]
        [InlineData("\\\\server")]
        [InlineData("\\\\server\\")]
        [InlineData("\\\\?\\C:\\model.rvt")]
        [InlineData("\\\\.\\C:\\model.rvt")]
        [InlineData("\\??\\C:\\model.rvt")]
        public void TryCanonicalizeWindowsPath_RejectsUnsafeOrNonAbsoluteInput(string? input)
        {
            Assert.False(BimDocumentKeyCodec.TryCanonicalizeWindowsPath(input, out var canonical));
            Assert.Equal(string.Empty, canonical);
        }

        [Fact]
        public void TryCreate_ProducesPinnedFileAndSavedProjectKeys()
        {
            var guid = Guid.ParseExact("00112233-4455-6677-8899-aabbccddeeff", "D");

            Assert.True(BimDocumentKeyCodec.TryCreate(
                BimDocumentKeySource.RevitCreationGuidCentralPathV1, guid, @"C:\Models\A.rvt", out var fileKey));
            Assert.True(BimDocumentKeyCodec.TryCreate(
                BimDocumentKeySource.RevitCreationGuidDocumentPathV1, guid, @"\\server\share\A.rvt", out var savedKey));

            Assert.Equal("file-document-v1:50250fd46d4c96e14f57ff283d6fd21965d8525a34d638e5070eaf60df13a0ac", fileKey);
            Assert.Equal("saved-document-v1:f8068f0ccb7e520b278de67a1b167f880ecbc7ec9ff4ddba603407643fc3e250", savedKey);
            Assert.DoesNotContain(@"C:\MODELS\A.RVT", fileKey);
            Assert.DoesNotContain(guid.ToString("D"), fileKey, StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void BimDocumentKeySource_HasOnlyApprovedNamesInOrder()
        {
            Assert.Equal(
                new[] { "Unavailable", "RevitCreationGuidCentralPathV1", "RevitCreationGuidDocumentPathV1" },
                Enum.GetNames(typeof(BimDocumentKeySource)));
        }

        [Fact]
        public void TryCreate_RejectsEmptyGuidAndUnavailableSource()
        {
            Assert.False(BimDocumentKeyCodec.TryCreate(
                BimDocumentKeySource.RevitCreationGuidCentralPathV1, Guid.Empty, @"C:\A.rvt", out var emptyGuidKey));
            Assert.Equal(string.Empty, emptyGuidKey);
            Assert.False(BimDocumentKeyCodec.TryCreate(BimDocumentKeySource.Unavailable, Guid.NewGuid(), @"C:\A.rvt", out var unavailableKey));
            Assert.Equal(string.Empty, unavailableKey);
            Assert.False(BimDocumentKeyCodec.IsValid(BimDocumentKeySource.Unavailable, "file-document-v1:50250fd46d4c96e14f57ff283d6fd21965d8525a34d638e5070eaf60df13a0ac"));
        }

        [Theory]
        [InlineData(BimDocumentKeySource.RevitCreationGuidCentralPathV1, "saved-document-v1:f8068f0ccb7e520b278de67a1b167f880ecbc7ec9ff4ddba603407643fc3e250")]
        [InlineData(BimDocumentKeySource.RevitCreationGuidDocumentPathV1, "file-document-v1:50250fd46d4c96e14f57ff283d6fd21965d8525a34d638e5070eaf60df13a0ac")]
        [InlineData(BimDocumentKeySource.RevitCreationGuidCentralPathV1, "file-document-v1:50250FD46D4C96E14F57FF283D6FD21965D8525A34D638E5070EAF60DF13A0AC")]
        [InlineData(BimDocumentKeySource.RevitCreationGuidCentralPathV1, "file-document-v1:50250fd46d4c96e14f57ff283d6fd21965d8525a34d638e5070eaf60df13a")]
        [InlineData(BimDocumentKeySource.RevitCreationGuidCentralPathV1, "file-document-v1:50250fd46d4c96e14f57ff283d6fd21965d8525a34d638e5070eaf60df13a0acc")]
        [InlineData(BimDocumentKeySource.RevitCreationGuidCentralPathV1, "file-document-v1:50250fd46d4c96e14f57ff283d6fd21965d8525a34d638e5070eaf60df13a0ag")]
        [InlineData(BimDocumentKeySource.RevitCreationGuidCentralPathV1, "file-document-v150250fd46d4c96e14f57ff283d6fd21965d8525a34d638e5070eaf60df13a0ac")]
        [InlineData(BimDocumentKeySource.RevitCreationGuidCentralPathV1, "server-document-v1:50250fd46d4c96e14f57ff283d6fd21965d8525a34d638e5070eaf60df13a0ac")]
        public void IsValid_RejectsSourceIncoherentOrMalformedKeys(BimDocumentKeySource source, string key)
        {
            Assert.False(BimDocumentKeyCodec.IsValid(source, key));
        }

        [Fact]
        public void IsValid_AcceptsOnlyApprovedKeyKinds()
        {
            Assert.True(BimDocumentKeyCodec.IsValid(
                BimDocumentKeySource.RevitCreationGuidCentralPathV1,
                "file-document-v1:50250fd46d4c96e14f57ff283d6fd21965d8525a34d638e5070eaf60df13a0ac"));
            Assert.True(BimDocumentKeyCodec.IsValid(
                BimDocumentKeySource.RevitCreationGuidDocumentPathV1,
                "saved-document-v1:f8068f0ccb7e520b278de67a1b167f880ecbc7ec9ff4ddba603407643fc3e250"));
        }

        private static string Hex(byte[] bytes)
        {
            return string.Concat(bytes.Select(value => value.ToString("x2")));
        }
    }
}
