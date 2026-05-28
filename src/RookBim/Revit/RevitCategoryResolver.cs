using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Autodesk.Revit.DB;
using Rook.Bim;

namespace RookBim.Revit
{
    internal sealed class RevitCategoryResolver
    {
        private const int MaxSuggestions = 5;

        public BimListCategoriesResult List(Document document)
        {
            var table = LiveCategories(document);
            return new BimListCategoriesResult
            {
                Document = RevitIdentitySerializer.DocumentIdentity(document),
                SkippedCount = table.SkippedCount,
                DegradedCount = table.DegradedCount,
                Diagnostics = table.Diagnostics,
                Categories = table.Entries
                    .Select(entry => entry.Summary)
                    .OrderBy(category => category.Name, StringComparer.OrdinalIgnoreCase)
                    .ToList()
            };
        }

        public BimCategoryResolution Resolve(Document document, string? input)
        {
            var entries = LiveCategories(document).Entries;
            var resolution = new BimCategoryResolution
            {
                Input = input,
                NormalizedInput = Normalize(input),
                Document = RevitIdentitySerializer.DocumentIdentity(document)
            };

            if (string.IsNullOrWhiteSpace(input))
            {
                resolution.Suggestions = Suggestions(entries, string.Empty);
                return resolution;
            }

            var strategies = new[]
            {
                BimCategoryResolutionStrategy.BuiltInExact,
                BimCategoryResolutionStrategy.CategoryIdExact,
                BimCategoryResolutionStrategy.DocumentDisplayNameExact,
                BimCategoryResolutionStrategy.DocumentDisplayNameNormalized,
                BimCategoryResolutionStrategy.BuiltInTolerant,
                BimCategoryResolutionStrategy.CuratedAlias
            };

            foreach (var strategy in strategies)
            {
                resolution.AttemptedStrategies.Add(strategy);
                var matches = ResolveByStrategy(document, entries, input!, strategy).ToList();
                if (matches.Count == 0)
                {
                    continue;
                }

                if (matches.Count == 1)
                {
                    return Resolved(resolution, matches[0], strategy);
                }

                return Ambiguous(resolution, matches, strategy);
            }

            resolution.Suggestions = Suggestions(entries, input!);
            return resolution;
        }

        private static BimCategoryResolution Resolved(
            BimCategoryResolution resolution,
            CategoryEntry entry,
            BimCategoryResolutionStrategy strategy)
        {
            resolution.Status = BimCategoryResolutionStatus.Resolved;
            resolution.Strategy = strategy;
            resolution.Queryable = entry.Summary.Id.HasValue;
            resolution.Category = entry.Summary;
            return resolution;
        }

        private static BimCategoryResolution Ambiguous(
            BimCategoryResolution resolution,
            IReadOnlyCollection<CategoryEntry> entries,
            BimCategoryResolutionStrategy strategy)
        {
            resolution.Status = BimCategoryResolutionStatus.Ambiguous;
            resolution.Strategy = strategy;
            resolution.Ambiguous = true;
            resolution.Candidates = entries.Select(entry => entry.Summary).ToList();
            resolution.Suggestions = entries
                .Select(entry => Suggestion(entry, "ambiguous_match"))
                .Take(MaxSuggestions)
                .ToList();
            return resolution;
        }

