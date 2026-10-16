using System;
using System.Linq;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Video
{
    internal sealed class VideoRequestIntent
    {
        private readonly JsonObject _supplied;
        private VideoRequestIntent(VideoGenerationRequest request, JsonObject supplied)
        {
            Request = request.With(referenceFrames: request.ReferenceFrames is null ? null : Array.AsReadOnly(request.ReferenceFrames.ToArray()));
            _supplied = (JsonObject)supplied.DeepClone();
            PersonGenerationSupplied = supplied.ContainsKey("person_generation");
        }
        public VideoGenerationRequest Request { get; }
        public JsonObject SuppliedOptions => (JsonObject)_supplied.DeepClone();
        public bool PersonGenerationSupplied { get; }
        public static VideoRequestIntent Normalize(VideoGenerationRequest request, JsonObject suppliedOptions)
        {
            if (VideoSubmissionCoordinator.IsGoogleModel(request.Model) && !suppliedOptions.ContainsKey("person_generation"))
                request = request.With(options: new VeoOptions(request.Mode == VideoMode.T2V && (request.ReferenceFrames?.Count ?? 0) == 0 && request.StartFrame is null && request.EndFrame is null ? PersonGenerationPolicy.AllowAll : PersonGenerationPolicy.AllowAdult));
            return new VideoRequestIntent(request, suppliedOptions);
        }
    }
}
