namespace Rook.Services.Vision.MediaImport
{
    internal static class MediaImportConstants
    {
        public const string ImportedImageKind = "imported_image";
        public const string ImportedVideoKind = "imported_video";
        public const int MaxBatchFiles = 20;
        public const int RecentJobLimit = 50;
        public const int VideoImportConcurrency = 1;
        public const long MaxImageBytes = 50L * 1024 * 1024;
        public const long MaxVideoBytes = 2L * 1024 * 1024 * 1024;
    }
}
