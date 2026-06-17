using System.Text;

namespace Rook.Bim
{
    public static class BimExportLayerNamer
    {
        public const string Root = "RookBim";
        public const string ModelLeaf = "Model";
        public const string NoLevel = "_NoLevel";
        public const string OtherCategory = "_Other";

        public static string LayerPath(BimLayerScheme scheme, string? category, string? levelValue)
        {
            switch (scheme)
            {
                case BimLayerScheme.ByCategory:
                    return Root + "::" + CategorySegment(category);

                case BimLayerScheme.ByLevelThenCategory:
                    return Root + "::" + LevelSegment(levelValue) + "::" + CategorySegment(category);

                case BimLayerScheme.Flat:
                default:
                    return Root + "::" + ModelLeaf;
            }
        }

        private static string CategorySegment(string? category)
        {
            var clean = Sanitize(category);
            return clean.Length == 0 ? OtherCategory : clean;
        }

        private static string LevelSegment(string? levelValue)
        {
            var clean = Sanitize(levelValue);
            return clean.Length == 0 ? NoLevel : clean;
        }

        // Collapse the "::" separator (and control chars) inside a single segment so a category or
        // level name can never alter the layer path's structure. Spaces are preserved (Rhino allows
        // them); ":" becomes "_".
        private static string Sanitize(string? value)
        {
            if (string.IsNullOrWhiteSpace(value))
            {
                return string.Empty;
            }

            var builder = new StringBuilder(value!.Length);
            foreach (var c in value.Trim())
            {
                if (c == ':' || char.IsControl(c))
                {
                    builder.Append('_');
                }
                else
                {
                    builder.Append(c);
                }
            }

            return builder.ToString();
        }
    }
}
