using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Vision.MediaImport
{
    public interface IMediaImportProcessor
    {
        Task<MediaImportProcessResult> ProcessAsync(string path, CancellationToken ct);
    }
}
