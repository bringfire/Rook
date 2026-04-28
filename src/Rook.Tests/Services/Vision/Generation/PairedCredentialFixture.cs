using System.Collections.Generic;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    /// <summary>
    /// Paired-credential shape demonstration. Phase 0 evidence: Tencent
    /// requires a paired SecretId + SecretKey under separate slots
    /// (<c>tencent.secret_id</c> + <c>tencent.secret_key</c>); absence
    /// of one is distinct from absence of both.
    ///
    /// PR-1 ships only the shape demonstration via a tiny in-memory
    /// store stand-in. The real <see cref="IGenerationSecretStore"/>
    /// (DPAPI-backed, with legacy-section migration) lands in PR-4.
    /// This fixture confirms the seam-level discrimination — multiple
    /// independently-keyed secrets per provider — works as intended.
    /// </summary>
    public class PairedCredentialFixture
    {
        private sealed class InMemorySecretStore
        {
            private readonly Dictionary<string, string> _slots = new();

            public string? Get(string key) => _slots.TryGetValue(key, out var v) ? v : null;
            public void Set(string key, string value) => _slots[key] = value;
            public bool Has(string key) => _slots.ContainsKey(key);
        }

        [Fact]
        public void Single_token_provider_uses_one_slot()
        {
            var store = new InMemorySecretStore();
            store.Set("gemini.api_key", "AIza-test-token");

            Assert.True(store.Has("gemini.api_key"));
            Assert.False(store.Has("gemini.secret_id"));
            Assert.Equal("AIza-test-token", store.Get("gemini.api_key"));
        }

        [Fact]
        public void Paired_credential_provider_uses_two_slots_independently()
        {
            var store = new InMemorySecretStore();
            store.Set("tencent.secret_id", "AKID-test");
            store.Set("tencent.secret_key", "secret-test");

            Assert.True(store.Has("tencent.secret_id"));
            Assert.True(store.Has("tencent.secret_key"));
            Assert.NotEqual(store.Get("tencent.secret_id"), store.Get("tencent.secret_key"));
        }

        [Fact]
        public void Partial_paired_credential_is_distinct_from_total_absence()
        {
            var store = new InMemorySecretStore();
            store.Set("tencent.secret_id", "AKID-test");
            // tencent.secret_key intentionally absent

            Assert.True(store.Has("tencent.secret_id"));
            Assert.False(store.Has("tencent.secret_key"));

            // The provider can distinguish "configured one of two"
            // from "configured none" — the seam supports the
            // discrimination PR-4's IGenerationSecretStore.HasSecret
            // will surface as DependencyUnavailable error variants.
            var hasAny = store.Has("tencent.secret_id") || store.Has("tencent.secret_key");
            var hasAll = store.Has("tencent.secret_id") && store.Has("tencent.secret_key");
            Assert.True(hasAny);
            Assert.False(hasAll);
        }
    }
}