        private static IEnumerable<CategoryEntry> ResolveByStrategy(
            Document document,
            IReadOnlyCollection<CategoryEntry> entries,
            string input,
            BimCategoryResolutionStrategy strategy)
        {
            switch (strategy)
            {
                case BimCategoryResolutionStrategy.BuiltInExact:
                    var exactBuiltIn = TryBuiltInExact(input);
                    return exactBuiltIn.HasValue
                        ? MatchResolvedBuiltIn(document, entries, exactBuiltIn.Value)
                        : Enumerable.Empty<CategoryEntry>();
                case BimCategoryResolutionStrategy.CategoryIdExact:
                    return TryCategoryId(input, out var id)
                        ? entries.Where(entry => entry.Id == id)
                        : Enumerable.Empty<CategoryEntry>();
                case BimCategoryResolutionStrategy.DocumentDisplayNameExact:
                    return entries.Where(entry => string.Equals(entry.Name, input.Trim(), StringComparison.OrdinalIgnoreCase));
                case BimCategoryResolutionStrategy.DocumentDisplayNameNormalized:
                    var normalizedInput = Normalize(input);
                    var singularInput = TrimTrailingPluralS(normalizedInput);
                    return entries.Where(entry =>
                        string.Equals(entry.NormalizedName, normalizedInput, StringComparison.OrdinalIgnoreCase) ||
                        string.Equals(TrimTrailingPluralS(entry.NormalizedName), singularInput, StringComparison.OrdinalIgnoreCase));
                case BimCategoryResolutionStrategy.BuiltInTolerant:
                    return MatchBuiltInTolerant(document, entries, input);
                case BimCategoryResolutionStrategy.CuratedAlias:
                    var alias = ResolveCuratedAlias(input);
                    return alias.HasValue
                        ? MatchResolvedBuiltIn(document, entries, alias.Value)
                        : Enumerable.Empty<CategoryEntry>();
                default:
                    return Enumerable.Empty<CategoryEntry>();
            }
        }

        private static BuiltInCategory? TryBuiltInExact(string input)
        {
            var value = input.Trim();
            if (TryCategoryId(value, out _))
            {
                return null;
            }

            if (!Enum.TryParse(value, false, out BuiltInCategory builtIn))
            {
                return null;
            }

            return Enum.IsDefined(typeof(BuiltInCategory), builtIn) ? builtIn : (BuiltInCategory?)null;
        }

        private static IEnumerable<CategoryEntry> MatchResolvedBuiltIn(
            Document document,
            IEnumerable<CategoryEntry> entries,
            BuiltInCategory builtIn)
        {
            var category = ResolveBuiltIn(document, builtIn);
            if (category == null)
            {
                return Enumerable.Empty<CategoryEntry>();
            }

            var id = SafeCategoryId(category);
            return id.HasValue
                ? entries.Where(entry => entry.Id == id.Value).Select(entry => WithBuiltIn(entry, builtIn.ToString()))
                : Enumerable.Empty<CategoryEntry>();
        }

        private static Category? ResolveBuiltIn(Document document, BuiltInCategory builtIn)
        {
            return TryGetBuiltInCategory(document, builtIn, out var category) ? category : null;
        }

