using System;
using System.Collections.Generic;
using System.Linq;

namespace Rook.Services.Vision.Fal.Models
{
    public sealed class FalCatalogSnapshot
    {
        private readonly Dictionary<string, FalModelDefinition> _models;
        public string RootDirectory { get; }
        public IReadOnlyList<FalModelDefinition> Definitions { get; }
        internal FalCatalogSnapshot(string root, IEnumerable<FalModelDefinition> definitions)
        {
            RootDirectory = root;
            Definitions = Array.AsReadOnly(definitions.ToArray());
            _models = Definitions.ToDictionary(d => d.ModelId, StringComparer.Ordinal);
        }
        public FalOperationBinding GetOperation(string modelId, string operationId)
        {
            if (TryGetOperation(modelId, operationId, out var binding)) return binding;
            throw new KeyNotFoundException("Unknown configured fal operation: " + modelId + "/" + operationId);
        }
        public bool TryGetOperation(string modelId, string operationId, out FalOperationBinding binding)
        {
            binding = null!;
            if (modelId == null || operationId == null || !_models.TryGetValue(modelId, out var model)) return false;
            var found = model.Operations.FirstOrDefault(o => o.OperationId == operationId);
            if (found == null) return false;
            binding = found; return true;
        }
    }
}
