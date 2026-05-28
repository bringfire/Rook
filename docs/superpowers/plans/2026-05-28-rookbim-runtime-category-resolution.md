# RookBIM Runtime Category Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic, document-scoped runtime category resolution for RookBIM and expose document-wide category listing through `rookbim_list_categories`.

**Architecture:** Revit remains the source of truth. `RevitCategoryResolver` resolves every successful category input back to a live `Document.Settings.Categories` entry before query application. The knowledge graph is not used in v1; the response contract reserves advisory fields for later read-only suggestions.

**Tech Stack:** C#/.NET Framework 4.8 shared contracts and Revit module, C++ RookNative proxy routes, Python MCP server/tool dispatcher, xUnit tests, pytest MCP tests.

---

## File Structure

- Modify `src/Rook/Bim/BimContracts.cs`: add category resolution DTOs, category summary fields, list-categories result, and new error codes.
- Modify `src/Rook/Bim/IRookBimRuntime.cs`: add `ListCategories()`.
- Modify `src/Rook/Bim/RookBimUnavailableRuntime.cs`: return unavailable for `ListCategories()`.
- Modify `src/Rook/Handlers/BimHandler.cs`: add `list_categories` op, map new error codes, and dispatch runtime list call.
- Modify `src/Rook.Tests/Bim/RookBimContractsTests.cs`: contract tests for category resolution and list result shape.
- Modify `src/Rook.Tests/Handlers/BimHandlerTests.cs`: op list, error mapping, and `details.resolution` envelope tests.
- Modify `src/Rook.Tests/Handlers/NativeBimDispatchSourceTests.cs`: native `/bim/categories` route source guard.
- Create `src/RookBim/Revit/RevitCategoryResolver.cs`: live document category listing and category resolution.
- Modify `src/RookBim/Revit/RevitQueryService.cs`: use resolver and include `query.categoryResolution`.
- Modify `src/RookBim/Revit/RevitRookBimRuntime.cs`: wire `ListCategories()` through the Revit dispatcher.
- Modify `src/RookBim.Tests/RookBimModuleSourceTests.cs`: source/structure tests for resolver and runtime wiring.
- Modify `src/RookNative/Handlers/GrasshopperProxyHandler.h`: declare `HandleBimCategories`.
- Modify `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`: implement `HandleBimCategories`.
- Modify `src/RookNative/RookServer.cpp`: register `GET /bim/categories`.
- Modify `mcp_server/src/rook/server.py`: schema, tool registration, and call routing for `rookbim_list_categories`.
- Modify `mcp_server/src/rook/agent/tool_dispatcher.py`: add bridge route.
- Modify `mcp_server/src/rook/agent/tool_groups.py`: add tool to `rookbim` and `rookbim_readonly`.
- Modify `mcp_server/src/rook/targeting.py`: add read targeting policy entries.
- Modify `mcp_server/src/rook/context.py`: classify tool as `document`.
- Modify `mcp_server/tests/test_rookbim_mcp_tools.py`: MCP schema, routing, groups, targeting, and context tests.

## Task 1: Shared BIM Contract Objects

**Files:**
- Modify: `src/Rook/Bim/BimContracts.cs`
- Test: `src/Rook.Tests/Bim/RookBimContractsTests.cs`

- [ ] **Step 1: Write failing contract tests**

Append these tests to `RookBimContractsTests`:

```csharp
[Fact]
public void CategoryResolution_RepresentsResolvedRuntimeCategory()
{
    var resolution = new BimCategoryResolution
    {
        SchemaVersion = 1,
        Status = BimCategoryResolutionStatus.Resolved,
        Input = "Pipes",
        NormalizedInput = "pipes",
        Strategy = BimCategoryResolutionStrategy.DocumentDisplayNameExact,
        Ambiguous = false,
        Queryable = true,
        AttemptedStrategies = new List<BimCategoryResolutionStrategy>
        {
            BimCategoryResolutionStrategy.BuiltInExact,
            BimCategoryResolutionStrategy.DocumentDisplayNameExact
        },
        Category = new BimCategorySummary
        {
            Id = -2008044,
            Name = "Pipes",
            BuiltIn = "OST_PipeCurves",
            CategoryType = "Model"
        },
        Document = new BimDocumentIdentity
        {
            Title = "Snowdon Towers Sample Plumbing",
            GuidSource = BimDocumentGuidSource.Unavailable,
            IsFamilyDocument = false
        }
    };

    Assert.Equal(1, resolution.SchemaVersion);
    Assert.Equal(BimCategoryResolutionStatus.Resolved, resolution.Status);
    Assert.Equal("OST_PipeCurves", resolution.Category!.BuiltIn);
    Assert.True(resolution.Queryable);
    Assert.Empty(resolution.AdvisorySources);
}

[Fact]
public void CategoryResolution_RepresentsInvalidAndAmbiguousResults()
{
    var invalid = new BimCategoryResolution
    {
        Status = BimCategoryResolutionStatus.Invalid,
        Strategy = BimCategoryResolutionStrategy.None,
        Input = "Pipe Accessoryz",
        NormalizedInput = "pipeaccessoryz",
        Suggestions = new List<BimCategorySuggestion>
        {
            new BimCategorySuggestion
            {
                Name = "Pipe Accessories",
                Id = -2008055,
                BuiltIn = "OST_PipeAccessory",
                Source = "live_document",
                MatchReason = "close_normalized_name"
            }
        }
    };
    var ambiguous = new BimCategoryResolution
    {
        Status = BimCategoryResolutionStatus.Ambiguous,
        Ambiguous = true,
        Candidates = new List<BimCategorySummary>
        {
            new BimCategorySummary { Id = -1, Name = "Lines" },
            new BimCategorySummary { Id = -2, Name = "Lines" }
        }
    };

    Assert.Single(invalid.Suggestions);
    Assert.Equal("close_normalized_name", invalid.Suggestions[0].MatchReason);
    Assert.True(ambiguous.Ambiguous);
    Assert.Equal(2, ambiguous.Candidates.Count);
}

[Fact]
public void ListCategoriesResult_UsesDocumentWideCategoryTableShape()
{
    var result = new BimListCategoriesResult
    {
        SchemaVersion = 1,
        Source = "document_category_table",
        Document = new BimDocumentIdentity { Title = "Family.rfa", IsFamilyDocument = true },
        Categories = new List<BimCategorySummary>
        {
            new BimCategorySummary
            {
                Id = -2000240,
                Name = "Levels",
                BuiltIn = "OST_Levels",
                CategoryType = "Model",
                Parent = new BimCategoryParentSummary
                {
                    Id = -2000000,
                    Name = "Parent",
                    BuiltIn = null
                }
            }
        }
    };

    Assert.Equal("document_category_table", result.Source);
    Assert.True(result.Document.IsFamilyDocument);
    Assert.Equal("Parent", result.Categories[0].Parent!.Name);
}
```

