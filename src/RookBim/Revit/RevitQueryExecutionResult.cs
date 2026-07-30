using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using Rook.Bim;

namespace RookBim.Revit
{
    internal sealed class RevitQueryExecutionResult
    {
        internal RevitQueryExecutionResult(
            BimApiResponse response,
            IEnumerable<Element>? elements = null)
        {
            Response = response ?? throw new ArgumentNullException(nameof(response));
            Elements = (elements ?? Enumerable.Empty<Element>()).ToList().AsReadOnly();
        }

        internal BimApiResponse Response { get; }

        internal IReadOnlyList<Element> Elements { get; }
    }
}
