using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Pure data description of a video-generation model's capability
    /// matrix. PR-2 renames the V1c <c>ModelCapability</c> to
    /// <see cref="VideoCapability"/> and converts to <c>sealed class</c>
    /// with read-only properties + defensive list copies via
    /// <see cref="Array.AsReadOnly{T}"/>; this matches the Generation
    /// namespace's invariant-bearing pattern (no <c>init</c> setters,
    /// no <c>with</c>-bypass, structurally read-only lists). Implements
    /// <see cref="IModelCapability"/> so the modality-neutral catalog
    /// surfaces (provider registries, picker UIs, descriptor helpers)
    /// can read video models without touching <c>VideoCapability</c>'s
    /// typed fields.
    ///
    /// <para>Pricing is on the per-resolved <c>IPricingModel&lt;...&gt;</c>
    /// attached to <see cref="ResolvedVideoModel"/>; this type stays
    /// pure data.</para>
    /// </summary>
    public sealed class VideoCapability : IModelCapability
    {
        // Parameter names match the prior positional record (PascalCase)
        // so existing call sites that use named arguments — e.g.
        // VeoCapabilities — keep compiling without rewrite.
        public VideoCapability(
            string Id,
            string Name,
            string Status,                                  // "stable" | "preview"
            IReadOnlyList<string> Resolutions,
            IReadOnlyList<int> Durations,
            IReadOnlyList<string> AspectRatios,
            IReadOnlyList<VideoMode> Modes,                  // T2V supported by all; I2V/Interp gated
            bool SupportsReferenceImages,
            int MaxReferenceImages,
            IReadOnlyList<string> Must8sWith)                // tokens forcing duration=8 ("1080p", "4k", "referenceImages")
        {
            if (string.IsNullOrWhiteSpace(Id))
                throw new ArgumentException("Id must be non-empty.", nameof(Id));
            if (string.IsNullOrWhiteSpace(Name))
                throw new ArgumentException("Name must be non-empty.", nameof(Name));
            if (string.IsNullOrWhiteSpace(Status))
                throw new ArgumentException("Status must be non-empty.", nameof(Status));
            if (Resolutions is null) throw new ArgumentNullException(nameof(Resolutions));
            if (Durations is null) throw new ArgumentNullException(nameof(Durations));
            if (AspectRatios is null) throw new ArgumentNullException(nameof(AspectRatios));
            if (Modes is null) throw new ArgumentNullException(nameof(Modes));
            if (Must8sWith is null) throw new ArgumentNullException(nameof(Must8sWith));
            if (MaxReferenceImages < 0)
                throw new ArgumentOutOfRangeException(
                    nameof(MaxReferenceImages), MaxReferenceImages,
                    "MaxReferenceImages must be non-negative.");

            this.Id = Id;
            this.Name = Name;
            this.Status = Status;
            this.Resolutions = CopyReadOnly(Resolutions);
            this.Durations = CopyReadOnly(Durations);
            this.AspectRatios = CopyReadOnly(AspectRatios);
            this.Modes = CopyReadOnly(Modes);
            this.SupportsReferenceImages = SupportsReferenceImages;
            this.MaxReferenceImages = MaxReferenceImages;
            this.Must8sWith = CopyReadOnly(Must8sWith);

            // SubCapabilities is the modality-neutral projection of
            // Modes for IModelCapability consumers. Stable lowercase
            // strings; future picker UI filters by these.
            var subs = new List<string>(Modes.Count);
            foreach (var m in Modes)
            {
                subs.Add(m switch
                {
                    VideoMode.T2V => "text_to_video",
                    VideoMode.I2V => "image_to_video",
                    VideoMode.Interp => "frame_interpolation",
                    _ => m.ToString().ToLowerInvariant(),
                });
            }
            SubCapabilities = new ReadOnlyCollection<string>(subs);
        }

        public string Id { get; }
        public string Name { get; }
        public string Status { get; }
        public string Modality => "video";
        public IReadOnlyList<string> SubCapabilities { get; }

        public IReadOnlyList<string> Resolutions { get; }
        public IReadOnlyList<int> Durations { get; }
        public IReadOnlyList<string> AspectRatios { get; }
        public IReadOnlyList<VideoMode> Modes { get; }
        public bool SupportsReferenceImages { get; }
        public int MaxReferenceImages { get; }
        public IReadOnlyList<string> Must8sWith { get; }

        // Defensive copy + Array.AsReadOnly: callers cannot mutate the
        // backing storage even by downcasting. Explicit foreach because
        // net48's Dictionary<,> / Array constructors don't take
        // IReadOnlyCollection<T>.
        private static IReadOnlyList<T> CopyReadOnly<T>(IReadOnlyList<T> source)
        {
            var copy = new T[source.Count];
            for (int i = 0; i < source.Count; i++) copy[i] = source[i];
            return Array.AsReadOnly(copy);
        }
    }
}
