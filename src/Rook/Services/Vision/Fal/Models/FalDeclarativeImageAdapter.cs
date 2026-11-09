using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
namespace Rook.Services.Vision.Fal.Models
{
    public sealed class FalDeclarativeImageAdapter : IFalModelAdapter
    {
        private readonly FalPayloadMapper _mapper = new FalPayloadMapper();
        public JsonObject BuildPayload(FalNormalizedRequest request, IReadOnlyList<FalPreparedMedia> media)
        { RequireBinding(request?.Binding); return _mapper.BuildPayload(request!, media); }
        public ProviderResultOutcome MapResult(FalOperationBinding binding, JsonObject response)
        { RequireBinding(binding); return _mapper.MapResult(binding, response); }
        private static void RequireBinding(FalOperationBinding? binding)
        {
            if (binding == null) throw new ArgumentNullException(nameof(binding));
            if (binding.AdapterId != "fal.image.declarative" || binding.AdapterVersion != 1 || binding.Result.MimeFamily != "image")
                throw new ArgumentException("Binding is not a v1 declarative image operation.", nameof(binding));
        }
    }
}
