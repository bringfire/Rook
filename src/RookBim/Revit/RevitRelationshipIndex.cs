using System.Collections.Generic;

namespace RookBim.Revit
{
    /// <summary>
    /// Factual membership index (room/host/level) built from already-extracted labels. Emits only
    /// what Revit explicitly provides, each entry carrying source + confidence. No inferred
    /// containment, no precomputed calibration pairs.
    /// </summary>
    internal sealed class RevitRelationshipIndex
    {
        private readonly List<object> roomMembership = new List<object>();
        private readonly List<object> hostMembership = new List<object>();
        private readonly List<object> levelMembership = new List<object>();

        public void Accumulate(string elementUniqueId, RevitElementLabels labels)
        {
            if (HasValue(labels.ContainingRoom))
            {
                roomMembership.Add(new
                {
                    elementUniqueId,
                    roomUniqueId = labels.ContainingRoom.Value,
                    source = labels.ContainingRoom.Source,
                    confidence = labels.ContainingRoom.Confidence,
                });
            }

            if (HasValue(labels.HostId))
            {
                hostMembership.Add(new
                {
                    elementUniqueId,
                    hostUniqueId = labels.HostId.Value,
                    source = labels.HostId.Source,
                    confidence = labels.HostId.Confidence,
                });
            }

            if (HasValue(labels.Level))
            {
                levelMembership.Add(new
                {
                    elementUniqueId,
                    levelName = labels.Level.Value,
                    source = labels.Level.Source,
                    confidence = labels.Level.Confidence,
                });
            }
        }

        public object ToWire()
        {
            return new
            {
                roomMembership,
                hostMembership,
                levelMembership,
            };
        }

        public static object EmptyWire()
        {
            return new
            {
                roomMembership = new List<object>(),
                hostMembership = new List<object>(),
                levelMembership = new List<object>()
            };
        }

        private static bool HasValue(BimSemanticLabel? label)
        {
            return label != null && !string.IsNullOrWhiteSpace(label.Value);
        }
    }
}
