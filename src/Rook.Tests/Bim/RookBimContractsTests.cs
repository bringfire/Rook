using System.Collections.Generic;
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class RookBimContractsTests
    {
        [Fact]
        public void QueryElementsRequest_UsesPhaseOneDefaults()
        {
            var request = new BimQueryElementsRequest();

            Assert.Equal(BimQueryScope.ActiveView, request.EffectiveScope);
            Assert.Equal(100, request.EffectiveLimit);
            Assert.Equal(1000, BimQueryElementsRequest.HardMaxLimit);
        }

        [Fact]
        public void Validate_RejectsDocumentScopeWithFiltersAndNoCategory()
        {
            var request = new BimQueryElementsRequest
            {
                Scope = BimQueryScope.Document,
                Filters =
                {
                    new BimQueryFilter
                    {
                        Parameter = "Mark",
                        Operation = BimFilterOperation.Equals,
                        Value = "A101"
                    }
                }
            };

            var result = request.Validate();

            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.UnboundedDocumentQuery, result.ErrorCode);
            Assert.Contains("document scope requires category", result.Message);
        }

        [Fact]
        public void Validate_RejectsUndefinedScope()
        {
            var request = new BimQueryElementsRequest
            {
                Scope = (BimQueryScope)999
            };

            var result = request.Validate();

            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.InvalidScope, result.ErrorCode);
            Assert.Contains("scope is invalid", result.Message);
        }

        [Fact]
        public void Validate_RejectsUndefinedFilterOperation()
        {
            var request = new BimQueryElementsRequest
            {
                Filters =
                {
                    new BimQueryFilter
                    {
                        Parameter = "Mark",
                        Operation = (BimFilterOperation)999,
                        Value = "A101"
                    }
                }
            };

            var result = request.Validate();

            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.InvalidScope, result.ErrorCode);
            Assert.Contains("invalid filter operation", result.Message);
        }

        [Fact]
        public void Validate_TreatsNullFiltersAsEmpty()
        {
            var request = new BimQueryElementsRequest
            {
                Filters = null!
            };

            var exception = Record.Exception(() => request.Validate());
            var result = request.Validate();

            Assert.Null(exception);
            Assert.True(result.Success);
            Assert.Equal(BimErrorCode.None, result.ErrorCode);
            Assert.Empty(request.EffectiveFilters);
        }

        [Fact]
        public void Validate_RejectsNullFilterEntry()
        {
            var request = new BimQueryElementsRequest();
            request.Filters.Add(null!);

            var result = request.Validate();

            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.InvalidScope, result.ErrorCode);
            Assert.Contains("filter is required", result.Message);
        }

        [Theory]
        [InlineData(BimFilterOperation.Equals, false)]
        [InlineData(BimFilterOperation.Contains, false)]
        [InlineData(BimFilterOperation.NotEquals, true)]
        [InlineData(BimFilterOperation.IsEmpty, true)]
        [InlineData(BimFilterOperation.IsNotEmpty, false)]
        public void MissingParameterMatches_UsesPinnedFilterSemantics(
            BimFilterOperation operation,
            bool expected)
        {
            Assert.Equal(expected, BimFilterSemantics.MissingParameterMatches(operation));
        }

        [Fact]
        public void DocumentIdentity_IncludesApprovedDocumentFields()
        {
            var identity = new BimDocumentIdentity
            {
                Guid = "doc-guid"
            };

            string? guid = identity.Guid;
            string? title = identity.Title;
            string? path = identity.Path;

            Assert.Equal("doc-guid", guid);
            Assert.Equal(BimDocumentGuidSource.Unavailable, identity.GuidSource);
            Assert.Null(title);
            Assert.Null(path);
            Assert.False(identity.IsFamilyDocument);
            Assert.False(identity.IsWorkshared);
        }

        [Fact]
        public void ViewIdentity_UsesApprovedIntIdContract()
        {
            var identity = new BimViewIdentity
            {
                Id = 17,
                Type = "ThreeD"
            };

            int id = identity.Id;
            string? type = identity.Type;

            Assert.Equal(17, id);
            Assert.Equal("ThreeD", type);
        }

        [Fact]
        public void ElementIdentity_UsesApprovedIdentityShape()
        {
            var identity = new BimElementIdentity
            {
                DocumentGuid = "doc-guid",
                ElementId = 123,
                LinkInstanceId = 456,
                LinkedDocumentGuid = "linked-doc-guid",
                LinkedElementId = 789
            };

            string? documentGuid = identity.DocumentGuid;
            string? documentTitle = identity.DocumentTitle;
            string? documentPath = identity.DocumentPath;
            int? elementId = identity.ElementId;
            string? uniqueId = identity.UniqueId;
            string? fullUniqueId = identity.FullUniqueId;
            int? linkInstanceId = identity.LinkInstanceId;
            string? linkInstanceUniqueId = identity.LinkInstanceUniqueId;
            string? linkedDocumentGuid = identity.LinkedDocumentGuid;
            int? linkedElementId = identity.LinkedElementId;
            string? linkedElementUniqueId = identity.LinkedElementUniqueId;

            Assert.Equal("revit", identity.Source);
            Assert.Equal("doc-guid", documentGuid);
            Assert.Equal(BimDocumentGuidSource.Unavailable, identity.DocumentGuidSource);
            Assert.Null(documentTitle);
            Assert.Null(documentPath);
            Assert.Equal(123, elementId);
            Assert.Null(uniqueId);
            Assert.Null(fullUniqueId);
            Assert.False(identity.Linked);
            Assert.Equal(456, linkInstanceId);
            Assert.Null(linkInstanceUniqueId);
            Assert.Equal("linked-doc-guid", linkedDocumentGuid);
            Assert.Equal(789, linkedElementId);
            Assert.Null(linkedElementUniqueId);
            Assert.False(identity.Resolved);
            Assert.Equal(BimIdentityConfidence.Unresolved, identity.Confidence);
        }

        [Fact]
        public void QueryElementsResult_UsesStructuredQueryAndElementSummaries()
        {
            var result = new BimQueryElementsResult
            {
                Query =
                {
                    Category = "Walls",
                    Limit = 100,
                    Returned = 1,
                    Truncated = false,
                    Filters =
                    {
                        new BimQueryFilterSummary
                        {
                            Parameter = "IfcGUID",
                            Operation = BimFilterOperation.Contains,
                            Value = "1G_I00"
                        }
                    },
                    MissingParameterCounts =
                    {
                        ["FireRating"] = 2
                    }
                },
                Elements =
                {
                    new BimElementSummary
                    {
                        Name = "Basic Wall",
                        Category =
                        {
                            Id = 2000011,
                            Name = "Walls"
                        },
                        Type =
                        {
                            Id = 42,
                            UniqueId = "type-unique-id",
                            FamilyName = "Basic Wall",
                            Name = "Generic - 8\""
                        }
                    }
                }
            };

            Assert.NotNull(result.Query);
            Assert.Equal("Walls", result.Query.Category);
            Assert.Equal(100, result.Query.Limit);
            Assert.Equal(1, result.Query.Returned);
            Assert.False(result.Query.Truncated);
            var filter = Assert.Single(result.Query.Filters);
            Assert.Equal("IfcGUID", filter.Parameter);
            Assert.Equal(BimFilterOperation.Contains, filter.Operation);
            Assert.Equal("1G_I00", filter.Value);
            Assert.Equal(2, result.Query.MissingParameterCounts["FireRating"]);

            var element = Assert.Single(result.Elements);
            Assert.NotNull(element.Category);
            int? categoryId = element.Category.Id;
            Assert.Equal(2000011, element.Category.Id);
            Assert.Equal(2000011, categoryId);
            Assert.Equal("Walls", element.Category.Name);
            Assert.NotNull(element.Type);
            int? typeId = element.Type.Id;
            Assert.Equal(42, element.Type.Id);
            Assert.Equal(42, typeId);
            Assert.Equal("type-unique-id", element.Type.UniqueId);
            Assert.Equal("Basic Wall", element.Type.FamilyName);
            Assert.Equal("Generic - 8\"", element.Type.Name);
        }

        [Fact]
        public void CategoryResolution_UsesSafeDefaults()
        {
            var resolution = new BimCategoryResolution();

            Assert.Equal(1, resolution.SchemaVersion);
            Assert.Equal(BimCategoryResolutionStatus.Invalid, resolution.Status);
            Assert.Equal(BimCategoryResolutionStrategy.None, resolution.Strategy);
            Assert.Null(resolution.Queryable);
            Assert.False(resolution.Ambiguous);
            Assert.Empty(resolution.AttemptedStrategies);
            Assert.Empty(resolution.Candidates);
            Assert.Empty(resolution.Suggestions);
            Assert.Empty(resolution.AdvisorySources);
        }

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
                SkippedCount = 1,
                DegradedCount = 1,
                Diagnostics = new BimCategoryTableDiagnostics
                {
                    CountsByReason = new Dictionary<string, int>
                    {
                        ["missing_id"] = 1,
                        ["missing_name"] = 1
                    },
                    Examples = new List<string> { "missing_id" }
                },
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
            Assert.Equal(1, result.SkippedCount);
            Assert.Equal(1, result.DegradedCount);
            Assert.Equal(1, result.Diagnostics.CountsByReason["missing_id"]);
            Assert.Single(result.Diagnostics.Examples);
            Assert.Equal("Parent", result.Categories[0].Parent!.Name);
        }
    }
}
