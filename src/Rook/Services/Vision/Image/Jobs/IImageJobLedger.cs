using System.Threading;

namespace Rook.Services.Vision.Image.Jobs
{
    public interface IImageJobLedger
    {
        void Append(ImageJobLedgerRecord record);

        ImageJobLedgerReadResult ReadAll();
    }

    /// <summary>Cancellation bounds admission to ledger I/O, never abandons admitted I/O.</summary>
    public interface ICancellationAwareImageJobLedger : IImageJobLedger
    {
        void Append(ImageJobLedgerRecord record, CancellationToken ct);
        ImageJobLedgerReadResult ReadAll(CancellationToken ct);
    }
}