- [ ] **Step 2: Run contract tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~RookBimContractsTests
```

Expected: compile failures for missing `BimCategoryResolution`, `BimCategoryResolutionStatus`, `BimCategoryResolutionStrategy`, `BimCategorySuggestion`, `BimListCategoriesResult`, and category summary fields.

- [ ] **Step 3: Add contract types**

In `BimContracts.cs`, add error codes:

```csharp
AmbiguousCategory,
CategoryNotQueryable,
```

Add these contract types near the existing category/query DTOs:

```csharp
public enum BimCategoryResolutionStatus
{
    Resolved,
    Invalid,
    Ambiguous
}

public enum BimCategoryResolutionStrategy
{
    None,
    BuiltInExact,
    CategoryIdExact,
    DocumentDisplayNameExact,
    DocumentDisplayNameNormalized,
    BuiltInTolerant,
    CuratedAlias
}

public sealed class BimCategoryParentSummary
{
    public int? Id { get; set; }

    public string? Name { get; set; }

    public string? BuiltIn { get; set; }
}
```

Extend `BimCategorySummary`:

```csharp
public sealed class BimCategorySummary
{
    public int? Id { get; set; }

    public string? Name { get; set; }

    public string? BuiltIn { get; set; }

    public string? CategoryType { get; set; }

    public BimCategoryParentSummary? Parent { get; set; }
}
```

Add:

```csharp
public sealed class BimCategorySuggestion
{
    public int? Id { get; set; }

    public string? Name { get; set; }

    public string? BuiltIn { get; set; }

    public string Source { get; set; } = "live_document";

    public string? MatchReason { get; set; }
}

public sealed class BimCategoryResolution
{
    public int SchemaVersion { get; set; } = 1;

    public BimCategoryResolutionStatus Status { get; set; } = BimCategoryResolutionStatus.Invalid;

    public string? Input { get; set; }

    public string? NormalizedInput { get; set; }

    public List<BimCategoryResolutionStrategy> AttemptedStrategies { get; set; } =
        new List<BimCategoryResolutionStrategy>();

    public BimCategoryResolutionStrategy Strategy { get; set; } = BimCategoryResolutionStrategy.None;

    public bool Ambiguous { get; set; }

    public bool? Queryable { get; set; }

    public BimCategorySummary? Category { get; set; }

    public BimDocumentIdentity Document { get; set; } = new BimDocumentIdentity();

    public List<BimCategorySummary> Candidates { get; set; } = new List<BimCategorySummary>();

    public List<BimCategorySuggestion> Suggestions { get; set; } = new List<BimCategorySuggestion>();

    public List<string> AdvisorySources { get; set; } = new List<string>();
}

public sealed class BimListCategoriesResult
{
    public int SchemaVersion { get; set; } = 1;

    public string Source { get; set; } = "document_category_table";

    public BimDocumentIdentity Document { get; set; } = new BimDocumentIdentity();

    public List<BimCategorySummary> Categories { get; set; } = new List<BimCategorySummary>();
}
```

Extend `BimQuerySummary`:

```csharp
public BimCategoryResolution? CategoryResolution { get; set; }
```

- [ ] **Step 4: Run contract tests and verify they pass**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~RookBimContractsTests
```

Expected: all filtered tests pass.

## Task 2: Managed BIM Handler and Runtime Interface

**Files:**
- Modify: `src/Rook/Bim/IRookBimRuntime.cs`
- Modify: `src/Rook/Bim/RookBimUnavailableRuntime.cs`
- Modify: `src/Rook/Handlers/BimHandler.cs`
- Test: `src/Rook.Tests/Handlers/BimHandlerTests.cs`
- Test: `src/Rook.Tests/Bim/RookBimUnavailableRuntimeTests.cs`

- [ ] **Step 1: Write failing handler tests**

Update `BimHandlerTests.Phase1Ops` or equivalent expected op list to include:

```csharp
"list_categories",
```

Add:

