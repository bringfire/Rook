using System;
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionSubmitRequestParserTests
{
    [Fact]
    public void Parse_RejectsLocalPath()
    {
        var result = ReconstructionSubmitRequestParser.Parse("""
        {"path":"C:/tmp/source.png","model_id":"fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d"}
        """);

        Assert.False(result.Success);
        Assert.Equal("invalid_request", result.Failure!.Code);
        Assert.Equal("source_artifact_id", result.Failure.Field);
    }

    [Fact]
    public void Parse_RejectsManualRemoveBackgroundStageUntilPreprocessingExecutes()
    {
        var sourceId = Guid.NewGuid();
        var result = ReconstructionSubmitRequestParser.Parse(
            "{" +
            $"\"source_artifact_id\":\"{sourceId}\"," +
            "\"source_role\":\"image\"," +
            "\"model_id\":\"fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d\"," +
            "\"preprocessing_chain\":[{" +
            "\"role\":\"remove_background\"," +
            "\"model_id\":\"fal-ai/birefnet/v2\"," +
            "\"input_role\":\"image\"," +
            "\"output_role\":\"preprocessed_image\"," +
            "\"options\":{}" +
            "}]," +
            "\"options\":{\"enable_pbr\":true,\"enable_geometry\":false}" +
            "}");

        Assert.False(result.Success);
        Assert.Equal("preprocessing_chain", result.Failure!.Field);
        Assert.Contains("not implemented", result.Failure.Message);
    }

    [Fact]
    public void Parse_RejectsTwoPreprocessingStages()
    {
        var sourceId = Guid.NewGuid();
        var result = ReconstructionSubmitRequestParser.Parse(
            "{" +
            $"\"source_artifact_id\":\"{sourceId}\"," +
            "\"model_id\":\"fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d\"," +
            "\"preprocessing_chain\":[" +
            "{\"role\":\"remove_background\",\"model_id\":\"fal-ai/birefnet/v2\"}," +
            "{\"role\":\"remove_background\",\"model_id\":\"fal-ai/birefnet/v2\"}" +
            "]" +
            "}");

        Assert.False(result.Success);
        Assert.Equal("preprocessing_chain", result.Failure!.Field);
    }

    [Fact]
    public void Parse_DefaultsSourceRoleOptionsAndEstimate()
    {
        var sourceId = Guid.NewGuid();
        var result = ReconstructionSubmitRequestParser.Parse(
            "{" +
            $"\"source_artifact_id\":\"{sourceId}\"," +
            "\"model_id\":\"fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d\"" +
            "}");

        Assert.True(result.Success);
        Assert.Equal("image", result.Request!.SourceRole);
        Assert.Empty(result.Request.PreprocessingChain);
        Assert.Empty(result.Request.Options);
        Assert.False(result.Request.EstimateRequested);
    }
}
