using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VideoPreparedMediaSnapshotTests
    {
        [Fact]
        public void PreparedSnapshotOwnsBytesAndOrderedDigests()
        {
            var reference = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var original = new byte[] { 97, 98, 99 }; // SHA-256("abc"), independently known
            var request = TestVideoFixtures.DefaultT2vRequest(referenceFrames: new[] { reference, reference });
            var resolved = new Dictionary<MediaRef, ResolvedMedia> { [reference] = new(original, "image/png") };
            var snapshot = VideoPreparedMediaSnapshot.Capture(request, resolved);
            original[0] = 0;
            resolved.Clear();
            snapshot.Slots[0].CopyBytes()[0] = 0;
            snapshot.ToResolvedMedia()[reference].Bytes[0] = 0;
            Assert.Equal(new[] { "reference_frames[0]", "reference_frames[1]" }, snapshot.Slots.Select(s => s.Role));
            Assert.All(snapshot.Slots, slot => {
                Assert.Equal(reference, slot.Ref);
                Assert.Equal("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", slot.Sha256);
                Assert.Equal(new byte[] { 97, 98, 99 }, slot.CopyBytes());
                using var stream = slot.OpenRead();
                Assert.False(stream.CanWrite);
                Assert.Throws<NotSupportedException>(() => stream.WriteByte(0));
                if (stream is MemoryStream memory) Assert.False(memory.TryGetBuffer(out _));
            });
        }

        [Fact]
        public void MissingResolvedInputCannotDisappear()
        {
            var request = TestVideoFixtures.DefaultT2vRequest(startFrame: MediaRef.ForArtifact(Guid.NewGuid(), "image"));
            Assert.Throws<ArgumentException>(() => VideoPreparedMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia>()));
        }
    }
}
