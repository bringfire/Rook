using System.IO;

namespace Rook.UI.Web
{
    /// <summary>
    /// Value returned by <see cref="RookWebSurface.TryResolveVirtualResource"/>
    /// to serve a resource that is NOT embedded in the assembly — typically
    /// an on-disk file (e.g. an artifact blob) or a bridge-synthesized
    /// payload.
    ///
    /// Stream ownership transfers to WebView2 after
    /// <c>CreateWebResourceResponse</c>; callers do not need to dispose
    /// the stream themselves.
    /// </summary>
    public sealed class VirtualResource
    {
        /// <summary>
        /// Response body stream. WebView2 reads and closes it.
        /// </summary>
        public Stream Content { get; }

        /// <summary>
        /// MIME type for the <c>Content-Type</c> header
        /// (e.g. <c>"image/png"</c>, <c>"application/json"</c>).
        /// </summary>
        public string ContentType { get; }

        /// <summary>
        /// HTTP status code (200, 404, etc.). Defaults to 200.
        /// </summary>
        public int StatusCode { get; }

        /// <summary>
        /// Optional additional headers appended to Content-Type with
        /// <c>\r\n</c> separators. Do NOT include Content-Type here —
        /// it's emitted automatically from <see cref="ContentType"/>.
        /// </summary>
        public string? ExtraHeaders { get; }

        public VirtualResource(
            Stream content,
            string contentType,
            int statusCode = 200,
            string? extraHeaders = null)
        {
            Content = content;
            ContentType = contentType;
            StatusCode = statusCode;
            ExtraHeaders = extraHeaders;
        }
    }
}
