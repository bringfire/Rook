using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Image
{
    public sealed class DefaultImageProviderRegistry : IImageProviderRegistry
    {
        private readonly Dictionary<string, ResolvedImageModel> _byId;
        private readonly Dictionary<string, IImageProvider> _providerByName;
        private readonly List<ResolvedImageModel> _ordered;

        public DefaultImageProviderRegistry(IEnumerable<IImageProviderRegistration> registrations)
        {
            if (registrations is null)
                throw new ArgumentNullException(nameof(registrations));

            _byId = new Dictionary<string, ResolvedImageModel>(StringComparer.Ordinal);
            _providerByName = new Dictionary<string, IImageProvider>(StringComparer.Ordinal);
            _ordered = new List<ResolvedImageModel>();

            foreach (var reg in registrations)
            {
                if (reg is null)
                    throw new InvalidOperationException("Registration is null.");
                if (string.IsNullOrWhiteSpace(reg.ProviderName))
                    throw new InvalidOperationException("Registration has empty ProviderName.");
                if (reg.Provider is null)
                    throw new InvalidOperationException(
                        $"Provider '{reg.ProviderName}' registration has null Provider.");
                if (reg.OptionsCodec is null)
                    throw new InvalidOperationException(
                        $"Provider '{reg.ProviderName}' registration has null OptionsCodec.");
                if (reg.Models is null)
                    throw new InvalidOperationException(
                        $"Provider '{reg.ProviderName}' registration has null Models.");

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

                    var resolved = new ResolvedImageModel(
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

        public bool TryResolve(string modelId, out ResolvedImageModel model)
        {
            if (!string.IsNullOrWhiteSpace(modelId) && _byId.TryGetValue(modelId, out var found))
            {
                model = found;
                return true;
            }

            model = null!;
            return false;
        }

        public bool TryResolveProviderByName(string providerName, out IImageProvider provider)
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

        public IReadOnlyList<ImageModelDescriptor> EnumerateAllModels()
        {
            var list = new List<ImageModelDescriptor>(_ordered.Count);
            foreach (var m in _ordered)
            {
                list.Add(new ImageModelDescriptor(
                    ModelId: m.ModelId,
                    ProviderName: m.ProviderName,
                    Capability: m.Capability,
                    PricingSource: m.PricingModel.PricingSource));
            }
            return list;
        }
    }
}
