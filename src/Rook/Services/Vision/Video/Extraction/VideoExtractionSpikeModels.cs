using System;

namespace Rook.Services.Vision.Video.Extraction
{
    internal enum FfmpegBinaryResolutionSource
    {
        Bundled,
        ConfiguredPath,
        PathLookup,
    }

    internal enum FfmpegBinaryResolutionError
    {
        ConfiguredPathMissing,
        NotFound,
    }

    internal sealed class FfmpegBinaryResolution
    {
        private FfmpegBinaryResolution(
            bool success,
            string? path,
            FfmpegBinaryResolutionSource? source,
            FfmpegBinaryResolutionError? errorCode,
            string message)
        {
            Success = success;
            Path = path;
            Source = source;
            ErrorCode = errorCode;
            Message = message;
        }

        public bool Success { get; }
        public string? Path { get; }
        public FfmpegBinaryResolutionSource? Source { get; }
        public FfmpegBinaryResolutionError? ErrorCode { get; }
        public string Message { get; }

        public static FfmpegBinaryResolution Found(
            string path,
            FfmpegBinaryResolutionSource source) =>
            new FfmpegBinaryResolution(
                success: true,
                path: path,
                source: source,
                errorCode: null,
                message: $"Resolved ffmpeg.exe from {source}.");

        public static FfmpegBinaryResolution Failed(
            FfmpegBinaryResolutionError errorCode,
            string message) =>
            new FfmpegBinaryResolution(
                success: false,
                path: null,
                source: null,
                errorCode: errorCode,
                message: message);
    }

    internal enum FfmpegPosterExtractionError
    {
        InputMissing,
        BinaryMissing,
        ProcessStartFailed,
        ProcessFailed,
        TimedOut,
        OutputMissing,
        InvalidOutputImage,
    }

    internal sealed class FfmpegPosterExtractionResult
    {
        private FfmpegPosterExtractionResult(
            bool success,
            string commandLine,
            int? exitCode,
            string stderr,
            string outputPath,
            int? width,
            int? height,
            TimeSpan elapsed,
            FfmpegPosterExtractionError? errorCode,
            string message)
        {
            Success = success;
            CommandLine = commandLine;
            ExitCode = exitCode;
            Stderr = stderr;
            OutputPath = outputPath;
            Width = width;
            Height = height;
            Elapsed = elapsed;
            ErrorCode = errorCode;
            Message = message;
        }

        public bool Success { get; }
        public string CommandLine { get; }
        public int? ExitCode { get; }
        public string Stderr { get; }
        public string OutputPath { get; }
        public int? Width { get; }
        public int? Height { get; }
        public TimeSpan Elapsed { get; }
        public FfmpegPosterExtractionError? ErrorCode { get; }
        public string Message { get; }

        public static FfmpegPosterExtractionResult Completed(
            string commandLine,
            int exitCode,
            string stderr,
            string outputPath,
            int width,
            int height,
            TimeSpan elapsed) =>
            new FfmpegPosterExtractionResult(
                true,
                commandLine,
                exitCode,
                stderr,
                outputPath,
                width,
                height,
                elapsed,
                null,
                "Extracted poster candidate frame.");

        public static FfmpegPosterExtractionResult Failed(
            string commandLine,
            int? exitCode,
            string stderr,
            string outputPath,
            TimeSpan elapsed,
            FfmpegPosterExtractionError errorCode,
            string message) =>
            new FfmpegPosterExtractionResult(
                false,
                commandLine,
                exitCode,
                stderr,
                outputPath,
                null,
                null,
                elapsed,
                errorCode,
                message);
    }

    internal sealed class ProcessRunResult
    {
        public ProcessRunResult(int? exitCode, string standardError, bool timedOut, TimeSpan elapsed)
        {
            ExitCode = exitCode;
            StandardError = standardError ?? string.Empty;
            TimedOut = timedOut;
            Elapsed = elapsed;
        }

        public int? ExitCode { get; }
        public string StandardError { get; }
        public bool TimedOut { get; }
        public TimeSpan Elapsed { get; }
    }
}
