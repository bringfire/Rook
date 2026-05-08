using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Video.Fal
{
    internal sealed class FalSourceFramePolicy
    {
        public FalSourceFramePolicy(
            string ModelLabel,
            string FileNamePrefix,
            IReadOnlyList<VideoMode> AllowedModes,
            long MaxSourceFrameBytes,
            IReadOnlyList<string> AllowedMimeTypes,
            bool RejectEndFrameForI2v)
        {
            if (string.IsNullOrWhiteSpace(ModelLabel))
                throw new ArgumentException("Model label must be non-empty.", nameof(ModelLabel));
            if (string.IsNullOrWhiteSpace(FileNamePrefix))
                throw new ArgumentException("File name prefix must be non-empty.", nameof(FileNamePrefix));
            if (AllowedModes is null || AllowedModes.Count == 0)
                throw new ArgumentException("Allowed modes must be non-empty.", nameof(AllowedModes));
            if (MaxSourceFrameBytes <= 0)
                throw new ArgumentOutOfRangeException(nameof(MaxSourceFrameBytes));
            if (AllowedMimeTypes is null || AllowedMimeTypes.Count == 0)
                throw new ArgumentException("Allowed MIME types must be non-empty.", nameof(AllowedMimeTypes));

            foreach (var mimeType in AllowedMimeTypes)
            {
                if (string.IsNullOrWhiteSpace(mimeType))
                    throw new ArgumentException("Allowed MIME types must be non-empty.", nameof(AllowedMimeTypes));
            }

            this.ModelLabel = ModelLabel;
            this.FileNamePrefix = FileNamePrefix;
            this.AllowedModes = new List<VideoMode>(AllowedModes);
            this.MaxSourceFrameBytes = MaxSourceFrameBytes;
            this.AllowedMimeTypes = new List<string>(AllowedMimeTypes);
            this.RejectEndFrameForI2v = RejectEndFrameForI2v;
        }

        public string ModelLabel { get; }
        public string FileNamePrefix { get; }
        public IReadOnlyList<VideoMode> AllowedModes { get; }
        public long MaxSourceFrameBytes { get; }
        public IReadOnlyList<string> AllowedMimeTypes { get; }
        public bool RejectEndFrameForI2v { get; }
    }
}
