using System.Text;

namespace Rook.Bim
{
    public static class BimExportObjectNamer
    {
        public static string? ObjectName(
            BimNameScheme scheme, string? category, string? type, long? elementId, string? revitName)
        {
            switch (scheme)
            {
                case BimNameScheme.None:
                    return null;

                case BimNameScheme.RevitName:
                    return Clean(revitName) ?? FallbackBase(category, type);

                case BimNameScheme.TypeOnly:
                    return FallbackBase(category, type);

                case BimNameScheme.Readable:
                    return Readable(category, type);

                case BimNameScheme.ReadableWithId:
                default:
                    return WithId(Readable(category, type), elementId);
            }
        }

        private static string Readable(string? category, string? type)
        {
            var cat = Clean(category);
            var typ = Clean(type);
            if (cat != null && typ != null)
            {
                return cat + " - " + typ;
            }

            return FallbackBase(category, type);
        }

        // Type preferred; then category; then the generic literal.
        private static string FallbackBase(string? category, string? type)
        {
            return Clean(type) ?? Clean(category) ?? "Revit Element";
        }

        private static string WithId(string baseName, long? elementId)
        {
            return elementId.HasValue ? baseName + " [" + elementId.Value + "]" : baseName;
        }

        // Object names may contain spaces and most punctuation; strip only control chars and trim.
        private static string? Clean(string? value)
        {
            if (string.IsNullOrWhiteSpace(value))
            {
                return null;
            }

            var builder = new StringBuilder(value!.Length);
            foreach (var c in value.Trim())
            {
                if (!char.IsControl(c))
                {
                    builder.Append(c);
                }
            }

            var result = builder.ToString().Trim();
            return result.Length == 0 ? null : result;
        }
    }
}
