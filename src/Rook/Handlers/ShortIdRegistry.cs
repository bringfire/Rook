using System;
using System.Collections.Generic;

namespace Rook.Handlers
{
    /// <summary>
    /// Bidirectional mapping between short IDs (C1, C2, ..., G1, G2, ...)
    /// and Grasshopper InstanceGuids. Session-stable: the same InstanceGuid
    /// always maps to the same short ID within a session via persistent cache.
    /// </summary>
    public class ShortIdRegistry
    {
        private readonly Dictionary<string, Guid> _shortToGuid = new();
        private readonly Dictionary<Guid, string> _guidToShort = new();
        private readonly Dictionary<Guid, string> _persistentCache = new();

        private int _nextComponentId = 1;
        private int _nextGroupId = 1;

        /// <summary>
        /// Epoch increments on each Rebuild. Used by gh_edit to reject
        /// stale references when the canvas has changed since last snapshot.
        /// </summary>
        public int Epoch { get; private set; }

        /// <summary>
        /// Rebuild active mappings from current document objects.
        /// Reuses cached IDs for known GUIDs (session stability).
        /// Returns the new epoch.
        /// </summary>
        public int Rebuild(IEnumerable<(Guid guid, bool isGroup)> objects)
        {
            _shortToGuid.Clear();
            _guidToShort.Clear();

            foreach (var (guid, isGroup) in objects)
            {
                string shortId;
                if (_persistentCache.TryGetValue(guid, out var cached))
                {
                    shortId = cached;
                }
                else
                {
                    shortId = isGroup
                        ? $"G{_nextGroupId++}"
                        : $"C{_nextComponentId++}";
                    _persistentCache[guid] = shortId;
                }

                _shortToGuid[shortId] = guid;
                _guidToShort[guid] = shortId;
            }

            Epoch++;
            return Epoch;
        }

        /// <summary>
        /// Register a newly created component and return its short ID.
        /// Used by ApplyEdit when creating components in a batch.
        /// </summary>
        public string Register(Guid guid, bool isGroup = false)
        {
            if (_guidToShort.TryGetValue(guid, out var existing))
                return existing;

            var shortId = isGroup
                ? $"G{_nextGroupId++}"
                : $"C{_nextComponentId++}";

            _shortToGuid[shortId] = guid;
            _guidToShort[guid] = shortId;
            _persistentCache[guid] = shortId;
            return shortId;
        }

        /// <summary>Resolve short ID to GUID. Returns null if not found.</summary>
        public Guid? Resolve(string shortId)
        {
            return _shortToGuid.TryGetValue(shortId, out var guid) ? guid : null;
        }

        /// <summary>Resolve GUID to short ID. Returns null if not found.</summary>
        public string? ResolveReverse(Guid guid)
        {
            return _guidToShort.TryGetValue(guid, out var shortId) ? shortId : null;
        }

        /// <summary>
        /// Clear all mappings. Called on NewDocument/OpenDocument
        /// when the canvas document changes entirely.
        /// </summary>
        public void Clear()
        {
            _shortToGuid.Clear();
            _guidToShort.Clear();
            _persistentCache.Clear();
            _nextComponentId = 1;
            _nextGroupId = 1;
            Epoch = 0;
        }
    }
}
