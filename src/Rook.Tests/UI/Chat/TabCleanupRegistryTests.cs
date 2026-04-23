using System;
using System.Collections.Generic;
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    /// <summary>
    /// Tests for <see cref="TabCleanupRegistry"/>, the callback
    /// registry that backs <see cref="RookChatPanel"/>'s generalized
    /// tab cleanup. The fire-once invariants live here (rather than
    /// in an Eto-dependent panel test) because <c>TabPage</c>
    /// construction requires an Eto platform init that is not
    /// available in the xUnit host.
    ///
    /// Keys are arbitrary <c>object</c>; at the call site the panel
    /// passes <c>TabPage</c> references, but the registry does not
    /// depend on that type.
    /// </summary>
    public class TabCleanupRegistryTests
    {
        [Fact]
        public void FireAndRemove_Registered_InvokesCallbackAndRemoves()
        {
            var calls = 0;
            var reg = new TabCleanupRegistry(_ => { });
            var key = new object();
            reg.Register(key, () => calls++);

            var fired = reg.FireAndRemove(key);

            Assert.True(fired);
            Assert.Equal(1, calls);
            Assert.Equal(0, reg.Count);
        }

        [Fact]
        public void FireAndRemove_Twice_FiresExactlyOnce()
        {
            var calls = 0;
            var reg = new TabCleanupRegistry(_ => { });
            var key = new object();
            reg.Register(key, () => calls++);

            reg.FireAndRemove(key);
            var secondFire = reg.FireAndRemove(key);

            Assert.False(secondFire);
            Assert.Equal(1, calls);
        }

        [Fact]
        public void FireAndRemove_UnregisteredKey_ReturnsFalse()
        {
            var reg = new TabCleanupRegistry(_ => { });

            var fired = reg.FireAndRemove(new object());

            Assert.False(fired);
        }

        [Fact]
        public void DrainAll_EmptyRegistry_NoOp()
        {
            var reg = new TabCleanupRegistry(_ => { });
            reg.DrainAll(); // must not throw
            Assert.Equal(0, reg.Count);
        }

        [Fact]
        public void DrainAll_FiresAllCallbacksAndClears()
        {
            var calls = new List<string>();
            var reg = new TabCleanupRegistry(_ => { });
            reg.Register("a", () => calls.Add("a"));
            reg.Register("b", () => calls.Add("b"));
            reg.Register("c", () => calls.Add("c"));

            reg.DrainAll();

            Assert.Equal(3, calls.Count);
            Assert.Contains("a", calls);
            Assert.Contains("b", calls);
            Assert.Contains("c", calls);
            Assert.Equal(0, reg.Count);
        }

        [Fact]
        public void CloseThenDispose_FiresExactlyOnce()
        {
            // Symmetry test: Close Tab removes the entry; the later
            // Dispose-time DrainAll sees no entry and does not fire
            // the callback a second time. This is the core invariant
            // Codex asked us to pin.
            var calls = 0;
            var reg = new TabCleanupRegistry(_ => { });
            var key = new object();
            reg.Register(key, () => calls++);

            reg.FireAndRemove(key);  // "Close Tab" path
            reg.DrainAll();           // "Dispose" path

            Assert.Equal(1, calls);
        }

        [Fact]
        public void Register_NullCallback_IsNoOp()
        {
            // Callers do not need to guard nullability at the call site.
            var reg = new TabCleanupRegistry(_ => { });

            reg.Register(new object(), onClosed: null);

            Assert.Equal(0, reg.Count);
        }

        [Fact]
        public void Register_DuplicateKey_Overwrites()
        {
            // Registering twice for the same key replaces the callback.
            // Prevents stale closures from firing when tabs rebind.
            var calls = new List<string>();
            var reg = new TabCleanupRegistry(_ => { });
            var key = new object();

            reg.Register(key, () => calls.Add("first"));
            reg.Register(key, () => calls.Add("second"));

            reg.FireAndRemove(key);

            Assert.Single(calls);
            Assert.Equal("second", calls[0]);
        }

        [Fact]
        public void FireAndRemove_CallbackThrows_LogsAndRemoves()
        {
            // A throwing callback must not leave the entry in the
            // registry (which would let a later DrainAll re-invoke it)
            // and must not propagate to the caller (which would leave
            // the tab page half-removed from the UI).
            var logs = new List<string>();
            var reg = new TabCleanupRegistry(logs.Add);
            var key = new object();
            reg.Register(key, () => throw new InvalidOperationException("test-throw"));

            var fired = reg.FireAndRemove(key);

            Assert.True(fired);
            Assert.Equal(0, reg.Count);
            Assert.Contains(logs, m => m.Contains("test-throw"));
        }

        [Fact]
        public void DrainAll_CallbackThrows_LogsAndStillFiresOthers()
        {
            // A throwing callback must not prevent other pending
            // callbacks from firing during Dispose.
            var logs = new List<string>();
            var calls = 0;
            var reg = new TabCleanupRegistry(logs.Add);
            reg.Register("throwing", () => throw new InvalidOperationException("test-throw"));
            reg.Register("ok", () => calls++);

            reg.DrainAll();

            Assert.Equal(1, calls);
            Assert.Contains(logs, m => m.Contains("test-throw"));
        }

        [Fact]
        public void RemoveBeforeInvoke_PreventsReentrantRefire()
        {
            // If a callback somehow re-enters FireAndRemove for the
            // same key (e.g. via a reentrant UI event), the entry
            // must already be gone so we don't double-fire. We
            // simulate by having the callback call FireAndRemove
            // back on itself.
            var calls = 0;
            TabCleanupRegistry? reg = null;
            reg = new TabCleanupRegistry(_ => { });
            var key = new object();
            reg.Register(key, () =>
            {
                calls++;
                // Reentrant call — should be a no-op because the
                // entry was removed BEFORE the callback fired.
                reg!.FireAndRemove(key);
            });

            reg.FireAndRemove(key);

            Assert.Equal(1, calls);
        }

        [Fact]
        public void KeyEquality_IsReferenceEquality()
        {
            // Two distinct object instances are treated as different
            // keys. This matches Dictionary<object, Action> default
            // behavior and reflects the per-TabPage-instance semantic
            // — the panel never holds two TabPages that should share
            // a cleanup callback.
            var reg = new TabCleanupRegistry(_ => { });
            var calls = 0;
            var keyA = new List<int>();  // distinct reference
            var keyB = new List<int>();  // equal-by-value but distinct reference

            reg.Register(keyA, () => calls++);

            var fired = reg.FireAndRemove(keyB);
            Assert.False(fired);
            Assert.Equal(0, calls);

            Assert.True(reg.FireAndRemove(keyA));
            Assert.Equal(1, calls);
        }
    }
}
