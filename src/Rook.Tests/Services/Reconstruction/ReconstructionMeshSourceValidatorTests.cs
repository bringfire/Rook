using System;
using System.IO;
using Rook.Artifacts;
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionMeshSourceValidatorTests : IDisposable
{
    private readonly string _root;
    private readonly ArtifactStore _store;

    public ReconstructionMeshSourceValidatorTests()
    {
        _root = Path.Combine(Path.GetTempPath(), $"rook-mesh-source-validator-{Guid.NewGuid():N}");
        _store = new ArtifactStore(_root);
    }

    public void Dispose()
    {
        if (Directory.Exists(_root))
            Directory.Delete(_root, recursive: true);
    }

    // 1) unknown package id -> invalid_source_package
    [Fact]
    public void Validate_UnknownId_ReturnsInvalidSourcePackage()
    {
        var unknownId = Guid.NewGuid();

        var result = ReconstructionMeshSourceValidator.Validate(_store, unknownId);

        Assert.False(result.Success);
        Assert.Equal("invalid_source_package", result.Failure!.Code);
        Assert.Equal(unknownId, result.SourcePackageId);
        Assert.Null(result.ModelGlbAbsolutePath);
    }

    // 2) artifact of a non-package kind -> invalid_source_package
    [Fact]
    public void Validate_WrongKind_ReturnsInvalidSourcePackage()
    {
        var artifact = _store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

        var result = ReconstructionMeshSourceValidator.Validate(_store, artifact.Id);

        Assert.False(result.Success);
        Assert.Equal("invalid_source_package", result.Failure!.Code);
        Assert.Equal(artifact.Id, result.SourcePackageId);
        Assert.Null(result.ModelGlbAbsolutePath);
    }

    // 3) package WITHOUT a model_glb file role -> missing_model_glb
    [Fact]
    public void Validate_PackageMissingModelGlbRole_ReturnsMissingModelGlb()
    {
        // A reconstruction_package but with only a model_obj — no model_glb role.
        var artifact = _store.Create(
            ReconstructionArtifactKinds.Package,
            new[] { new BlobInput(ReconstructionFileRoles.ModelObj, new byte[] { 1, 2, 3 }, "obj") });

        var result = ReconstructionMeshSourceValidator.Validate(_store, artifact.Id);

        Assert.False(result.Success);
        Assert.Equal("missing_model_glb", result.Failure!.Code);
        Assert.Equal(artifact.Id, result.SourcePackageId);
        Assert.Null(result.ModelGlbAbsolutePath);
    }

    // 4) package WITH model_glb but the blob is empty (0 bytes) -> invalid_source_package
    [Fact]
    public void Validate_PackageWithEmptyModelGlbBlob_ReturnsInvalidSourcePackage()
    {
        // Create with a non-empty blob first (ArtifactStore rejects null content,
        // but not empty byte arrays — use 1 byte then overwrite on disk with 0 bytes).
        var artifact = _store.Create(
            ReconstructionArtifactKinds.Package,
            new[] { new BlobInput(ReconstructionFileRoles.ModelGlb, new byte[] { 0x00 }, "glb") });

        // Overwrite the blob file with empty content to simulate an empty/corrupt GLB.
        var blobPath = _store.GetBlobAbsolutePath(artifact.Id, ReconstructionFileRoles.ModelGlb);
        File.WriteAllBytes(blobPath, Array.Empty<byte>());

        var result = ReconstructionMeshSourceValidator.Validate(_store, artifact.Id);

        Assert.False(result.Success);
        Assert.Equal("invalid_source_package", result.Failure!.Code);
        Assert.Equal(artifact.Id, result.SourcePackageId);
        Assert.Null(result.ModelGlbAbsolutePath);
    }

    // 5) happy path: package with non-empty model_glb -> Success, ModelGlbAbsolutePath set, Failure null
    [Fact]
    public void Validate_PackageWithNonEmptyModelGlb_ReturnsSuccess()
    {
        var artifact = _store.Create(
            ReconstructionArtifactKinds.Package,
            new[] { new BlobInput(ReconstructionFileRoles.ModelGlb, new byte[] { 1, 2, 3 }, "glb") });

        var result = ReconstructionMeshSourceValidator.Validate(_store, artifact.Id);

        Assert.True(result.Success);
        Assert.Null(result.Failure);
        Assert.Equal(artifact.Id, result.SourcePackageId);
        Assert.NotNull(result.ModelGlbAbsolutePath);
        Assert.True(File.Exists(result.ModelGlbAbsolutePath));
        Assert.EndsWith("model_glb.glb", result.ModelGlbAbsolutePath);
    }
}