```csharp
[Fact]
public void Dispatch_ListCategories_UsesRuntime()
{
    RookBimRuntimeRegistry.Install(new DetailFailureRuntime(), "test-list-categories");
    try
    {
        var handler = new BimHandler();
        var response = handler.Dispatch("{\"op\":\"list_categories\"}");

        Assert.True(response.Success);
        Assert.Contains("document_category_table", response.Data!.ToJsonString());
    }
    finally
    {
        RookBimRuntimeRegistry.ResetForTests();
    }
}

[Fact]
public void MapErrorCode_MapsCategoryResolutionErrors()
{
    Assert.Equal("ambiguous_category", BimHandler.MapErrorCode(BimErrorCode.AmbiguousCategory));
    Assert.Equal("category_not_queryable", BimHandler.MapErrorCode(BimErrorCode.CategoryNotQueryable));
}

[Fact]
public void Dispatch_CategoryFailure_PreservesResolutionUnderDetails()
{
    RookBimRuntimeRegistry.Install(new CategoryFailureRuntime(), "test-category-failure");
    try
    {
        var handler = new BimHandler();
        var response = handler.Dispatch("{\"op\":\"query_elements\",\"scope\":\"document\",\"category\":\"Pipe Accessoryz\"}");
        var json = response.Data!.ToJsonString();

        Assert.False(response.Success);
        Assert.Contains("\"errorCode\":\"invalid_category\"", json);
        Assert.Contains("\"details\":{\"resolution\":", json);
        Assert.Contains("\"status\":\"invalid\"", json);
        Assert.Contains("\"input\":\"Pipe Accessoryz\"", json);
    }
    finally
    {
        RookBimRuntimeRegistry.ResetForTests();
    }
}
```

Extend the private `DetailFailureRuntime` test double:

```csharp
public BimApiResponse ListCategories()
{
    return BimApiResponse.Ok(new BimListCategoriesResult
    {
        Source = "document_category_table"
    });
}
```

Add this private test runtime:

```csharp
private sealed class CategoryFailureRuntime : IRookBimRuntime
{
    public BimStatusResponse Status()
    {
        return new BimStatusResponse { Available = true, Runtime = "test" };
    }

    public BimApiResponse ActiveDocument()
    {
        return BimApiResponse.Ok(null);
    }

    public BimApiResponse ListCategories()
    {
        return BimApiResponse.Ok(null);
    }

    public BimApiResponse QueryElements(BimQueryElementsRequest request)
    {
        var response = BimApiResponse.Fail(
            BimErrorCode.InvalidCategory,
            "Unknown Revit category 'Pipe Accessoryz'.",
            400);
        response.Data = new
        {
            resolution = new BimCategoryResolution
            {
                Status = BimCategoryResolutionStatus.Invalid,
                Input = "Pipe Accessoryz",
                NormalizedInput = "pipeaccessoryz"
            }
        };
        return response;
    }

    public BimApiResponse ElementInfo(BimElementRequest request)
    {
        return BimApiResponse.Ok(null);
    }

    public BimApiResponse ElementParameters(BimElementRequest request)
    {
        return BimApiResponse.Ok(null);
    }

    public BimApiResponse SelectElements(BimSelectElementsRequest request)
    {
        return BimApiResponse.Ok(null);
    }

    public BimApiResponse ClearSelection()
    {
        return BimApiResponse.Ok(null);
    }
}
```

Update `RookBimUnavailableRuntimeTests` to assert `ListCategories()` returns unavailable:

```csharp
AssertUnavailable(runtime.ListCategories(), configuredMessage);
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~BimHandlerTests|FullyQualifiedName~RookBimUnavailableRuntimeTests"
```

Expected: compile failures for missing `ListCategories()` and missing error-code mapping.

- [ ] **Step 3: Implement interface and handler wiring**

In `IRookBimRuntime.cs`, add:

```csharp
BimApiResponse ListCategories();
```

In `RookBimUnavailableRuntime.cs`, add:

```csharp
public BimApiResponse ListCategories()
{
    return Unavailable();
}
```

In `BimHandler.ExpectedBimOps`, add:

```csharp
"list_categories",
```

In the dispatch switch, add:

```csharp
"list_categories" => FromBimResponse(runtime.ListCategories()),
```

In `MapErrorCode`, add:

```csharp
BimErrorCode.AmbiguousCategory => "ambiguous_category",
BimErrorCode.CategoryNotQueryable => "category_not_queryable",
```

- [ ] **Step 4: Run managed handler tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~BimHandlerTests|FullyQualifiedName~RookBimUnavailableRuntimeTests"
```

Expected: all filtered tests pass.

## Task 3: Revit Category Resolver Source and Runtime Wiring

**Files:**
- Create: `src/RookBim/Revit/RevitCategoryResolver.cs`
- Modify: `src/RookBim/Revit/RevitRookBimRuntime.cs`
- Test: `src/RookBim.Tests/RookBimModuleSourceTests.cs`

- [ ] **Step 1: Write failing source tests**

Add tests to `RookBimModuleSourceTests`:

```csharp
[Fact]
public void RevitCategoryResolver_UsesLiveDocumentCategoryTableAsAuthority()
{
    var resolver = Read("src/RookBim/Revit/RevitCategoryResolver.cs");

    Assert.Contains("internal sealed class RevitCategoryResolver", resolver);
    Assert.Contains("document.Settings.Categories", resolver);
    Assert.Contains("BimCategoryResolution", resolver);
    Assert.Contains("BimCategoryResolutionStrategy.BuiltInExact", resolver);
    Assert.Contains("BimCategoryResolutionStrategy.CategoryIdExact", resolver);
    Assert.Contains("BimCategoryResolutionStrategy.DocumentDisplayNameExact", resolver);
    Assert.Contains("BimCategoryResolutionStrategy.DocumentDisplayNameNormalized", resolver);
    Assert.Contains("BimCategoryResolutionStrategy.BuiltInTolerant", resolver);
    Assert.Contains("BimCategoryResolutionStrategy.CuratedAlias", resolver);
    Assert.Contains("MaxSuggestions = 5", resolver);
    Assert.Contains("BimCategoryResolutionStatus.Ambiguous", resolver);
    Assert.Contains("Queryable = true", resolver);
    Assert.DoesNotContain("knowledge", resolver, StringComparison.OrdinalIgnoreCase);
}

