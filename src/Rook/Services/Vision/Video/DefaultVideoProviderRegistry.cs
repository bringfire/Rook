using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Default <see cref="IVideoProviderRegistry"/>. Flattens
    /// registrations into a single model-id → <see cref="ResolvedVideoModel"/>
    /// map at construction. Build-time invariants:
    /// <list type="bullet">
    ///   <item><description>Duplicate model ids across registrations throw
    ///     <see cref="InvalidOperationException"/> with the offending id and
    ///     both provider names.</description></item>
    ///   <item><description>Null/empty model ids, null capabilities, null
    ///     pricing models, or missing per-registration fields throw
    ///     <see cref="InvalidOperationException"/>.</description></item>
    ///   <item><description>Duplicate provider names are <em>allowed</em> —
    ///     a future provider may legitimately split registrations across
    ///     product families.</description></item>
    ///   <item><description>Empty registrations list is allowed — the trivial
    ///     registry is valid (used by tests).</description></item>
    /// </list>
    /// </summary>
    public sealed class DefaultVideoProviderRegistry : IVideoProviderRegistry
    {
        private readonly Dictionary<string, ResolvedVideoModel> _byId;
        private readonly Dictionary<string, IVideoProvider> _providerByName;
        private readonly List<ResolvedVideoModel> _ordered;

        public DefaultVideoProviderRegistry(IEnumerable<IVideoProviderRegistration> registrations)
        {
            if (registrations is null)
                throw new ArgumentNullException(nameof(registrations));

            _byId = new Dictionary<string, ResolvedVideoModel>(StringComparer.Ordinal);
            _providerByName = new Dictionary<string, IVideoProvider>(StringComparer.Ordinal);
            _ordered = new List<ResolvedVideoModel>();

            foreach (var reg in registrations)
            {
                if (reg is null)
                    throw new InvalidOperationException(
                        "Registration is null.");

                if (string.IsNullOrWhiteSpace(reg.ProviderName))
                    throw new InvalidOperationException(
                        "Registration has empty ProviderName.");

                if (reg.Provider is null)
                    throw new InvalidOperationException(
                        $"Provider '{reg.ProviderName}' registration has null Provider.");

                if (reg.OptionsCodec is null)
                    throw new InvalidOperationException(
                        $"Provider '{reg.ProviderName}' registration has null OptionsCodec.");

                if (reg.Models is null)
                    throw new InvalidOperationException(
                        $"Provider '{reg.ProviderName}' registration has null Models.");

                // First-registered-wins for provider-name → provider
                // mapping. Used by CancelAsync's deprecated-model recovery
                // path; assumes registrations sharing a name are
                // interchangeable for out-of-band ops.
                if (!_providerByName.ContainsKey(reg.ProviderName))
                    _providerByName[reg.ProviderName] = reg.Provider;

                foreach (var kvp in reg.Models)
                {
                    if (string.IsNullOrWhiteSpace(kvp.Key))
                        throw new InvalidOperationException(
                            $"Provider '{reg.ProviderName}' has empty model id in registration.");

                    var (cap, pricing) = kvp.Value;
                    if (cap is null)
                        throw new InvalidOperationException(
                            $"Provider '{reg.ProviderName}' model '{kvp.Key}' has null Capability.");
                    if (pricing is null)
                        throw new InvalidOperationException(
                            $"Provider '{reg.ProviderName}' model '{kvp.Key}' has null PricingModel.");

                    // F3 (review pass 2): identity consistency. The
                    // dictionary key is the resolved model id; cap.Id is
                    // the same identity from the data record's perspective.
                    // If they disagree, downstream descriptors / validation
                    // / pricing all use one or the other inconsistently —
                    // a registration that publishes key "runway-x" with
                    // cap.Id "veo-3.1-lite-..." would silently corrupt
                    // identity. Reject at construction.
                    if (string.IsNullOrWhiteSpace(cap.Id))
                        throw new InvalidOperationException(
                            $"Provider '{reg.ProviderName}' model '{kvp.Key}' has empty Capability.Id.");
                    if (!string.Equals(cap.Id, kvp.Key, StringComparison.Ordinal))
                        throw new InvalidOperationException(
                            $"Provider '{reg.ProviderName}' model registration key '{kvp.Key}' " +
                            $"does not match Capability.Id '{cap.Id}'.");

                    if (_byId.TryGetValue(kvp.Key, out var existing))
                        throw new InvalidOperationException(
                            $"Duplicate model id '{kvp.Key}' registered by providers " +
                            $"'{existing.ProviderName}' and '{reg.ProviderName}'.");

                    var resolved = new ResolvedVideoModel(
                        ModelId: kvp.Key,
                        ProviderName: reg.ProviderName,
                        Provider: reg.Provider,
                        Capability: cap,
                        PricingModel: pricing,
                        OptionsCodec: reg.OptionsCodec);

                    _byId[kvp.Key] = resolved;
                    _ordered.Add(resolved);
                }
            }
        }

        public bool TryResolve(string modelId, out ResolvedVideoModel model)
        {
            if (!string.IsNullOrWhiteSpace(modelId) && _byId.TryGetValue(modelId, out var found))
            {
                model = found;
                return true;
            }

            model = null!;
            return false;
        }

        public bool TryResolveProviderByName(string providerName, out IVideoProvider provider)
        {
            if (!string.IsNullOrWhiteSpace(providerName)
                && _providerByName.TryGetValue(providerName, out var found))
            {
                provider = found;
                return true;
            }

            provider = null!;
            return false;
        }

        public IReadOnlyList<VideoModelDescriptor> EnumerateAllModels()
        {
            var list = new List<VideoModelDescriptor>(_ordered.Count);
            foreach (var m in _ordered)
            {
                list.Add(new VideoModelDescriptor(
                    ModelId: m.ModelId,
                    ProviderName: m.ProviderName,
                    Capability: m.Capability,
                    PricingKind: m.PricingModel.Kind,
                    PricingSource: m.PricingModel.PricingSource));
            }
            return list;
        }
    }
}
