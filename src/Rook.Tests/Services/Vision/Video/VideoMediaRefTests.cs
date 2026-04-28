using System;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class MediaRefTests
    {
        // ─── ForArtifact ─────────────────────────────────────────────

        [Fact]
        public void ForArtifact_with_nonempty_guid_constructs()
        {
            var id = Guid.NewGuid();

            var media = MediaRef.ForArtifact(id, VideoMediaRoles.Image);

            Assert.Equal(MediaRefKind.Artifact, media.Kind);
            Assert.Equal(id, media.ArtifactId);
            Assert.Null(media.Path);
            Assert.Equal(VideoMediaRoles.Image, media.Role);
        }

        [Fact]
        public void ForArtifact_with_Guid_Empty_throws()
        {
            Assert.Throws<ArgumentException>(() =>
                MediaRef.ForArtifact(Guid.Empty, VideoMediaRoles.Image));
        }

        [Fact]
        public void ForArtifact_honours_explicit_role()
        {
            var id = Guid.NewGuid();

            var media = MediaRef.ForArtifact(id, VideoMediaRoles.StartFrame);

            Assert.Equal("start_frame", media.Role);
        }

        // ─── ForPath ─────────────────────────────────────────────────

        [Fact]
        public void ForPath_with_nonempty_path_constructs()
        {
            var media = MediaRef.ForPath(@"C:\fixtures\frame.png", VideoMediaRoles.Image);

            Assert.Equal(MediaRefKind.Path, media.Kind);
            Assert.Null(media.ArtifactId);
            Assert.Equal(@"C:\fixtures\frame.png", media.Path);
            Assert.Equal(VideoMediaRoles.Image, media.Role);
        }

        [Theory]
        [InlineData("")]
        [InlineData("   ")]
        public void ForPath_with_empty_or_whitespace_throws(string path)
        {
            Assert.Throws<ArgumentException>(() =>
                MediaRef.ForPath(path, VideoMediaRoles.Image));
        }

        [Fact]
        public void ForPath_with_null_throws()
        {
            Assert.Throws<ArgumentException>(() =>
                MediaRef.ForPath(null!, VideoMediaRoles.Image));
        }

        // ─── role validation (matches ArtifactStore RolePattern) ─────

        [Theory]
        [InlineData("image")]
        [InlineData("start_frame")]
        [InlineData("end_frame")]
        [InlineData("poster")]
        [InlineData("video")]
        [InlineData("a")]
        [InlineData("0")]
        [InlineData("a-b")]
        [InlineData("a_b")]
        [InlineData("0name")]
        public void Valid_role_strings_accepted(string role)
        {
            var id = Guid.NewGuid();

            var media = MediaRef.ForArtifact(id, role);

            Assert.Equal(role, media.Role);
        }

        [Theory]
        [InlineData("Image")]              // uppercase rejected by ArtifactStore pattern
        [InlineData("-leading-hyphen")]    // leading non-alphanumeric
        [InlineData("_leading_underscore")]// leading non-alphanumeric
        [InlineData("has space")]          // whitespace not allowed
        [InlineData("has.dot")]            // dot not allowed
        public void Invalid_role_strings_rejected(string role)
        {
            var id = Guid.NewGuid();

            Assert.Throws<ArgumentException>(() =>
                MediaRef.ForArtifact(id, role));
        }

        [Fact]
        public void Empty_role_string_rejected()
        {
            var id = Guid.NewGuid();

            Assert.Throws<ArgumentException>(() =>
                MediaRef.ForArtifact(id, ""));
        }
    }
}