[Fact]
public void RevitRuntime_WiresListCategoriesThroughDispatcher()
{
    var runtime = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");
    var listCategories = ExtractMethod(runtime, "public BimApiResponse ListCategories(");

    Assert.Contains("private readonly RevitCategoryResolver categories;", runtime);
    Assert.Contains("this.categories = new RevitCategoryResolver();", runtime);
    Assert.Contains("return Dispatch(uiapp =>", listCategories);
    Assert.Contains("RevitContext.ActiveUiDocument(uiapp)", listCategories);
    Assert.Contains("BimErrorCode.NoActiveDocument", listCategories);
    Assert.Contains("categories.List(document)", listCategories);
}
```

- [ ] **Step 2: Run source tests and verify they fail**

Run:

```powershell
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --no-restore --filter "FullyQualifiedName~RevitCategoryResolver|FullyQualifiedName~ListCategories"
```

Expected: failure because `RevitCategoryResolver.cs` and runtime wiring do not exist.

- [ ] **Step 3: Create resolver skeleton**

Create `RevitCategoryResolver.cs`:

```csharp
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
            return new BimListCategoriesResult
            {
                Document = RevitIdentitySerializer.DocumentIdentity(document),
                Categories = LiveCategories(document)
                    .Select(item => item.Summary)
                    .OrderBy(category => category.Name, StringComparer.OrdinalIgnoreCase)
                    .ToList()
            };
        }

        public BimCategoryResolution Resolve(Document document, string? input)
        {
            var resolution = NewResolution(document, input);
            if (string.IsNullOrWhiteSpace(input))
            {
                resolution.Suggestions = Suggestions(LiveCategories(document), string.Empty);
                return resolution;
            }

            var live = LiveCategories(document);
            TryBuiltInExact(document, live, resolution);
            if (resolution.Status == BimCategoryResolutionStatus.Resolved)
                return resolution;

            TryCategoryIdExact(live, resolution);
            if (resolution.Status == BimCategoryResolutionStatus.Resolved)
                return resolution;

            TryDisplayNameExact(live, resolution);
            if (resolution.Status != BimCategoryResolutionStatus.Invalid)
                return resolution;

            TryDisplayNameNormalized(live, resolution);
            if (resolution.Status != BimCategoryResolutionStatus.Invalid)
                return resolution;

            TryBuiltInTolerant(document, live, resolution);
            if (resolution.Status == BimCategoryResolutionStatus.Resolved)
                return resolution;

            TryCuratedAlias(document, live, resolution);
            if (resolution.Status == BimCategoryResolutionStatus.Resolved)
                return resolution;

            resolution.Suggestions = Suggestions(live, resolution.NormalizedInput ?? string.Empty);
            return resolution;
        }

        private static BimCategoryResolution NewResolution(Document document, string? input)
        {
            return new BimCategoryResolution
            {
                Input = input,
                NormalizedInput = Normalize(input),
                Document = RevitIdentitySerializer.DocumentIdentity(document),
                Strategy = BimCategoryResolutionStrategy.None,
                Status = BimCategoryResolutionStatus.Invalid,
                Ambiguous = false,
                Queryable = null
            };
        }

        private static IReadOnlyList<LiveCategory> LiveCategories(Document document)
        {
            var result = new List<LiveCategory>();
            foreach (Category category in document.Settings.Categories)
            {
                var summary = Summary(category);
                result.Add(new LiveCategory(category, summary, Normalize(summary.Name)));
            }
            return result;
        }

        private static BimCategorySummary Summary(Category category)
        {
            var builtIn = TryBuiltIn(category);
            return new BimCategorySummary
            {
                Id = ToInt32OrNull(category.Id),
                Name = NullIfWhiteSpace(category.Name),
                BuiltIn = builtIn,
                CategoryType = category.CategoryType.ToString(),
                Parent = category.Parent == null ? null : new BimCategoryParentSummary
                {
                    Id = ToInt32OrNull(category.Parent.Id),
                    Name = NullIfWhiteSpace(category.Parent.Name),
                    BuiltIn = TryBuiltIn(category.Parent)
                }
            };
        }

        private static void TryBuiltInExact(Document document, IReadOnlyList<LiveCategory> live, BimCategoryResolution resolution)
        {
            resolution.AttemptedStrategies.Add(BimCategoryResolutionStrategy.BuiltInExact);
            if (int.TryParse(resolution.Input, NumberStyles.Integer, CultureInfo.InvariantCulture, out _))
                return;
            if (!Enum.TryParse(resolution.Input, true, out BuiltInCategory builtIn))
                return;
            if (!Enum.IsDefined(typeof(BuiltInCategory), builtIn))
                return;
            ResolveBuiltIn(document, live, builtIn, resolution, BimCategoryResolutionStrategy.BuiltInExact);
        }

        private static void TryCategoryIdExact(IReadOnlyList<LiveCategory> live, BimCategoryResolution resolution)
        {
            resolution.AttemptedStrategies.Add(BimCategoryResolutionStrategy.CategoryIdExact);
            if (!int.TryParse(resolution.Input, NumberStyles.Integer, CultureInfo.InvariantCulture, out var id))
                return;
            var matches = live.Where(item => item.Summary.Id == id).ToList();
            ApplyMatches(matches, resolution, BimCategoryResolutionStrategy.CategoryIdExact);
        }

        private static void TryDisplayNameExact(IReadOnlyList<LiveCategory> live, BimCategoryResolution resolution)
        {
            resolution.AttemptedStrategies.Add(BimCategoryResolutionStrategy.DocumentDisplayNameExact);
            var matches = live
                .Where(item => string.Equals(item.Summary.Name, resolution.Input?.Trim(), StringComparison.OrdinalIgnoreCase))
                .ToList();
            ApplyMatches(matches, resolution, BimCategoryResolutionStrategy.DocumentDisplayNameExact);
        }

        private static void TryDisplayNameNormalized(IReadOnlyList<LiveCategory> live, BimCategoryResolution resolution)
        {
            resolution.AttemptedStrategies.Add(BimCategoryResolutionStrategy.DocumentDisplayNameNormalized);
            var normalized = resolution.NormalizedInput ?? string.Empty;
            var singular = TrimTrailingPluralS(normalized);
            var matches = live
                .Where(item => string.Equals(item.NormalizedName, normalized, StringComparison.OrdinalIgnoreCase) ||
                    string.Equals(TrimTrailingPluralS(item.NormalizedName), singular, StringComparison.OrdinalIgnoreCase))
                .ToList();
            ApplyMatches(matches, resolution, BimCategoryResolutionStrategy.DocumentDisplayNameNormalized);
        }

        private static void TryBuiltInTolerant(Document document, IReadOnlyList<LiveCategory> live, BimCategoryResolution resolution)
        {
            resolution.AttemptedStrategies.Add(BimCategoryResolutionStrategy.BuiltInTolerant);
            var requested = resolution.NormalizedInput ?? string.Empty;
            foreach (BuiltInCategory builtIn in Enum.GetValues(typeof(BuiltInCategory)))
            {
                var name = builtIn.ToString();
                var withoutPrefix = name.StartsWith("OST_", StringComparison.OrdinalIgnoreCase)
                    ? name.Substring(4)
                    : name;
                if (string.Equals(Normalize(name), requested, StringComparison.OrdinalIgnoreCase) ||
                    string.Equals(Normalize(withoutPrefix), requested, StringComparison.OrdinalIgnoreCase))
                {
                    ResolveBuiltIn(document, live, builtIn, resolution, BimCategoryResolutionStrategy.BuiltInTolerant);
                    return;
                }
            }
        }

        private static void TryCuratedAlias(Document document, IReadOnlyList<LiveCategory> live, BimCategoryResolution resolution)
        {
            resolution.AttemptedStrategies.Add(BimCategoryResolutionStrategy.CuratedAlias);
            var aliases = new Dictionary<string, BuiltInCategory>(StringComparer.OrdinalIgnoreCase)
            {
                ["Generic Models"] = BuiltInCategory.OST_GenericModel,
                ["Generic Model"] = BuiltInCategory.OST_GenericModel,
                ["Curtain Panels"] = BuiltInCategory.OST_CurtainWallPanels,
                ["Curtain Panel"] = BuiltInCategory.OST_CurtainWallPanels
            };
            foreach (var alias in aliases)
            {
                if (string.Equals(Normalize(alias.Key), resolution.NormalizedInput, StringComparison.OrdinalIgnoreCase))
                {
                    ResolveBuiltIn(document, live, alias.Value, resolution, BimCategoryResolutionStrategy.CuratedAlias);
                    return;
                }
            }
        }

        private static void ResolveBuiltIn(
            Document document,
            IReadOnlyList<LiveCategory> live,
            BuiltInCategory builtIn,
            BimCategoryResolution resolution,
            BimCategoryResolutionStrategy strategy)
        {
            if (!Enum.IsDefined(typeof(BuiltInCategory), builtIn))
                return;
            var category = Category.GetCategory(document, builtIn);
            if (category == null)
                return;
            var id = ToInt32OrNull(category.Id);
            var matches = live.Where(item => item.Summary.Id == id).ToList();
            ApplyMatches(matches, resolution, strategy);
        }

        private static void ApplyMatches(
            IReadOnlyList<LiveCategory> matches,
            BimCategoryResolution resolution,
            BimCategoryResolutionStrategy strategy)
        {
            if (matches.Count == 0)
                return;
            if (matches.Count > 1)
            {
                resolution.Status = BimCategoryResolutionStatus.Ambiguous;
                resolution.Ambiguous = true;
                resolution.Candidates = matches.Select(item => item.Summary).ToList();
                resolution.Strategy = strategy;
                return;
            }

            resolution.Status = BimCategoryResolutionStatus.Resolved;
            resolution.Ambiguous = false;
            resolution.Category = matches[0].Summary;
            resolution.Strategy = strategy;
            resolution.Queryable = true;
        }

        private static List<BimCategorySuggestion> Suggestions(IReadOnlyList<LiveCategory> live, string normalizedInput)
        {
            return live
                .Where(item => !string.IsNullOrWhiteSpace(item.Summary.Name))
                .OrderByDescending(item => Score(item.NormalizedName, normalizedInput))
                .ThenBy(item => item.Summary.Name, StringComparer.OrdinalIgnoreCase)
                .Take(MaxSuggestions)
                .Select(item => new BimCategorySuggestion
                {
                    Id = item.Summary.Id,
                    Name = item.Summary.Name,
                    BuiltIn = item.Summary.BuiltIn,
                    Source = "live_document",
                    MatchReason = "close_normalized_name"
                })
                .ToList();
        }

        private static int Score(string candidate, string input)
        {
            if (string.IsNullOrWhiteSpace(input))
                return 0;
            if (candidate.IndexOf(input, StringComparison.OrdinalIgnoreCase) >= 0)
                return input.Length;
            return candidate.Zip(input, (left, right) => char.ToUpperInvariant(left) == char.ToUpperInvariant(right) ? 1 : 0).Sum();
        }

        private static string Normalize(string? value)
        {
            return (value ?? string.Empty)
                .Trim()
                .Replace(" ", string.Empty)
                .Replace("_", string.Empty)
                .Replace("-", string.Empty)
                .ToLowerInvariant();
        }

        private static string TrimTrailingPluralS(string value)
        {
            return value.Length > 1 && value.EndsWith("s", StringComparison.OrdinalIgnoreCase)
                ? value.Substring(0, value.Length - 1)
                : value;
        }

        private static string? TryBuiltIn(Category category)
        {
            var id = ToInt32OrNull(category.Id);
            if (!id.HasValue)
                return null;
            return Enum.IsDefined(typeof(BuiltInCategory), id.Value)
                ? ((BuiltInCategory)id.Value).ToString()
                : null;
        }

        private static int? ToInt32OrNull(ElementId? id)
        {
            if (id == null)
                return null;
            var value = id.Value;
            return value < int.MinValue || value > int.MaxValue ? (int?)null : (int)value;
        }

        private static string? NullIfWhiteSpace(string? value)
        {
            return string.IsNullOrWhiteSpace(value) ? null : value;
        }

        private sealed class LiveCategory
        {
            public LiveCategory(Category category, BimCategorySummary summary, string normalizedName)
            {
                Category = category;
                Summary = summary;
                NormalizedName = normalizedName;
            }

            public Category Category { get; }

            public BimCategorySummary Summary { get; }

            public string NormalizedName { get; }
        }
    }
}
```

- [ ] **Step 4: Wire runtime list method**

In `RevitRookBimRuntime`, add field initialization:

```csharp
private readonly RevitCategoryResolver categories;
```

In the constructor:

```csharp
this.categories = new RevitCategoryResolver();
```

Add method:

```csharp
public BimApiResponse ListCategories()
{
    try
    {
        return Dispatch(uiapp =>
        {
            var uidoc = RevitContext.ActiveUiDocument(uiapp);
            if (uidoc == null || uidoc.Document == null)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.NoActiveDocument,
                    "No active Revit document is open.",
                    409);
            }

            return BimApiResponse.Ok(categories.List(uidoc.Document));
        });
    }
    catch (Exception ex)
    {
        return BimApiResponse.Fail(
            BimErrorCode.NotRhinoInside,
            $"RookBIM could not enter the Revit API context: {DescribeDispatchException(ex)}",
            503);
    }
}
```

- [ ] **Step 5: Run RookBIM source tests**

Run:

```powershell
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --no-restore --filter "FullyQualifiedName~RevitCategoryResolver|FullyQualifiedName~ListCategories"
```

Expected: filtered tests pass.

## Task 4: Query Service Uses Runtime Resolver

**Files:**
- Modify: `src/RookBim/Revit/RevitQueryService.cs`
- Test: `src/RookBim.Tests/RookBimModuleSourceTests.cs`

- [ ] **Step 1: Write failing source test**

Add:

```csharp
[Fact]
public void RevitQueryService_UsesCategoryResolverAndReturnsResolutionEvidence()
{
    var service = Read("src/RookBim/Revit/RevitQueryService.cs");
    var query = ExtractMethod(service, "public BimApiResponse Query(");

    Assert.Contains("private readonly RevitCategoryResolver categories", service);
    Assert.Contains("categories.Resolve(document, categoryName)", query);
    Assert.Contains("BimErrorCode.AmbiguousCategory", query);
    Assert.Contains("BimErrorCode.CategoryNotQueryable", query);
    Assert.Contains("Data = new { resolution = resolution }", service);
    Assert.Contains("CategoryResolution = categoryResolution", service);
    Assert.DoesNotContain("ResolveBuiltInCategory", service);
}
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --no-restore --filter FullyQualifiedName~RevitQueryService_UsesCategoryResolverAndReturnsResolutionEvidence
```

Expected: fails because query service still uses `ResolveBuiltInCategory`.

- [ ] **Step 3: Update query service**

Add field:

```csharp
private readonly RevitCategoryResolver categories = new RevitCategoryResolver();
```

In `Query`, declare before category handling:

```csharp
BimCategoryResolution? categoryResolution = null;
```

Replace current category resolution block with:

```csharp
if (!string.IsNullOrWhiteSpace(request.Category))
{
    var categoryName = request.Category!;
    var resolution = categories.Resolve(document, categoryName);
    categoryResolution = resolution;

    if (resolution.Status == BimCategoryResolutionStatus.Ambiguous)
    {
        var response = BimApiResponse.Fail(
            BimErrorCode.AmbiguousCategory,
            $"Category '{categoryName}' matched multiple live Revit categories.",
            400);
        response.Data = new { resolution = resolution };
        return response;
    }

    if (resolution.Status != BimCategoryResolutionStatus.Resolved || resolution.Category?.Id == null)
    {
        var response = BimApiResponse.Fail(
            BimErrorCode.InvalidCategory,
            $"Unknown Revit category '{categoryName}'.",
            400);
        response.Data = new { resolution = resolution };
        return response;
    }

    if (!TryResolvedBuiltInCategory(resolution, out var builtInCategory))
    {
        resolution.Queryable = false;
        var response = BimApiResponse.Fail(
            BimErrorCode.CategoryNotQueryable,
            $"Revit category '{resolution.Category.Name ?? categoryName}' is available in the document but cannot be safely used for element collection.",
            400);
        response.Data = new { resolution = resolution };
        return response;
    }

    try
    {
        collector.OfCategory(builtInCategory);
    }
    catch (Autodesk.Revit.Exceptions.ArgumentException)
    {
        resolution.Queryable = false;
        var response = BimApiResponse.Fail(
            BimErrorCode.CategoryNotQueryable,
            $"Revit category '{resolution.Category.Name ?? categoryName}' is available in the document but cannot be safely used for element collection.",
            400);
        response.Data = new { resolution = resolution };
        return response;
    }
    catch (ArgumentException)
    {
        resolution.Queryable = false;
        var response = BimApiResponse.Fail(
            BimErrorCode.CategoryNotQueryable,
            $"Revit category '{resolution.Category.Name ?? categoryName}' is available in the document but cannot be safely used for element collection.",
            400);
        response.Data = new { resolution = resolution };
        return response;
    }
}
```

Change `BuildResult` signature to accept `BimCategoryResolution? categoryResolution`, and set:

```csharp
CategoryResolution = categoryResolution,
```

Pass `categoryResolution` from both unfiltered and filtered result paths.

Delete `ResolveBuiltInCategory`, `NormalizeCategoryCandidate`, and `TrimTrailingPluralS` from `RevitQueryService` after the new resolver owns that logic.

Add this helper in `RevitQueryService`:

```csharp
private static bool TryResolvedBuiltInCategory(
    BimCategoryResolution resolution,
    out BuiltInCategory builtInCategory)
{
    builtInCategory = default;
    var builtIn = resolution.Category?.BuiltIn;
    if (string.IsNullOrWhiteSpace(builtIn))
    {
        return false;
    }

    if (!Enum.TryParse(builtIn, false, out builtInCategory))
    {
        return false;
    }

    return Enum.IsDefined(typeof(BuiltInCategory), builtInCategory);
}
```

- [ ] **Step 4: Run query source test**

Run:

```powershell
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --no-restore --filter FullyQualifiedName~RevitQueryService_UsesCategoryResolverAndReturnsResolutionEvidence
```

Expected: test passes.

- [ ] **Step 5: Run RookBIM tests**

Run:

```powershell
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --no-restore
```

Expected: all RookBIM tests pass.

## Task 5: Native BIM Categories Route

**Files:**
- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.h`
- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`
- Modify: `src/RookNative/RookServer.cpp`
- Test: `src/Rook.Tests/Handlers/NativeBimDispatchSourceTests.cs`

- [ ] **Step 1: Write failing native source test**

Add inline data to `RookServer_RegistersBimRoutesWithCanonicalOps`:

```csharp
[InlineData("Get", "/bim/categories", "HandleBimCategories", "list_categories")]
```

- [ ] **Step 2: Run source test and verify it fails**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~NativeBimDispatchSourceTests
```

