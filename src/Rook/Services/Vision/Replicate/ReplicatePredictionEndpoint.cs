using System;

namespace Rook.Services.Vision.Replicate
{
    public sealed class ReplicatePredictionEndpoint
    {
        private ReplicatePredictionEndpoint(string owner, string name)
        {
            Owner = owner;
            Name = name;
            ModelId = owner + "/" + name;
            CreatePredictionPath =
                "v1/models/" +
                EscapePathSegment(owner) +
                "/" +
                EscapePathSegment(name) +
                "/predictions";
        }

        public string Owner { get; }

        public string Name { get; }

        public string ModelId { get; }

        public string CreatePredictionPath { get; }

        public static ReplicatePredictionEndpoint OfficialModel(string owner, string name)
        {
            ValidatePathSegment(owner, nameof(owner));
            ValidatePathSegment(name, nameof(name));

            return new ReplicatePredictionEndpoint(owner, name);
        }

        private static void ValidatePathSegment(string value, string paramName)
        {
            if (string.IsNullOrWhiteSpace(value))
                throw new ArgumentException(
                    "Replicate model endpoint segments must be non-empty.",
                    paramName);

            if (value.IndexOfAny(new[] { '/', '?', '#' }) >= 0)
                throw new ArgumentException(
                    "Replicate model endpoint segments must be single URI path segments.",
                    paramName);
        }

        private static string EscapePathSegment(string value) =>
            Uri.EscapeDataString(value);
    }
}
