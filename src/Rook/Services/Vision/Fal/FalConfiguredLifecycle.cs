using System;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Fal
{
    public static class FalConfiguredLifecycle
    {
        public static ProviderJobHandle ParseSubmitHandle(FalOperationBinding binding, JsonObject body)
        {
            var handle = FalLifecycleMapper.ParseSubmitHandle(body, "PUT");
            if (Validate(binding, handle) is GenerationError error) throw new ArgumentException(error.Message);
            // Provider metadata is not lifecycle authority. Keep the accepted persistence seam
            // free of arbitrary response fields and temporary source-media URLs.
            return new ProviderJobHandle(handle.ProviderJobId, handle.StatusUrl, handle.ResponseUrl, handle.CancelUrl, "PUT");
        }
        public static GenerationError? Validate(FalOperationBinding binding, ProviderJobHandle handle)
        {
            if (binding.Invocation != "queue" || string.IsNullOrWhiteSpace(binding.LifecycleRoot) || handle == null ||
                !Regex.IsMatch(handle.ProviderJobId, @"\A[A-Za-z0-9_-]+\z") || handle.CancelHttpMethod != "PUT") return Invalid();
            var path = "/" + binding.LifecycleRoot + "/requests/" + handle.ProviderJobId;
            return ValidUrl(handle.StatusUrl, path + "/status") && ValidUrl(handle.ResponseUrl, path) && ValidUrl(handle.CancelUrl, path + "/cancel") ? null : Invalid();
        }
        private static bool ValidUrl(Uri? url, string path)
        {
            if (url == null || !url.IsAbsoluteUri || url.Scheme != Uri.UriSchemeHttps || url.Host != "queue.fal.run" || !url.IsDefaultPort ||
                url.UserInfo.Length != 0 || url.Fragment.Length != 0 || url.Query.Length != 0 || url.AbsolutePath != path) return false;
            // Uri normalizes dot segments before AbsolutePath; inspect the original as well.
            var original = url.OriginalString;
            return original.IndexOf('%') < 0 && original.IndexOf('\\') < 0 && original.IndexOf("/../", StringComparison.Ordinal) < 0 && original.IndexOf("/./", StringComparison.Ordinal) < 0;
        }
        private static GenerationError Invalid() => new(GenerationErrorCode.InvalidRequest, "Invalid configured fal lifecycle binding.", false, "provider_handle");
    }
}