Expected: fails because `/bim/categories` is not registered or forwarded.

- [ ] **Step 3: Add native handler**

In `GrasshopperProxyHandler.h`, add:

```cpp
void HandleBimCategories(const httplib::Request& req, httplib::Response& res);
```

In `GrasshopperProxyHandler.cpp`, add near `HandleBimActiveDocument`:

```cpp
void HandleBimCategories(const httplib::Request& req, httplib::Response& res)
{
    ForwardBimDispatch(req, res, "list_categories", nlohmann::json::object());
}
```

In `RookServer.cpp`, register:

```cpp
m_server->Get("/bim/categories", Rook::Handlers::HandleBimCategories);
```

- [ ] **Step 4: Run native source tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter FullyQualifiedName~NativeBimDispatchSourceTests
```

Expected: tests pass.

## Task 6: MCP Tool Surface

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/src/rook/targeting.py`
- Modify: `mcp_server/src/rook/context.py`
- Test: `mcp_server/tests/test_rookbim_mcp_tools.py`

- [ ] **Step 1: Write failing MCP tests**

In `ROOKBIM_TOOL_ROUTES`, add:

```python
"rookbim_list_categories": ("/bim/categories", "GET"),
```

In `ROOKBIM_READONLY_TOOLS`, add:

```python
"rookbim_list_categories",
```

