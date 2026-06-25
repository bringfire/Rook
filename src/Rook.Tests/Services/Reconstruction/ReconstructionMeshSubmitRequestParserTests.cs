using System;
using System.Text.Json.Nodes;
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionMeshSubmitRequestParserTests
{
    private const string Pkg = "11111111-1111-1111-1111-111111111111";

    [Fact]
    public void Parse_ValidBody_PopulatesRequest()
    {
        var result = ReconstructionMeshSubmitRequestParser.Parse(
            $"{{\"source_package_id\":\"{Pkg}\",\"model_id\":\"fal-ai/hunyuan-3d/v3.1/smart-topology\"," +
            "\"options\":{\"face_level\":\"high\"},\"allow_experimental_model\":true}");

        Assert.True(result.Success, result.Failure?.Message);
        Assert.Equal(Guid.Parse(Pkg), result.Request!.SourcePackageId);
        Assert.Equal("fal-ai/hunyuan-3d/v3.1/smart-topology", result.Request!.ModelId);
        Assert.True(result.Request!.AllowExperimentalModel);
        Assert.Equal("high", result.Request!.Options["face_level"]!.GetValue<string>());
    }

    [Fact]
    public void Parse_MissingSourcePackageId_Fails()
    {
        var result = ReconstructionMeshSubmitRequestParser.Parse("{\"model_id\":\"m\"}");
        Assert.False(result.Success);
        Assert.Equal("invalid_request", result.Failure!.Code);
        Assert.Equal("source_package_id", result.Failure!.Field);
    }

    [Fact]
    public void Parse_MissingModelId_Fails()
    {
        var result = ReconstructionMeshSubmitRequestParser.Parse($"{{\"source_package_id\":\"{Pkg}\"}}");
        Assert.False(result.Success);
        Assert.Equal("model_id", result.Failure!.Field);
    }

    [Fact]
    public void Parse_OptionsNotObject_Fails()
    {
        var result = ReconstructionMeshSubmitRequestParser.Parse(
            $"{{\"source_package_id\":\"{Pkg}\",\"model_id\":\"m\",\"options\":[1,2]}}");
        Assert.False(result.Success);
        Assert.Equal("invalid_request", result.Failure!.Code);
        Assert.Equal("options", result.Failure!.Field);
    }

    [Fact]
    public void Parse_AllowExperimentalNotBool_Fails()
    {
        var result = ReconstructionMeshSubmitRequestParser.Parse(
            $"{{\"source_package_id\":\"{Pkg}\",\"model_id\":\"m\",\"allow_experimental_model\":\"yes\"}}");
        Assert.False(result.Success);
        Assert.Equal("allow_experimental_model", result.Failure!.Field);
    }
}
