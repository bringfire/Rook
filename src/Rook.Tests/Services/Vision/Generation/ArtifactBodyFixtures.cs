using System;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    /// <summary>
    /// URL-vs-inline artifact-body discrimination tests. The closed
    /// union <see cref="ArtifactBody"/> (abstract class + sealed leaves)
    /// enforces URL-xor-inline at the type level: a
    /// <see cref="ResultArtifact"/> carries exactly one of
    /// <see cref="RemoteArtifactBody"/> or
    /// <see cref="InlineArtifactBody"/>, never both.
    /// </summary>
    public class ArtifactBodyFixtures
    {
        [Fact]
        public void RemoteArtifactBody_constructs_with_uri()
        {
            var body = new RemoteArtifactBody(
                new Uri("https://v3b.fal.media/files/abc/output.png"));

            Assert.Equal("https://v3b.fal.media/files/abc/output.png", body.Url.ToString());
            Assert.Null(body.SignedUrlTtl);
        }

        [Fact]
        public void RemoteArtifactBody_carries_optional_signed_url_ttl()
        {
            var body = new RemoteArtifactBody(
                new Uri("https://v3b.fal.media/files/abc/output.png"),
                SignedUrlTtl: TimeSpan.FromHours(24));

            Assert.Equal(TimeSpan.FromHours(24), body.SignedUrlTtl);
        }

        [Fact]
        public void RemoteArtifactBody_rejects_null_url()
        {
            Assert.Throws<ArgumentNullException>(() =>
                new RemoteArtifactBody(null!));
        }

        [Fact]
        public void InlineArtifactBody_constructs_with_bytes()
        {
            var bytes = new byte[] { 0x89, 0x50, 0x4E, 0x47 };
            var body = new InlineArtifactBody(bytes);

            Assert.Same(bytes, body.Bytes);
        }

        [Fact]
        public void InlineArtifactBody_rejects_null_bytes()
        {
            Assert.Throws<ArgumentNullException>(() =>
                new InlineArtifactBody(null!));
        }

        [Fact]
        public void InlineArtifactBody_rejects_empty_bytes()
        {
            Assert.Throws<ArgumentException>(() =>
                new InlineArtifactBody(Array.Empty<byte>()));
        }

        [Fact]
        public void Pattern_match_discriminates_remote_vs_inline()
        {
            ArtifactBody remote = new RemoteArtifactBody(new Uri("https://example.com/x"));
            ArtifactBody inline = new InlineArtifactBody(new byte[] { 0x01 });

            Assert.Equal("remote", Describe(remote));
            Assert.Equal("inline", Describe(inline));

            static string Describe(ArtifactBody body) => body switch
            {
                RemoteArtifactBody => "remote",
                InlineArtifactBody => "inline",
                _ => throw new InvalidOperationException(
                    "ArtifactBody is sealed-record union — new subtype must be handled here."),
            };
        }
    }
}