Update the closed schema test loop to include `rookbim_list_categories`:

```python
for name in ("rookbim_status", "rookbim_active_document", "rookbim_list_categories", "rookbim_clear_selection"):
```

No request body entry is needed for `rookbim_list_categories`; it should behave like the other GET port-only tools.

- [ ] **Step 2: Run MCP tests and verify they fail**

Run:

```powershell
Push-Location mcp_server
uv run --extra test pytest tests\test_rookbim_mcp_tools.py -v
Pop-Location
```

Expected: fails because the new tool is not registered or routed.

- [ ] **Step 3: Add MCP server tool**

In `server.py`, add a `Tool` in the RookBIM section:

```python
Tool(
    name="rookbim_list_categories",
    description="Return document-wide Revit categories available in the active document category table.",
    inputSchema=_rookbim_empty_input_schema(),
),
```

In `call_tool` match section, add:

```python
case "rookbim_list_categories":
    result = await call_rhino("/bim/categories", "GET", None, port=port)
```

In `tool_dispatcher.BRIDGE_ROUTES`, add:

```python
"rookbim_list_categories":    ("/bim/categories", "GET"),
```

In `tool_groups.py`, add `rookbim_list_categories` to both `rookbim` and `rookbim_readonly`.

In `targeting.py`, add `rookbim_list_categories` to the read tool sets beside `rookbim_active_document`.

