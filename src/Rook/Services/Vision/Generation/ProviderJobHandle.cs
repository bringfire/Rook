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
    /// <para>Field population per provider (Phase 0 evidence):
    /// <list type="bullet">
    ///   <item><b>Veo</b> — populates <see cref="ProviderJobId"/> only at
    ///         submit; <see cref="ProviderResultToken"/> (videoUri) is
    ///         stamped onto an updated handle when status reports
    ///         <see cref="ProviderCompleteStatusOutcome"/>. URL fields
    ///         remain null.</item>
    ///   <item><b>fal queue</b> — populates <see cref="StatusUrl"/>,
    ///         <see cref="ResponseUrl"/>, <see cref="CancelUrl"/>,
    ///         <see cref="CancelHttpMethod"/>; the result lives at
    ///         <see cref="ResponseUrl"/>.</item>
    ///   <item><b>Replicate</b> — populates <see cref="StatusUrl"/>,
    ///         <see cref="CancelUrl"/>; <see cref="ResponseUrl"/> is
    ///         null because the terminal poll body embeds the result;
    ///         <see cref="ProviderResultToken"/> is the embedded output
    ///         URL stamped at terminal poll.</item>
    /// </list></para>
    ///
    /// <para>Persisted in the ledger on PR-2's video path (in the
    /// existing <c>Extensions["provider_handle"]</c> JsonObject only
    /// when the optional fields are populated, so Veo records remain
    /// byte-identical to V1c on disk).</para>
    /// </summary>
    public sealed record ProviderJobHandle
    {
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

            ProviderJobId = providerJobId;
            StatusUrl = statusUrl;
            ResponseUrl = responseUrl;
            CancelUrl = cancelUrl;
            CancelHttpMethod = cancelHttpMethod;
            ProviderResultToken = providerResultToken;
            ProviderMetadata = providerMetadata;
        }

        // All handle URLs that the manager will fetch from must be
        // absolute http/https. Reject relative URIs and unsupported
        // schemes (file://, ftp://, data:) at the seam — managers
        // should never have to defend against them downstream.
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

        public string ProviderJobId { get; init; }

        /// <summary>fal: <c>status_url</c>; Replicate: <c>urls.get</c>.</summary>
        public Uri? StatusUrl { get; init; }

        /// <summary>fal: <c>response_url</c> for the separate-fetch case;
        /// null when the terminal poll body embeds the result (Replicate).</summary>
        public Uri? ResponseUrl { get; init; }

        /// <summary>fal: <c>cancel_url</c>; Replicate: <c>urls.cancel</c>.</summary>
        public Uri? CancelUrl { get; init; }

        /// <summary>HTTP method to invoke <see cref="CancelUrl"/> with.
        /// fal Hunyuan: <c>PUT</c>; Replicate: <c>POST</c>. Null for
        /// SDK-mediated providers (Tencent) where cancellation goes
        /// through a typed SDK call rather than a raw HTTP method.</summary>
        public string? CancelHttpMethod { get; init; }

        /// <summary>Provider-specific result handle stamped onto the
        /// handle at <see cref="ProviderCompleteStatusOutcome"/>. Veo:
        /// videoUri. Replicate: embedded output URL. fal queue: null
        /// (the result address is <see cref="ResponseUrl"/>).</summary>
        public string? ProviderResultToken { get; init; }

        /// <summary>Free-form provider-specific bag (e.g. fal's
        /// <c>queue_position</c>, Replicate's <c>logs</c> tail).
        /// Round-trips through the ledger via JsonNode so audit /
        /// replay can reconstruct what the provider returned.</summary>
        public IReadOnlyDictionary<string, JsonNode>? ProviderMetadata { get; init; }
    }
}
