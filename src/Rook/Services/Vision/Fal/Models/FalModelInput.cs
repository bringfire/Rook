using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Fal.Models
{
    /// <summary>Raw supplied controls. Absence is retained independently of defaults.</summary>
    public sealed class FalModelInput
    {
        private readonly JsonObject _requestFields;
        private readonly JsonObject _options;
        public JsonObject RequestFields => (JsonObject)_requestFields.DeepClone();
        public JsonObject Options => (JsonObject)_options.DeepClone();
        public string? OperationId { get; }
        public IReadOnlyList<FalMediaInput> Media { get; }
        public int OutputCount { get; }
        public FalModelInput(JsonObject? requestFields = null, JsonObject? options = null, string? operationId = null,
            IReadOnlyList<FalMediaInput>? media = null, int outputCount = 1)
        {
            _requestFields = (JsonObject)(requestFields ?? new JsonObject()).DeepClone();
            _options = (JsonObject)(options ?? new JsonObject()).DeepClone();
            OperationId = operationId; OutputCount = outputCount;
            Media = Array.AsReadOnly((media ?? Array.Empty<FalMediaInput>()).Select(m => m ?? throw new ArgumentException("Media entries cannot be null.", nameof(media))).ToArray());
        }
    }

    public sealed class FalMediaInput
    {
        public string Role { get; }
        public int Ordinal { get; }
        public MediaRef Source { get; }
        public FalMediaInput(string role, int ordinal, MediaRef source)
        {
            Role = role ?? throw new ArgumentNullException(nameof(role)); Ordinal = ordinal;
            Source = source ?? throw new ArgumentNullException(nameof(source));
        }
    }
}
