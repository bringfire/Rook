using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Fal
{
    public sealed class FalHttpResponse
    {
        public FalHttpResponse(
            int statusCode,
            string body,
            IReadOnlyDictionary<string, IReadOnlyList<string>> headers)
        {
            if (headers is null)
                throw new ArgumentNullException(nameof(headers));

            StatusCode = statusCode;
            Body = body ?? string.Empty;

            var copy = new Dictionary<string, IReadOnlyList<string>>(
                StringComparer.OrdinalIgnoreCase);
            foreach (var kvp in headers)
            {
                copy[kvp.Key] = new List<string>(kvp.Value).ToArray();
            }
            Headers = copy;
        }

        public int StatusCode { get; }
        public string Body { get; }
        public IReadOnlyDictionary<string, IReadOnlyList<string>> Headers { get; }
        public bool IsSuccessStatusCode => StatusCode >= 200 && StatusCode <= 299;
    }
}
