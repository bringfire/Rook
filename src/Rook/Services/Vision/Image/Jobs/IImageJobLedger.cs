namespace Rook.Services.Vision.Image.Jobs
{
    public interface IImageJobLedger
    {
        void Append(ImageJobLedgerRecord record);

        ImageJobLedgerReadResult ReadAll();
    }
}
