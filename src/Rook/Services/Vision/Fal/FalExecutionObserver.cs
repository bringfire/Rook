using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Fal
{
    /// <summary>Admission and durable write seams. Dispatch intent must finish before paid HTTP;
    /// accepted persistence must finish before a queued handle can be returned.</summary>
    public interface IFalExecutionObserver
    {
        Task<GenerationError?> BeforeUploadAsync(CancellationToken ct);
        Task<GenerationError?> BeforeDispatchAsync(CancellationToken ct);
        Task AcceptedAsync(ProviderJobHandle handle, CancellationToken ct);
    }
}
