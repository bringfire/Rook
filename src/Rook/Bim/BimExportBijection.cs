using System.Collections.Generic;
using System.Linq;

namespace Rook.Bim
{
    /// <summary>
    /// Pure reconciliation of exported keys against the keys stamped on emitted geometry objects.
    /// A key may map to MORE THAN ONE object (a multi-solid element emits one object per Brep; this
    /// is valid, not a duplicate error). Every emitted object must resolve to an expected key, and
    /// every expected key must have at least one emitted object.
    /// </summary>
    public static class BimExportBijection
    {
        public static BimExportVerification Verify(
            IEnumerable<string?> objectKeys,
            IReadOnlyCollection<string> expectedKeys)
        {
            var verification = new BimExportVerification { Ok = true };
            var seen = new HashSet<string>(System.StringComparer.Ordinal);

            foreach (var key in objectKeys)
            {
                if (string.IsNullOrEmpty(key))
                {
                    verification.Ok = false;
                    verification.Discrepancies.Add("A .3dm object has no revit.uniqueId user string.");
                    continue;
                }

                seen.Add(key); // multiple objects per key are allowed (multi-solid element / multi-Brep)

                if (!expectedKeys.Contains(key))
                {
                    verification.Ok = false;
                    verification.Discrepancies.Add($".3dm object key {key} has no exported record.");
                }
            }

            foreach (var key in expectedKeys)
            {
                if (!seen.Contains(key))
                {
                    verification.Ok = false;
                    verification.Discrepancies.Add($"Exported key {key} has no .3dm object.");
                }
            }

            return verification;
        }
    }
}