In `context.py`, add:

```python
"rookbim_list_categories": "document",
```

- [ ] **Step 4: Run MCP tests**

Run:

```powershell
Push-Location mcp_server
uv run --extra test pytest tests\test_rookbim_mcp_tools.py -v
Pop-Location
```

Expected: all `test_rookbim_mcp_tools.py` tests pass.

## Task 7: Full Local Verification

**Files:**
- No new source edits unless verification exposes failures.

- [ ] **Step 1: Run managed Rook tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~RookBimContractsTests|FullyQualifiedName~BimHandlerTests|FullyQualifiedName~NativeBimDispatchSourceTests|FullyQualifiedName~RookBimUnavailableRuntimeTests"
```

Expected: all filtered tests pass.

- [ ] **Step 2: Run RookBIM tests**

Run:

```powershell
dotnet test src\RookBim.Tests\RookBim.Tests.csproj --no-restore
```

Expected: all tests pass.

- [ ] **Step 3: Run MCP RookBIM tests**

Run:

```powershell
Push-Location mcp_server
uv run --extra test pytest tests\test_rookbim_mcp_tools.py -v
Pop-Location
```

Expected: all tests pass.

- [ ] **Step 4: Build RookBIM Release**

Run:

```powershell
dotnet build src\RookBim\RookBim.csproj -c Release
```

Expected: build succeeds with 0 errors.

- [ ] **Step 5: Full local deploy**

Only run this after Rhino, Revit, and installed `python -m rook` MCP processes are closed or intentionally stopped.

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1
```

