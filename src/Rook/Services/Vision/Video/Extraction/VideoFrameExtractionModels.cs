using System;

namespace Rook.Services.Vision.Video.Extraction
{
    internal enum VideoFrameSelectorKind
    {
        First,
        Last,
        FrameIndex,
    }

    internal readonly struct VideoFrameSelector
    {
        private VideoFrameSelector(VideoFrameSelectorKind kind, long? frameIndexValue)
        {
            Kind = kind;
            FrameIndexValue = frameIndexValue;
        }

        public VideoFrameSelectorKind Kind { get; }
        public long? FrameIndexValue { get; }

        public static VideoFrameSelector First => new VideoFrameSelector(VideoFrameSelectorKind.First, 0);
        public static VideoFrameSelector Last => new VideoFrameSelector(VideoFrameSelectorKind.Last, null);

        public static VideoFrameSelector FrameIndex(long index)
        {
            if (index < 0)
                throw new ArgumentOutOfRangeException(nameof(index), "Frame index must be zero or greater.");

            return new VideoFrameSelector(VideoFrameSelectorKind.FrameIndex, index);
        }

        internal VideoFrameSelector NormalizeFirst()
            => Kind == VideoFrameSelectorKind.First ? FrameIndex(0) : this;
    }

    internal enum FfmpegVideoFrameExtractionError
    {
        InputMissing,
        FfmpegMissing,
        ProcessStartFailed,
        ProcessFailed,
        TimedOut,
        OutputMissing,
        InvalidOutputImage,
        Cancelled,
    }

    internal sealed class FfmpegVideoFrameExtractionResult
    {
        private const int MaxDiagnosticLength = 2048;

        private FfmpegVideoFrameExtractionResult(
            bool success,
            VideoFrameSelector selector,
            string commandLine,
            int? exitCode,
            string stderr,
            string outputPath,
            int? width,
            int? height,
            TimeSpan elapsed,
            FfmpegVideoFrameExtractionError? errorCode,
            string message)
        {
            Success = success;
            Selector = selector;
            CommandLine = commandLine ?? string.Empty;
            ExitCode = exitCode;
            Stderr = Truncate(stderr ?? string.Empty);
            OutputPath = outputPath ?? string.Empty;
            Width = width;
            Height = height;
            Elapsed = elapsed;
            ErrorCode = errorCode;
            Message = message ?? string.Empty;
        }

        public bool Success { get; }
        public VideoFrameSelector Selector { get; }
        public string CommandLine { get; }
        public int? ExitCode { get; }
        public string Stderr { get; }
        public string OutputPath { get; }
        public int? Width { get; }
        public int? Height { get; }
        public TimeSpan Elapsed { get; }
        public FfmpegVideoFrameExtractionError? ErrorCode { get; }
        public string Message { get; }

        public static FfmpegVideoFrameExtractionResult Completed(
            VideoFrameSelector selector,
            string commandLine,
            int exitCode,
            string stderr,
            string outputPath,
            int width,
            int height,
            TimeSpan elapsed) =>
            new FfmpegVideoFrameExtractionResult(
                true,
                selector,
                commandLine,
                exitCode,
                stderr,
                outputPath,
                width,
                height,
                elapsed,
                null,
                "Extracted video frame.");

        public static FfmpegVideoFrameExtractionResult Failed(
            VideoFrameSelector selector,
            string commandLine,
            int? exitCode,
            string stderr,
            string outputPath,
            TimeSpan elapsed,
            FfmpegVideoFrameExtractionError errorCode,
            string message) =>
            new FfmpegVideoFrameExtractionResult(
                false,
                selector,
                commandLine,
                exitCode,
                stderr,
                outputPath,
                null,
                null,
                elapsed,
                errorCode,
                message);

        private static string Truncate(string value)
            => value.Length <= MaxDiagnosticLength
                ? value
                : value.Substring(0, MaxDiagnosticLength);
    }
}
