using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionErrorMappingTests
{
    [Fact]
    public void MissingCredentialFailure_IsNonRetryableTypedFailureWithRemediation()
    {
        var failure = ReconstructionErrorMapping.MissingCredentialFailure();

        Assert.Equal("missing_credential", failure.Code);
        Assert.False(failure.Retryable);
        Assert.Null(failure.Field);
        Assert.Contains("fal API key", failure.Message);
        Assert.Contains("Vision settings", failure.Message);
    }
}