Expected: native build exits 0, managed build succeeds, plugin registration verifies, installed runtime verifies.

- [ ] **Step 6: Verify deployed RookBIM hash**

Run:

```powershell
Get-FileHash src\RookBim\bin\Release\net48\RookBim.dll, src\Rook\bin\Release\net48\RookBim.dll, "$env:APPDATA\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net48\RookBim.dll" -Algorithm SHA256 | Select-Object Path,Hash
```

Expected: all three hashes match.

## Task 8: Live Tester Codex Validation Prompt

**Files:**
- No source edits.

- [ ] **Step 1: Start live state**

Open Revit/RhinoInside after deploy. Use Snowdon Plumbing with a floor plan active for the primary pass.

- [ ] **Step 2: Give Tester Codex this prompt**

```text
You are Tester Codex validating the freshly deployed RookBIM runtime category resolver through MCP.

Hard rules:
- Do not deploy, rebuild, restart, kill, or relaunch anything.
- Use MCP tools only.
- Report exact structured payloads.
- Separate real failures from expected semantic failures.

1. Routing
- Bind to the RhinoInside/Revit target if needed.
- Call rhino_ping.
- Call rookbim_status.

2. Document-wide categories
- Call rookbim_list_categories.
- PASS only if response includes document identity, schemaVersion=1, source=document_category_table, and a categories array.
- Confirm the tool does not require or accept scope=active_view.
- Record entries for Pipes, Pipe Fittings, Pipe Accessories, Plumbing Fixtures if present.

3. Query resolution evidence
Run rookbim_query_elements(scope=document, limit=3) for:
- Pipes
- Pipe Fittings
- Pipe Accessories
- Plumbing Fixtures
- Pipe Accessoryz

For each structured success, report query.categoryResolution:
- schemaVersion
- status
- strategy
- queryable
- category.id/name/builtIn/categoryType
- attemptedStrategies

Expected:
- Valid live document categories resolve with status=resolved and queryable=true.
- Bogus Pipe Accessoryz returns invalid_category with details.resolution.status=invalid and bounded suggestions.

4. Category not queryable contract
If any category from rookbim_list_categories resolves but cannot be collected, PASS only if failure is category_not_queryable and details.resolution.status=resolved with queryable=false.
If no such category is found, report this section inconclusive.

5. Round trip
For every non-empty query result, reuse returned category.name as category input with scope=document, limit=3.
PASS if every returned display name resolves or returns ambiguous_category with candidates.

6. Final health
- rhino_ping
- rookbim_status

Report:
- Routing
- List Categories
- Query Resolution Evidence
- Invalid Category Failure Shape
- Category Not Queryable Check
- Returned Category Round Trip
- Final Health
- Real Failures
- Expected Semantic Failures
- Inconclusive Checks
```

Expected: no real failures. `Pipe Accessoryz` should fail semantically with `details.resolution`; valid plumbing categories should resolve from live document categories or report a precise semantic queryability failure.
