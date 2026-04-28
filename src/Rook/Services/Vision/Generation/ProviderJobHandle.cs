using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Generation
{
    /// <summary>
    /// Opaque-to-the-manager handle representing a queued provider job.
    /// Carries the provider job id plus optional URLs and metadata that
    /// async providers expose at submit and update across status polls.
    ///
    /// <para><b>Sealed class with read-only properties</b> — invariants
    /// (absolute http/https URLs, recognized HTTP cancel verb) cannot
    /// be bypassed via <c>with</c> or object initializers. Producing a
    /// handle whose result token has been stamped after a status poll
    /// uses <see cref="WithResultToken"/>, which goes through the
    /// validating constructor.</para>
    ///
    /// <para>Field population per provider (Phase 0 evidence):
    /// <list type="bullet">
    ///   <item><b>Veo</b> — <see cref="ProviderJobId"/> at submit;
    ///         <see cref="ProviderResultToken"/> stamped via
    ///         <see cref="WithResultToken"/> when status reports
    ///         <see cref="ProviderCompleteStatusOutcome"/>.</item>
    ///   <item><b>fal queue</b> — populates URL fields and
    ///         <see cref="CancelHttpMethod"/>; result lives at
    ///         <see cref="ResponseUrl"/>.</item>
    ///   <item><b>Replicate</b> — <see cref="StatusUrl"/> +
    ///         <see cref="CancelUrl"/>; <see cref="ResponseUrl"/> null;
    ///         result token stamped at terminal poll.</item>
    /// </list></para>
    /// </summary>
    public sealed class ProviderJobHandle
    {
        // Allowed cancel verbs: POST per Replicate, PUT per fal Hunyuan.
        // DELETE is RESTful for some providers; tolerated. Other verbs
        // would be a contract violation worth catching at the seam.
        private static readonly HashSet<string> AllowedCancelMethods =
            new(StringComparer.OrdinalIgnoreCase) { "POST", "PUT", "DELETE" };

        public ProviderJobHandle(
            string providerJobId,
            Uri? statusUrl = null,
            Uri? responseUrl = null,
            Uri? cancelUrl = null,
            string? cancelHttpMethod = null,
            string? providerResultToken = null,
            IReadOnlyDictionary<string, JsonNode>? providerMetadata = null)
        {
            if (string.IsNullOrWhiteSpace(providerJobId))
                throw new ArgumentException(
                    "ProviderJobId must be non-empty.", nameof(providerJobId));

            ValidateOptionalHttpUrl(statusUrl, nameof(statusUrl));
            ValidateOptionalHttpUrl(responseUrl, nameof(responseUrl));
            ValidateOptionalHttpUrl(cancelUrl, nameof(cancelUrl));

            string? normalizedCancel = null;
            if (cancelHttpMethod is not null)
            {
                if (string.IsNullOrWhiteSpace(cancelHttpMethod))
                    throw new ArgumentException(
                        "CancelHttpMethod must be non-empty when set; pass null to omit.",
                        nameof(cancelHttpMethod));

                normalizedCancel = cancelHttpMethod.Trim().ToUpperInvariant();
                if (!AllowedCancelMethods.Contains(normalizedCancel))
                    throw new ArgumentException(
                        $"CancelHttpMethod '{cancelHttpMethod}' is not in the supported set " +
                        $"({string.Join(", ", AllowedCancelMethods)}). Add a provider-supported " +
                        "verb to AllowedCancelMethods if a new provider needs it.",
                        nameof(cancelHttpMethod));
            }

            ProviderJobId = providerJobId;
            StatusUrl = statusUrl;
            ResponseUrl = responseUrl;
            CancelUrl = cancelUrl;
            CancelHttpMethod = normalizedCancel;
            ProviderResultToken = providerResultToken;
            // Defensive container copy when present. Caller's
            // dictionary remains externally mutable otherwise.
            // Explicit foreach because net48's Dictionary<,> has no
            // IReadOnlyDictionary ctor overload.
            if (providerMetadata is null)
            {
                ProviderMetadata = null;
            }
            else
            {
                var metaCopy = new Dictionary<string, JsonNode>(providerMetadata.Count);
                foreach (var kvp in providerMetadata) metaCopy[kvp.Key] = kvp.Value;
                ProviderMetadata = metaCopy;
            }
        }

        public string ProviderJobId { get; }

        /// <summary>fal: <c>status_url</c>; Replicate: <c>urls.get</c>.</summary>
        public Uri? StatusUrl { get; }

        /// <summary>fal: <c>response_url</c>; null when terminal poll
        /// embeds the result (Replicate).</summary>
        public Uri? ResponseUrl { get; }

        /// <summary>fal: <c>cancel_url</c>; Replicate: <c>urls.cancel</c>.</summary>
        public Uri? CancelUrl { get; }

        /// <summary>HTTP method to invoke <see cref="CancelUrl"/>. Normalized
        /// to UPPERCASE; restricted to the recognized set
        /// (<c>POST</c>, <c>PUT</c>, <c>DELETE</c>). Null for SDK-mediated
        /// providers (Tencent) where cancellation goes through a typed
        /// SDK call.</summary>
        public string? CancelHttpMethod { get; }

        /// <summary>Provider-specific result handle stamped onto the
        /// handle at <see cref="ProviderCompleteStatusOutcome"/>.</summary>
        public string? ProviderResultToken { get; }

        /// <summary>Free-form provider-specific bag (e.g. fal's
        /// <c>queue_position</c>). Round-trips through the ledger.</summary>
        public IReadOnlyDictionary<string, JsonNode>? ProviderMetadata { get; }

        /// <summary>Returns a new handle with
        /// <see cref="ProviderResultToken"/> set to
        /// <paramref name="providerResultToken"/>; all other fields are
        /// preserved verbatim. Goes through the validating constructor
        /// so invariants are re-checked. Used by status-polling code
        /// that observes a terminal poll embedding the result address.</summary>
        public ProviderJobHandle WithResultToken(string? providerResultToken) =>
            new(
                providerJobId: ProviderJobId,
                statusUrl: StatusUrl,
                responseUrl: ResponseUrl,
                cancelUrl: CancelUrl,
                cancelHttpMethod: CancelHttpMethod,
                providerResultToken: providerResultToken,
                providerMetadata: ProviderMetadata);

        // All handle URLs that the manager will fetch from must be
        // absolute http/https. Reject relative URIs and unsupported
        // schemes (file://, ftp://, data:) at the seam.
        private static void ValidateOptionalHttpUrl(Uri? url, string argName)
        {
            if (url is null) return;
            if (!url.IsAbsoluteUri)
                throw new ArgumentException(
                    $"{argName} must be absolute; got '{url}'.", argName);
            if (url.Scheme != Uri.UriSchemeHttp && url.Scheme != Uri.UriSchemeHttps)
                throw new ArgumentException(
                    $"{argName} must use http or https scheme; got '{url.Scheme}'.",
                    argName);
        }
    }
}
