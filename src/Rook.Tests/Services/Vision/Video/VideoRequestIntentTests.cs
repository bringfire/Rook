using System;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VideoRequestIntentTests
    {
        [Fact]
        public void OmittedPeopleControlRetainsProvenance()
        {
            var source = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var supplied = new JsonObject();
            var intent = VideoRequestIntent.Normalize(TestVideoFixtures.DefaultT2vRequest(mode: VideoMode.I2V, startFrame: source), supplied);
            supplied["person_generation"] = "allow_all";
            Assert.False(intent.PersonGenerationSupplied);
            Assert.Empty(intent.SuppliedOptions);
            Assert.Equal(PersonGenerationPolicy.AllowAdult, ((VeoOptions)intent.Request.Options).PersonGeneration);
            Assert.Equal(PersonGenerationPolicy.AllowAll, ((VeoOptions)VideoRequestIntent.Normalize(TestVideoFixtures.DefaultT2vRequest(), new JsonObject()).Request.Options).PersonGeneration);
        }

        [Fact]
        public void ExplicitDefaultBlocksOnlyFallback()
        {
            var intent = VideoRequestIntent.Normalize(TestVideoFixtures.DefaultT2vRequest(), new JsonObject { ["person_generation"] = "allow_all" });
            Assert.True(intent.PersonGenerationSupplied);
            Assert.Equal(PersonGenerationPolicy.AllowAll, ((VeoOptions)intent.Request.Options).PersonGeneration);
            Assert.True(new VeoOptionsCodec().Validate(intent.Request, intent.Request.Options, VeoCapabilities.Models[intent.Request.Model].Capability).Success);
        }
    }
}
