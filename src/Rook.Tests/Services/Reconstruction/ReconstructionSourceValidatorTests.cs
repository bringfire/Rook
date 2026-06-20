using System;
using System.IO;
using Rook.Artifacts;
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionSourceValidatorTests : IDisposable
{
    private readonly string _root;
    private readonly ArtifactStore _store;

    public ReconstructionSourceValidatorTests()
    {
        _root = Path.Combine(Path.GetTempPath(), $"rook-reconstruction-source-{Guid.NewGuid():N}");
        _store = new ArtifactStore(_root);
    }

    public void Dispose()
    {
        if (Directory.Exists(_root))
            Directory.Delete(_root, recursive: true);
    }

    [Fact]
    public void Validate_AllowsGeneratedImageWithImageRole()
    {
        var artifact = _store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

        var result = ReconstructionSourceValidator.Validate(_store, artifact, "image");

        Assert.True(result.Success);
        Assert.NotNull(result.AbsolutePath);
        Assert.Single(result.Warnings);
        Assert.Equal("source_dimensions_unreadable", result.Warnings[0].Code);
    }

    [Fact]
    public void Validate_RejectsReconstructionPackage()
    {
        var artifact = _store.Create(
            "reconstruction_package",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

        var result = ReconstructionSourceValidator.Validate(_store, artifact, "image");

        Assert.False(result.Success);
        Assert.Equal("source_artifact_id", result.Failure!.Field);
    }

    [Fact]
    public void Validate_RejectsMissingRole()
    {
        var artifact = _store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

        var result = ReconstructionSourceValidator.Validate(_store, artifact, "thumbnail");

        Assert.False(result.Success);
        Assert.Equal("source_role", result.Failure!.Field);
        Assert.Equal("invalid_source_role", result.Failure.Code);
    }

    [Fact]
    public void Validate_RejectsUnsupportedExtension()
    {
        var artifact = _store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "gif") });

        var result = ReconstructionSourceValidator.Validate(_store, artifact, "image");

        Assert.False(result.Success);
        Assert.Equal("invalid_source_file", result.Failure!.Code);
    }
}
