using System;
using Autodesk.Revit.DB;
using Rook.Bim;

namespace RookBim.Revit
{
    internal static class RevitViewIdentitySerializer
    {
        private const int InvalidElementIdValue = -1;

        internal static BimViewIdentity ViewIdentity(View view)
        {
            if (view == null)
            {
                throw new ArgumentNullException(nameof(view));
            }

            return new BimViewIdentity
            {
                Id = ToInt32OrNull(view.Id) ?? InvalidElementIdValue,
                UniqueId = NullIfWhiteSpace(TryGetUniqueId(view)),
                Name = NullIfWhiteSpace(view.Name),
                Type = view.ViewType.ToString(),
            };
        }

        private static string? TryGetUniqueId(View view)
        {
            try
            {
                return view.UniqueId;
            }
            catch (Autodesk.Revit.Exceptions.InvalidOperationException)
            {
                return null;
            }
        }

        private static string? NullIfWhiteSpace(string? value)
        {
            return string.IsNullOrWhiteSpace(value) ? null : value;
        }

        private static int? ToInt32OrNull(ElementId? id)
        {
            if (id == null || id.Value < int.MinValue || id.Value > int.MaxValue)
            {
                return null;
            }

            return (int)id.Value;
        }
    }
}
