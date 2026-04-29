using System;
using System.Collections.Generic;
using System.Globalization;

namespace Rook.Services.Vision.Fal
{
    public static class FalPricingHelpers
    {
        private const string BillableUnitsHeader = "x-fal-billable-units";

        public static bool TryGetBillableUnits(
            IReadOnlyDictionary<string, IReadOnlyList<string>> headers,
            out decimal units)
        {
            if (headers is null) throw new ArgumentNullException(nameof(headers));

            units = 0m;
            foreach (var kvp in headers)
            {
                if (!string.Equals(
                        kvp.Key,
                        BillableUnitsHeader,
                        StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                if (kvp.Value.Count == 0)
                    return false;

                if (decimal.TryParse(
                        kvp.Value[0],
                        NumberStyles.Number,
                        CultureInfo.InvariantCulture,
                        out units))
                {
                    return true;
                }

                units = 0m;
                return false;
            }

            return false;
        }
    }
}
