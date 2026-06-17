using System.Collections.Generic;

namespace RookBim.Revit
{
    /// <summary>Factual membership index (room/host/level). Task 9 fills Accumulate/ToWire.</summary>
    internal sealed class RevitRelationshipIndex
    {
        public void Accumulate(string elementUniqueId, RevitElementLabels labels)
        {
            // Task 9.
        }

        public object ToWire()
        {
            return EmptyWire();
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
    }
}