        private static IEnumerable<CategoryEntry> MatchBuiltInTolerant(
            Document document,
            IReadOnlyCollection<CategoryEntry> entries,
            string input)
        {
            var requested = Normalize(input);
            var requestedSingular = TrimTrailingPluralS(requested);
            foreach (BuiltInCategory builtIn in Enum.GetValues(typeof(BuiltInCategory)))
            {
                if (!Enum.IsDefined(typeof(BuiltInCategory), builtIn))
                {
                    continue;
                }

                var name = builtIn.ToString();
                var withoutPrefix = name.StartsWith("OST_", StringComparison.OrdinalIgnoreCase)
                    ? name.Substring(4)
                    : name;
                var normalizedName = Normalize(name);
                var normalizedWithoutPrefix = Normalize(withoutPrefix);
                if (!string.Equals(normalizedName, requested, StringComparison.OrdinalIgnoreCase) &&
                    !string.Equals(normalizedWithoutPrefix, requested, StringComparison.OrdinalIgnoreCase) &&
                    !string.Equals(TrimTrailingPluralS(normalizedName), requestedSingular, StringComparison.OrdinalIgnoreCase) &&
                    !string.Equals(TrimTrailingPluralS(normalizedWithoutPrefix), requestedSingular, StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                return MatchResolvedBuiltIn(document, entries, builtIn);
            }

            return Enumerable.Empty<CategoryEntry>();
        }

        private static BuiltInCategory? ResolveCuratedAlias(string input)
        {
            var aliases = new Dictionary<string, BuiltInCategory>(StringComparer.OrdinalIgnoreCase)
            {
                ["Generic Models"] = BuiltInCategory.OST_GenericModel,
                ["Generic Model"] = BuiltInCategory.OST_GenericModel,
                ["GenericModels"] = BuiltInCategory.OST_GenericModel,
                ["Curtain Panels"] = BuiltInCategory.OST_CurtainWallPanels,
                ["Curtain Panel"] = BuiltInCategory.OST_CurtainWallPanels,
                ["CurtainPanels"] = BuiltInCategory.OST_CurtainWallPanels
            };

            var requested = Normalize(input);
            foreach (var alias in aliases)
            {
                var normalizedAlias = Normalize(alias.Key);
                if (string.Equals(normalizedAlias, requested, StringComparison.OrdinalIgnoreCase) ||
                    string.Equals(TrimTrailingPluralS(normalizedAlias), TrimTrailingPluralS(requested), StringComparison.OrdinalIgnoreCase))
                {
                    return alias.Value;
                }
            }

            return null;
        }

        private static CategoryEntry WithBuiltIn(CategoryEntry entry, string builtIn)
        {
            return new CategoryEntry(
                entry.Id,
                entry.Name,
                new BimCategorySummary
                {
                    Id = entry.Summary.Id,
                    Name = entry.Summary.Name,
                    BuiltIn = builtIn,
                    CategoryType = entry.Summary.CategoryType,
                    Parent = entry.Summary.Parent
                });
        }

        private static LiveCategoryTable LiveCategories(Document document)
        {
            var entries = new List<CategoryEntry>();
            var diagnostics = new CategoryTableDiagnosticsBuilder();
            foreach (Category category in document.Settings.Categories)
            {
                if (TryBuildCategoryEntry(category, diagnostics, out var entry))
                {
                    entries.Add(entry);
                }
            }

            return new LiveCategoryTable(
                entries,
                diagnostics.Build(),
                diagnostics.SkippedCount,
                diagnostics.DegradedCount);
        }

        private static bool TryBuildCategoryEntry(
            Category category,
            CategoryTableDiagnosticsBuilder diagnostics,
            out CategoryEntry entry)
        {
            entry = default;
            var id = SafeCategoryId(category);
            if (!id.HasValue)
            {
                diagnostics.RecordSkip("missing_id", "Category id could not be read.");
                return false;
            }

            var name = SafeCategoryName(category) ?? string.Empty;
            if (string.IsNullOrWhiteSpace(name))
            {
                diagnostics.RecordDegradation("missing_name", $"Category {id.Value} name could not be read.");
            }

            entry = new CategoryEntry(
                id.Value,
                name,
                new BimCategorySummary
                {
                    Id = id,
                    Name = NullIfWhiteSpace(name),
                    BuiltIn = SafeBuiltInCategory(category),
                    CategoryType = SafeCategoryType(category),
                    Parent = null
                });
            return true;
        }

        private static bool TryGetBuiltInCategory(
            Document document,
            BuiltInCategory builtIn,
            out Category category)
        {
            category = null!;
            if (!Enum.IsDefined(typeof(BuiltInCategory), builtIn))
            {
                return false;
            }

            try
            {
                category = Category.GetCategory(document, builtIn);
                return category != null;
            }
            catch (Autodesk.Revit.Exceptions.InternalException)
            {
                return false;
            }
            catch (Autodesk.Revit.Exceptions.ArgumentException)
            {
                return false;
            }
            catch (Autodesk.Revit.Exceptions.InvalidOperationException)
            {
                return false;
            }
            catch (ArgumentException)
            {
                return false;
            }
            catch (InvalidOperationException)
            {
                return false;
            }
        }

        private static string? SafeBuiltInCategory(Category category)
        {
            try
            {
                var builtIn = category.BuiltInCategory;
                if (builtIn == BuiltInCategory.INVALID || !Enum.IsDefined(typeof(BuiltInCategory), builtIn))
                {
                    return null;
                }

                return builtIn.ToString();
            }
            catch (Autodesk.Revit.Exceptions.InvalidOperationException)
            {
                return null;
            }
            catch (InvalidOperationException)
            {
                return null;
            }
        }

        private static string? SafeCategoryName(Category category)
        {
            try
            {
                return category.Name;
            }
            catch (Autodesk.Revit.Exceptions.InvalidOperationException)
            {
                return null;
            }
            catch (InvalidOperationException)
            {
                return null;
            }
        }

        private static string? SafeCategoryType(Category category)
        {
            try
            {
                return category.CategoryType.ToString();
            }
            catch (Autodesk.Revit.Exceptions.InvalidOperationException)
            {
                return null;
            }
            catch (InvalidOperationException)
            {
                return null;
            }
        }

        private static int? SafeCategoryId(Category category)
        {
            try
            {
                return ToInt32OrNull(category.Id);
            }
            catch (Autodesk.Revit.Exceptions.InvalidOperationException)
            {
                return null;
            }
            catch (InvalidOperationException)
            {
                return null;
            }
        }

        private static List<BimCategorySuggestion> Suggestions(
            IReadOnlyCollection<CategoryEntry> entries,
            string input)
        {
            var normalizedInput = Normalize(input);
            return entries
                .Select(entry => new
                {
                    Entry = entry,
                    Rank = SuggestionRank(entry, normalizedInput),
                    Reason = SuggestionReason(entry, normalizedInput)
                })
                .OrderBy(candidate => candidate.Rank)
                .ThenBy(candidate => candidate.Entry.Name, StringComparer.OrdinalIgnoreCase)
                .Take(MaxSuggestions)
                .Select(candidate => Suggestion(candidate.Entry, candidate.Reason))
                .ToList();
        }

        private static int SuggestionRank(CategoryEntry entry, string normalizedInput)
        {
            if (string.IsNullOrEmpty(normalizedInput))
            {
                return 1000;
            }

            if (string.Equals(entry.NormalizedName, normalizedInput, StringComparison.OrdinalIgnoreCase))
            {
                return 0;
            }

            if (string.Equals(TrimTrailingPluralS(entry.NormalizedName), TrimTrailingPluralS(normalizedInput), StringComparison.OrdinalIgnoreCase))
            {
                return 10;
            }

            if (entry.NormalizedName.StartsWith(normalizedInput, StringComparison.OrdinalIgnoreCase))
            {
                return 20 + Math.Abs(entry.NormalizedName.Length - normalizedInput.Length);
            }

            if (normalizedInput.StartsWith(entry.NormalizedName, StringComparison.OrdinalIgnoreCase))
            {
                return 40 + Math.Abs(entry.NormalizedName.Length - normalizedInput.Length);
            }

            if (entry.NormalizedName.IndexOf(normalizedInput, StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return 60 + Math.Abs(entry.NormalizedName.Length - normalizedInput.Length);
            }

            if (entry.Summary.BuiltIn != null &&
                Normalize(entry.Summary.BuiltIn).IndexOf(normalizedInput, StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return 100 + Math.Abs(Normalize(entry.Summary.BuiltIn).Length - normalizedInput.Length);
            }

            return 200 + Math.Min(
                EditDistance(entry.NormalizedName, normalizedInput),
                entry.Summary.BuiltIn == null
                    ? int.MaxValue
                    : EditDistance(Normalize(entry.Summary.BuiltIn), normalizedInput));
        }

        private static string SuggestionReason(CategoryEntry entry, string normalizedInput)
        {
            if (string.IsNullOrEmpty(normalizedInput))
            {
                return "live_document";
            }

            if (string.Equals(entry.NormalizedName, normalizedInput, StringComparison.OrdinalIgnoreCase))
            {
                return "exact_normalized_name";
            }

            if (string.Equals(TrimTrailingPluralS(entry.NormalizedName), TrimTrailingPluralS(normalizedInput), StringComparison.OrdinalIgnoreCase))
            {
                return "singular_plural_normalized_name";
            }

            if (entry.NormalizedName.StartsWith(normalizedInput, StringComparison.OrdinalIgnoreCase) ||
                normalizedInput.StartsWith(entry.NormalizedName, StringComparison.OrdinalIgnoreCase))
            {
                return "prefix_normalized_name";
            }

            if (entry.NormalizedName.IndexOf(normalizedInput, StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "contains_normalized_name";
            }

            if (entry.Summary.BuiltIn != null &&
                Normalize(entry.Summary.BuiltIn).IndexOf(normalizedInput, StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return "contains_built_in";
            }

            return "fuzzy_normalized_name";
        }

        private static int EditDistance(string left, string right)
        {
            if (left.Length == 0)
            {
                return right.Length;
            }

            if (right.Length == 0)
            {
                return left.Length;
            }

            var previous = new int[right.Length + 1];
            var current = new int[right.Length + 1];
            for (var column = 0; column <= right.Length; column++)
            {
                previous[column] = column;
            }

            for (var row = 1; row <= left.Length; row++)
            {
                current[0] = row;
                for (var column = 1; column <= right.Length; column++)
                {
                    var cost = left[row - 1] == right[column - 1] ? 0 : 1;
                    current[column] = Math.Min(
                        Math.Min(current[column - 1] + 1, previous[column] + 1),
                        previous[column - 1] + cost);
                }

                var temp = previous;
                previous = current;
                current = temp;
            }

            return previous[right.Length];
        }

        private static BimCategorySuggestion Suggestion(CategoryEntry entry, string reason)
        {
            return new BimCategorySuggestion
            {
                Id = entry.Summary.Id,
                Name = entry.Summary.Name,
                BuiltIn = entry.Summary.BuiltIn,
                Source = "live_document",
                MatchReason = reason
            };
        }

        private static bool TryCategoryId(string input, out int id)
        {
            return int.TryParse(input.Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out id);
        }

        private static string Normalize(string? value)
        {
            return (value ?? string.Empty)
                .Trim()
                .Replace(" ", string.Empty)
                .Replace("_", string.Empty)
                .Replace("-", string.Empty);
        }

        private static string TrimTrailingPluralS(string value)
        {
            return value.Length > 1 && value.EndsWith("s", StringComparison.OrdinalIgnoreCase)
                ? value.Substring(0, value.Length - 1)
                : value;
        }

        private static string? NullIfWhiteSpace(string? value)
        {
            return string.IsNullOrWhiteSpace(value) ? null : value;
        }

        private static int? ToInt32OrNull(ElementId? id)
        {
            if (id == null)
            {
                return null;
            }

            var value = id.Value;
            if (value < int.MinValue || value > int.MaxValue)
            {
                return null;
            }

            return (int)value;
        }

        private readonly struct CategoryEntry
        {
            public CategoryEntry(int id, string name, BimCategorySummary summary)
            {
                Id = id;
                Name = name;
                NormalizedName = Normalize(name);
                Summary = summary;
            }

            public int Id { get; }

            public string Name { get; }

            public string NormalizedName { get; }

            public BimCategorySummary Summary { get; }
        }

        private sealed class LiveCategoryTable
        {
            public LiveCategoryTable(
                IReadOnlyList<CategoryEntry> entries,
                BimCategoryTableDiagnostics diagnostics,
                int skippedCount,
                int degradedCount)
            {
                Entries = entries;
                Diagnostics = diagnostics;
                SkippedCount = skippedCount;
                DegradedCount = degradedCount;
            }

            public IReadOnlyList<CategoryEntry> Entries { get; }

            public BimCategoryTableDiagnostics Diagnostics { get; }

            public int SkippedCount { get; }

            public int DegradedCount { get; }
        }

        private sealed class CategoryTableDiagnosticsBuilder
        {
            private const int MaxExamples = 5;
            private readonly Dictionary<string, int> countsByReason =
                new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            private readonly List<string> examples = new List<string>();
            private int skippedCount;
            private int degradedCount;

            public int SkippedCount => skippedCount;

            public int DegradedCount => degradedCount;

            public void RecordSkip(string reason, string example)
            {
                skippedCount++;
                Record(reason, example);
            }

            public void RecordDegradation(string reason, string example)
            {
                degradedCount++;
                Record(reason, example);
            }

            private void Record(string reason, string example)
            {
                countsByReason.TryGetValue(reason, out var count);
                countsByReason[reason] = count + 1;
                if (examples.Count < MaxExamples)
                {
                    examples.Add($"{reason}: {example}");
                }
            }

            public BimCategoryTableDiagnostics Build()
            {
                return new BimCategoryTableDiagnostics
                {
                    CountsByReason = new Dictionary<string, int>(countsByReason, StringComparer.OrdinalIgnoreCase),
                    Examples = examples.ToList()
                };
            }
        }
    }
}
