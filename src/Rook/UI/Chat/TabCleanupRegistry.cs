using System;
using System.Collections.Generic;

namespace Rook.UI.Chat
{
    /// <summary>
    /// Tracks per-tab <c>onClosed</c> callbacks for
    /// <see cref="RookChatPanel"/>. Factored out of the panel so the
    /// fire-once invariants are unit-testable without instantiating
    /// Eto.Forms widgets (<c>TabPage</c> construction requires a
    /// platform init that is not available in the xUnit host).
    ///
    /// Invariants:
    /// <list type="bullet">
    ///   <item>A callback registered for a key fires at most once across
    ///         the registry's lifetime, regardless of how many times
    ///         <see cref="FireAndRemove"/> or <see cref="DrainAll"/>
    ///         is invoked for that key.</item>
    ///   <item>A callback that throws is logged but does not prevent
    ///         later callbacks from firing during <see cref="DrainAll"/>.</item>
    ///   <item>Null callbacks at registration time are ignored (no entry
    ///         stored); later close/drain paths see no entry and no-op.</item>
    /// </list>
    ///
    /// Keys are <see cref="object"/> (typically <c>TabPage</c> at the
    /// call site) to keep the registry agnostic of Eto types. Equality
    /// is reference equality by default.
    /// </summary>
    internal sealed class TabCleanupRegistry
    {
        private readonly Dictionary<object, Action> _callbacks = new();
        private readonly Action<string> _log;

        public TabCleanupRegistry(Action<string> log)
        {
            _log = log ?? (_ => { });
        }

        /// <summary>Number of registered callbacks still pending.</summary>
        public int Count => _callbacks.Count;

        /// <summary>
        /// Register a cleanup callback for <paramref name="key"/>.
        /// No-op when <paramref name="onClosed"/> is null — the caller
        /// does not need to guard nullability at the call site.
        /// Duplicate registration for the same key overwrites.
        /// </summary>
        public void Register(object key, Action? onClosed)
        {
            if (onClosed is null) return;
            _callbacks[key] = onClosed;
        }

        /// <summary>
        /// Fire the callback for <paramref name="key"/> exactly once and
        /// remove it from the registry. Subsequent calls with the same
        /// key are no-ops. Returns <c>true</c> if a callback fired,
        /// <c>false</c> if the key had no registration.
        /// </summary>
        public bool FireAndRemove(object key)
        {
            if (!_callbacks.TryGetValue(key, out var onClosed)) return false;
            _callbacks.Remove(key); // remove BEFORE invoke so a throwing callback cannot re-register or re-fire
            try { onClosed(); }
            catch (Exception ex)
            {
                _log($"[RookChatPanel] Tab onClosed callback threw: {ex.Message}");
            }
            return true;
        }

        /// <summary>
        /// Fire every registered callback once and clear the registry.
        /// A throwing callback is logged and skipped; later callbacks
        /// still fire.
        /// </summary>
        public void DrainAll()
        {
            // Snapshot the values so a callback cannot mutate the
            // enumeration mid-iteration (defensive; current callers
            // don't re-register from inside a cleanup, but it's cheap).
            var snapshot = new List<KeyValuePair<object, Action>>(_callbacks);
            _callbacks.Clear();

            foreach (var kvp in snapshot)
            {
                try { kvp.Value(); }
                catch (Exception ex)
                {
                    _log($"[RookChatPanel] Dispose onClosed callback threw: {ex.Message}");
                }
            }
        }
    }
}
